"""Fixed, single-action owner process for the JavaScript host bridge.

The child owns one live :class:`MergeReviewSession`.  It receives only the
trusted ledger paths and parent identity in its launch arguments; all runtime
messages are bounded JSON frames over inherited stdin/stdout.  Context and
transport callbacks remain in the parent process and are never executable JSON.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from .session import MergeReviewSession, SessionError


SCHEMA_VERSION = "mothership-owner.v0"
DIAGNOSTIC_SCHEMA_VERSION = "mothership-owner.v1"
MAX_FRAME_BYTES = 65_536
MAX_DEPTH = 16
MAX_NODES = 2_048
MAX_CONTAINER = 256
MAX_STRING_BYTES = 16_384

_FRAME_KEYS = frozenset(
    {"schema_version", "type", "seq", "reply_to", "owner_id", "request_id", "action_id", "payload"}
)
_TYPES = frozenset({"prepare", "review", "execute", "cancel", "context", "get", "merge", "result", "error"})
_CALLBACK_TYPES = frozenset({"context", "get", "merge"})
_COMMAND_TYPES = frozenset({"prepare", "review", "execute", "cancel"})
_REPLY_TYPES = frozenset({"result", "error"})
_ERROR_CODES = frozenset(
    {
        "closed",
        "context",
        "eof",
        "internal",
        "malformed",
        "nonce",
        "oversized",
        "parameters",
        "parent_lost",
        "phase",
        "protocol",
        "reply",
        "sequence",
        "session",
        "transport",
    }
)
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REF_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REF_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")


class _OwnerError(Exception):
    def __init__(self, code: str):
        self.code = code if code in _ERROR_CODES else "internal"
        super().__init__(self.code)


class _RemoteError(_OwnerError):
    pass


def _reject_constant(_value: str) -> None:
    raise _OwnerError("malformed")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _OwnerError("malformed")
        result[key] = value
    return result


def _check_bounds(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise _OwnerError("oversized")
        if type(current) is str:
            try:
                size = len(current.encode("utf-8"))
            except UnicodeEncodeError:
                raise _OwnerError("malformed") from None
            if size > MAX_STRING_BYTES:
                raise _OwnerError("oversized")
        elif type(current) is dict:
            if len(current) > MAX_CONTAINER:
                raise _OwnerError("oversized")
            for key, child in current.items():
                if type(key) is not str:
                    raise _OwnerError("malformed")
                try:
                    if len(key.encode("utf-8")) > MAX_STRING_BYTES:
                        raise _OwnerError("oversized")
                except UnicodeEncodeError:
                    raise _OwnerError("malformed") from None
                stack.append((child, depth + 1))
        elif type(current) is list:
            if len(current) > MAX_CONTAINER:
                raise _OwnerError("oversized")
            stack.extend((child, depth + 1) for child in current)
        elif current is None or type(current) in (bool, int, float):
            continue
        else:
            raise _OwnerError("malformed")


def _detach(value: object) -> object:
    _check_bounds(value)
    try:
        return json.loads(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except _OwnerError:
        raise
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise _OwnerError("malformed") from None


def _exact(value: object, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise _OwnerError("protocol")
    return value


def _identifier(value: object, *, nullable: bool = True) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or not value or "\n" in value or "\r" in value:
        raise _OwnerError("protocol")
    return value


def _parameters(value: object) -> dict[str, Any]:
    data = _exact(value, {"repository", "pull_request", "expected_head_sha", "expected_base", "merge_method"})
    if (
        type(data["repository"]) is not str
        or _REPOSITORY.fullmatch(data["repository"]) is None
        or type(data["pull_request"]) is not int
        or type(data["pull_request"]) is bool
        or data["pull_request"] <= 0
        or type(data["expected_head_sha"]) is not str
        or _SHA.fullmatch(data["expected_head_sha"]) is None
        or type(data["expected_base"]) is not str
        or not data["expected_base"]
        or type(data["merge_method"]) is not str
        or data["merge_method"] not in {"merge", "squash", "rebase"}
    ):
        raise _OwnerError("parameters")
    return data


def _executor_ref(value: object) -> dict[str, Any]:
    data = _exact(value, {"ref_id", "sha256"})
    if (
        type(data["ref_id"]) is not str
        or not 1 <= len(data["ref_id"]) <= 256
        or _REF_ID.fullmatch(data["ref_id"]) is None
        or type(data["sha256"]) is not str
        or _REF_SHA.fullmatch(data["sha256"]) is None
    ):
        raise _OwnerError("parameters")
    return data


def _review_response(value: object) -> dict[str, Any]:
    data = _exact(value, {"schema_version", "decision", "request_id", "request_sha256", "action_id", "action_sha256"})
    if (
        data["schema_version"] != "authority-action-review-response.v0"
        or type(data["decision"]) is not str
        or data["decision"] not in {"approve", "reject"}
        or type(data["request_id"]) is not str
        or type(data["request_sha256"]) is not str
        or type(data["action_id"]) is not str
        or type(data["action_sha256"]) is not str
    ):
        raise _OwnerError("parameters")
    return data


def _callback_payload(frame_type: str, payload: object) -> object:
    if frame_type == "context":
        if type(payload) is not dict or payload:
            raise _OwnerError("protocol")
        return payload
    if frame_type == "get":
        value = _exact(payload, {"repository", "pull_request"})
        if type(value["repository"]) is not str or type(value["pull_request"]) is not int:
            raise _OwnerError("parameters")
        return value
    value = _exact(payload, {"repository", "pull_request", "expected_head_sha", "merge_method"})
    if (
        type(value["repository"]) is not str
        or type(value["pull_request"]) is not int
        or type(value["expected_head_sha"]) is not str
        or type(value["merge_method"]) is not str
    ):
        raise _OwnerError("parameters")
    return value


def _validate_frame(value: object, owner_id: str, schema_version: str = SCHEMA_VERSION) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _FRAME_KEYS:
        raise _OwnerError("protocol")
    if value["schema_version"] != schema_version or value["owner_id"] != owner_id:
        raise _OwnerError("nonce")
    if type(value["type"]) is not str or value["type"] not in _TYPES:
        raise _OwnerError("protocol")
    if (
        type(value["seq"]) is not int
        or type(value["seq"]) is bool
        or not 0 < value["seq"] <= 2**53
    ):
        raise _OwnerError("sequence")
    if value["reply_to"] is not None and (
        type(value["reply_to"]) is not int
        or type(value["reply_to"]) is bool
        or not 0 < value["reply_to"] <= 2**53
    ):
        raise _OwnerError("reply")
    _identifier(value["request_id"])
    _identifier(value["action_id"])
    _check_bounds(value["payload"])
    frame_type = value["type"]
    payload = value["payload"]
    if frame_type == "prepare":
        if value["reply_to"] is not None or value["request_id"] is not None or value["action_id"] is not None:
            raise _OwnerError("protocol")
        data = _exact(payload, {"parameters", "executor_ref"})
        _parameters(data["parameters"])
        _executor_ref(data["executor_ref"])
    elif frame_type == "review":
        if value["reply_to"] is not None:
            raise _OwnerError("protocol")
        _review_response(payload)
    elif frame_type == "execute":
        if value["reply_to"] is not None:
            raise _OwnerError("protocol")
        _parameters(payload)
    elif frame_type == "cancel":
        if value["reply_to"] is not None or payload != {}:
            raise _OwnerError("protocol")
    elif frame_type in _CALLBACK_TYPES:
        if value["reply_to"] is not None:
            raise _OwnerError("protocol")
        _callback_payload(frame_type, payload)
    elif frame_type == "error":
        if value["reply_to"] is None:
            raise _OwnerError("reply")
        data = _exact(payload, {"code"})
        if type(data["code"]) is not str or data["code"] not in _ERROR_CODES:
            raise _OwnerError("protocol")
    elif frame_type == "result":
        if value["reply_to"] is None:
            raise _OwnerError("reply")
    return value


class _OwnerProcess:
    def __init__(self, owner_id: str, parent_pid: int, authority_path: Path, attempts_path: Path,
                 *, session_diagnostics: bool = False):
        if type(owner_id) is not str or not owner_id or "\n" in owner_id:
            raise _OwnerError("nonce")
        if type(parent_pid) is not int or parent_pid <= 0:
            raise _OwnerError("parameters")
        if authority_path.resolve() == attempts_path.resolve():
            raise _OwnerError("parameters")
        self.owner_id = owner_id
        self.parent_pid = parent_pid
        self.authority_path = authority_path
        self.attempts_path = attempts_path
        self.schema_version = DIAGNOSTIC_SCHEMA_VERSION if session_diagnostics else SCHEMA_VERSION
        self.in_seq = 1
        self.out_seq = 1
        self.session: MergeReviewSession | None = None
        self.request_id: str | None = None
        self.action_id: str | None = None
        self.terminal = False
        self.command_type: str | None = None

    def _check_parent(self) -> None:
        if os.getppid() != self.parent_pid:
            raise _OwnerError("parent_lost")

    def _write(self, frame_type: str, payload: object, *, reply_to: int | None = None) -> int:
        self._check_parent()
        _check_bounds(payload)
        frame = {
            "schema_version": self.schema_version,
            "type": frame_type,
            "seq": self.out_seq,
            "reply_to": reply_to,
            "owner_id": self.owner_id,
            "request_id": self.request_id,
            "action_id": self.action_id,
            "payload": payload,
        }
        raw = (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > MAX_FRAME_BYTES:
            raise _OwnerError("oversized")
        try:
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()
        except (BrokenPipeError, OSError):
            raise _OwnerError("closed") from None
        seq = self.out_seq
        self.out_seq += 1
        return seq

    def _read(self) -> dict[str, Any]:
        self._check_parent()
        try:
            raw = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
        except (OSError, ValueError):
            raise _OwnerError("eof") from None
        if not raw:
            raise _OwnerError("eof")
        if len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
            raise _OwnerError("oversized" if len(raw) > MAX_FRAME_BYTES else "malformed")
        try:
            text = raw.decode("utf-8")
            value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)
        except _OwnerError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
            raise _OwnerError("malformed") from None
        _check_bounds(value)
        frame = _validate_frame(value, self.owner_id, self.schema_version)
        if frame["seq"] != self.in_seq:
            raise _OwnerError("sequence")
        self.in_seq += 1
        return frame

    def _callback(self, frame_type: str, payload: object) -> object:
        if self.command_type is None:
            raise _OwnerError("phase")
        callback_seq = self._write(frame_type, payload)
        response = self._read()
        if response["type"] not in _REPLY_TYPES or response["reply_to"] != callback_seq:
            raise _OwnerError("reply")
        if response["request_id"] != self.request_id or response["action_id"] != self.action_id:
            raise _OwnerError("protocol")
        if response["type"] == "error":
            raise _RemoteError(response["payload"]["code"])
        return response["payload"]

    def context(self) -> dict[str, Any]:
        value = self._callback("context", {})
        if type(value) is not dict:
            raise _OwnerError("context")
        return value

    def get_pull_request(self, repository: str, pull_request: int) -> dict[str, Any]:
        value = self._callback("get", {"repository": repository, "pull_request": pull_request})
        if type(value) is not dict:
            raise _OwnerError("transport")
        return value

    def merge_pull_request(self, **parameters: Any) -> dict[str, Any]:
        value = self._callback("merge", parameters)
        if type(value) is not dict:
            raise _OwnerError("transport")
        return value

    def _check_command_ids(self, frame: dict[str, Any]) -> None:
        if self.session is None:
            if frame["request_id"] is not None or frame["action_id"] is not None:
                raise _OwnerError("protocol")
        elif frame["request_id"] != self.request_id or frame["action_id"] != self.action_id:
            raise _OwnerError("protocol")

    def _handle(self, frame: dict[str, Any]) -> object:
        frame_type = frame["type"]
        if frame_type not in _COMMAND_TYPES or frame["reply_to"] is not None:
            raise _OwnerError("protocol")
        self._check_command_ids(frame)
        if frame_type == "prepare":
            if self.session is not None or self.terminal:
                raise _OwnerError("phase")
            data = frame["payload"]
            self.command_type = "prepare"
            self.session = MergeReviewSession(
                _parameters(data["parameters"]),
                context_provider=self.context,
                authority_path=self.authority_path,
                attempts_path=self.attempts_path,
                transport=self,
                executor_ref=_executor_ref(data["executor_ref"]),
            )
            request = self.session.request
            self.request_id = request["request_id"]
            self.action_id = request["action"]["action_id"]
            self.command_type = None
            return request
        if self.session is None or self.terminal:
            raise _OwnerError("phase")
        self.command_type = frame_type
        if frame_type == "review":
            decision = self.session.review(frame["payload"])
            self.command_type = None
            if decision not in {"approve", "reject"}:
                raise _OwnerError("session")
            if decision == "reject":
                self.terminal = True
            return decision
        if frame_type == "execute":
            result = self.session.execute(_parameters(frame["payload"]))
            self.command_type = None
            self.terminal = True
            return result
        if frame_type == "cancel":
            if self.session.state in {"finished", "rejected", "failed", "canceled"}:
                raise _OwnerError("phase")
            self.session.cancel()
            self.command_type = None
            self.terminal = True
            return None
        raise _OwnerError("protocol")

    def run(self) -> int:
        while True:
            frame: dict[str, Any] | None = None
            try:
                frame = self._read()
                result = self._handle(frame)
                self._write("result", result, reply_to=frame["seq"])
            except _OwnerError as error:
                try:
                    self._write("error", {"code": error.code}, reply_to=frame["seq"] if frame is not None else None)
                except Exception:
                    pass
                return 2
            except SessionError as error:
                try:
                    payload = {"code": "session"}
                    if self.schema_version == DIAGNOSTIC_SCHEMA_VERSION:
                        payload["diagnostic"] = error.diagnostic
                    self._write("error", payload, reply_to=frame["seq"] if frame is not None else None)
                except Exception:
                    pass
                return 2
            except Exception:
                try:
                    self._write("error", {"code": "session"}, reply_to=frame["seq"] if frame is not None else None)
                except Exception:
                    pass
                return 2


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--authority-path", required=True)
    parser.add_argument("--attempts-path", required=True)
    parser.add_argument("--session-diagnostics", action="store_true")
    try:
        return parser.parse_args(argv)
    except SystemExit:
        raise _OwnerError("parameters") from None


def main(argv: list[str] | None = None) -> int:
    try:
        args = _arguments(argv)
        owner = _OwnerProcess(
            args.owner_id,
            args.parent_pid,
            Path(args.authority_path),
            Path(args.attempts_path),
            session_diagnostics=args.session_diagnostics,
        )
        return owner.run()
    except _OwnerError:
        return 2
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["MAX_CONTAINER", "MAX_DEPTH", "MAX_FRAME_BYTES", "MAX_NODES", "MAX_STRING_BYTES", "SCHEMA_VERSION", "main"]
