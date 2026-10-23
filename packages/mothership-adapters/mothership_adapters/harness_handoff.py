"""Explicit thin-Harness handoff; no Lease, inference or implicit transport.

The caller owns the preview and callbacks. Hashes correlate supplied inputs;
they do not prove prose/target agreement or authenticate the producer. Fresh
Git checks are best-effort observations, not an atomic execution fence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from mothership.contracts import loads_strict
from .evidence import export_evidence, inspect_evidence, summarize_evidence
from .readback import readback_evidence
from .session import MergeReviewSession, SessionError


MAX_INPUT = 131_072
_PREVIEW_KEYS = frozenset({
    "schema_version", "source", "request_sha256", "interpretation_sha256", "work_type",
    "classification_status", "candidate_actions", "required_human_approvals",
    "surfaced_unknowns", "clarification_blocked", "authority", "execution",
})


class HandoffError(ValueError):
    """Finite local failure; never a request to retry an operation."""


def _invalid():
    return HandoffError("handoff input or retained records unavailable; no retry")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_handoff_json(raw: bytes):
    """Strict, bounded plain JSON shared by explicit local input boundaries."""
    try:
        if type(raw) is not bytes or len(raw) > MAX_INPUT:
            raise _invalid()
        value = loads_strict(raw.decode("utf-8"))
        stack, nodes = [(value, 1)], 0
        while stack:
            item, depth = stack.pop()
            nodes += 1
            if nodes > 4096 or depth > 16:
                raise _invalid()
            if type(item) is str:
                if len(item) > 16384:
                    raise _invalid()
                item.encode("utf-8")
            elif type(item) is dict:
                stack.extend((key, depth) for key in item)
                stack.extend((v, depth + 1) for v in item.values())
            elif type(item) is list:
                stack.extend((v, depth + 1) for v in item)
        # Also rejects non-finite numbers and ill-formed Unicode objects.
        _json(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise _invalid() from None


def _detach(value):
    try:
        return decode_handoff_json(_json(value))
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise _invalid() from None


def validate_preview(preview, raw_request, interpretation):
    try:
        checked, interpreted = _detach(preview), _detach(interpretation)
        if (type(raw_request) is not str or not raw_request.strip()
                or len(raw_request) > 16384 or len(raw_request.encode()) > MAX_INPUT
                or type(checked) is not dict or set(checked) != _PREVIEW_KEYS
                or type(interpreted) is not dict
                or checked["schema_version"] != "ume.preview-handoff.v0"
                or checked["source"] != "offline_interpretation"
                or checked["authority"] is not False or checked["execution"] is not False
                or checked["clarification_blocked"] is not False
                or checked["classification_status"] != "RESOLVED"
                or checked["work_type"] not in ("RESEARCH", "EDIT_CREATE", "ORGANIZE")
                or checked["request_sha256"] != _hash(raw_request.encode())
                or checked["interpretation_sha256"] != _hash(_json(interpreted))):
            raise _invalid()
        for key in ("candidate_actions", "required_human_approvals", "surfaced_unknowns"):
            if (type(checked[key]) is not list
                    or any(type(v) is not str or not v.strip() for v in checked[key])):
                raise _invalid()
        if (not checked["candidate_actions"] or checked["surfaced_unknowns"]
                or checked["candidate_actions"] != interpreted.get("candidate_actions")):
            raise _invalid()
        return checked
    except (ValueError, TypeError, UnicodeError, KeyError):
        raise _invalid() from None


def read_regular(path, limit=MAX_INPUT):
    """One explicit bounded input, no path discovery or symlink following."""
    try:
        path = Path(path).absolute()
        if path.resolve() != path:
            raise _invalid()
        required = {name: getattr(os, name, None) for name in (
            "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC", "O_DIRECTORY")}
        if any(type(flag) is not int or flag <= 0 for flag in required.values()):
            raise _invalid()
        if os.open not in getattr(os, "supports_dir_fd", ()):
            raise _invalid()
        parts = path.parts[1:]
        if not parts:
            raise _invalid()
        directory_flags = (os.O_RDONLY | required["O_NOFOLLOW"]
                           | required["O_CLOEXEC"] | required["O_DIRECTORY"])
        file_flags = (os.O_RDONLY | required["O_NOFOLLOW"]
                      | required["O_NONBLOCK"] | required["O_CLOEXEC"])
        descriptor = os.open(path.anchor, directory_flags)
        try:
            for part in parts[:-1]:
                next_descriptor = os.open(part, directory_flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            fd = os.open(parts[-1], file_flags, dir_fd=descriptor)
            try:
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
                    raise _invalid()
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(limit + 1)
                if len(raw) > limit:
                    raise _invalid()
                return raw
            finally:
                os.close(fd)
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        raise
    except (OSError, ValueError, TypeError):
        raise _invalid() from None


def write_complete(stream, text):
    try:
        written = stream.write(text)
        if type(written) is not int or written != len(text):
            raise _invalid()
        stream.flush()
    except (OSError, ValueError, TypeError):
        raise _invalid() from None


def collect_response(request, input_stream, output_stream):
    """One exact foreground response; test terminal doubles are synthetic."""
    try:
        if not input_stream.isatty() or not output_stream.isatty():
            raise _invalid()
        write_complete(output_stream, json.dumps(request, ensure_ascii=True, indent=2) +
                       "\nSYNTHETIC LOCAL RUN: type approve/reject request_id request_sha256; cancel stops.\n")
        line = input_stream.readline(1025)
        if len(line) > 1024 or not line.endswith("\n"):
            raise _invalid()
        parts = line.strip().split()
        if parts == ["cancel"]:
            return None
        if (len(parts) != 3 or parts[0] not in {"approve", "reject"}
                or parts[1:] != [request["request_id"], request["request_sha256"]]):
            raise _invalid()
        return dict(schema_version="authority-action-review-response.v0", decision=parts[0],
                    request_id=request["request_id"], request_sha256=request["request_sha256"],
                    action_id=request["action"]["action_id"], action_sha256=request["action_sha256"])
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        raise _invalid() from None


class ThinHarnessOwner:
    """Retain one existing Session; read only its explicitly owned ledgers.

    The new directory is never reused or cleaned up on failure. This local
    owner cannot restore a Session or select a default network client.
    """
    def __init__(self, parameters, *, preview, raw_request, interpretation, worktree,
                 run_directory, host_context_provider, transport, executor_ref,
                 interpretation_bytes=None):
        from .worktree_observer import GitWorktreeObserver
        self._preview = validate_preview(preview, raw_request, interpretation)
        original_interpretation = _json(interpretation) if interpretation_bytes is None else interpretation_bytes
        if decode_handoff_json(original_interpretation) != interpretation:
            raise _invalid()
        self._parameters, self._executor_ref = _detach(parameters), _detach(executor_ref)
        self._provider = host_context_provider
        self._response = self._diagnostic = self._readback = None
        self._readback_attempted = self._saved = False
        self._artifacts = {}
        try:
            self._observer = GitWorktreeObserver(worktree, self._parameters["repository"])
            self._baseline = self._observer.observe()
            if (not self._baseline["clean"]
                    or self._baseline["head_sha"] != self._parameters["expected_head_sha"]):
                raise _invalid()
            self.root = Path(run_directory).absolute()
            tree = Path(self._baseline["worktree_realpath"])
            if (self.root.resolve() != self.root or self.root.is_relative_to(tree)
                    or not self.root.parent.is_dir()):
                raise _invalid()
            self.root.mkdir(mode=0o700)
            metadata = self.root.stat()
            self._root_identity = (metadata.st_dev, metadata.st_ino)
            self.authority_path, self.attempts_path = self.root / "authority.jsonl", self.root / "attempts.jsonl"
            self._write("request.txt", raw_request.encode())
            self._write("interpretation.json", original_interpretation)
            self._write("preview.json", _json(self._preview))
            self._write("observation.json", _json(self._baseline))
            self._session = MergeReviewSession(
                self._parameters, context_provider=self._context,
                authority_path=self.authority_path, attempts_path=self.attempts_path,
                transport=transport, executor_ref=self._executor_ref)
            self._write("review-request.json", _json(self.request))
        except (OSError, ValueError, KeyError, TypeError):
            raise _invalid() from None

    def _check_directory(self):
        if self.root.resolve() != self.root:
            raise _invalid()
        metadata = self.root.stat()
        if ((metadata.st_dev, metadata.st_ino) != self._root_identity
                or not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700):
            raise _invalid()

    def _context(self):
        self._check_directory()
        if self._observer.observe() != self._baseline:
            raise _invalid()
        context = _detach(self._provider())
        if (type(context) is not dict or type(context.get("scope")) is not list
                or "github.merge_pr" not in context["scope"]):
            raise _invalid()
        return context

    def _write(self, name, raw):
        self._check_directory()
        flag = getattr(os, "O_NOFOLLOW", None)
        if type(flag) is not int or flag <= 0:
            raise _invalid()
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | flag, 0o600)
        try:
            # A partial artifact is retained as failure evidence, not repaired.
            if os.write(fd, raw) != len(raw):
                raise _invalid()
            os.fsync(fd)
        finally:
            os.close(fd)
        self._artifacts[name] = _hash(raw)

    @property
    def request(self):
        return self._session.request

    def review(self, response):
        self._response = _detach(response)
        try:
            return self._session.review(self._response)
        except SessionError as exc:
            self._diagnostic = exc.diagnostic
            raise

    def execute(self, parameters):
        try:
            return self._session.execute(parameters)
        except SessionError as exc:
            self._diagnostic = exc.diagnostic
            raise

    def cancel(self):
        self._session.cancel()

    def _rows(self, path):
        try:
            raw = read_regular(path, 262144)
        except FileNotFoundError:
            return []
        if raw and not raw.endswith(b"\n"):
            raise _invalid()
        return [decode_handoff_json(line) for line in raw.splitlines()]

    def export(self):
        try:
            self._check_directory()
            records = {}
            allowed = {"authority_action_approval": "decision", "authority_action_consume": "consume",
                       "attempt_started": "started", "attempt_finished": "finished"}
            for row in self._rows(self.authority_path) + self._rows(self.attempts_path):
                if type(row) is not dict or row.get("event_type") not in allowed:
                    raise _invalid()
                key = allowed[row["event_type"]]
                action = row.get("action") if key == "decision" else row
                if (type(action) is not dict or key in records
                        or action.get("action_id") != self.request["action"]["action_id"]):
                    raise _invalid()
                records[key] = row
            return export_evidence(self.request, response=self._response,
                                   executor_ref=self._executor_ref, **records)
        except (ValueError, TypeError, OSError):
            raise _invalid() from None

    def readback(self, *, opener):
        if not callable(opener) or self._readback_attempted:
            raise _invalid()
        original = self.export()
        if original["missing"] != ["verification"]:
            raise _invalid()
        self._readback_attempted = True
        self._observed_from = original["bundle_sha256"]
        self._readback = readback_evidence(original, opener=opener)
        return json.loads(_json(self._readback))

    def save(self):
        if self._saved:
            raise _invalid()
        self._saved = True
        original = self.export()
        self._write("original.json", _json(original))
        bundle, sidecar = original, None
        if self._readback is not None:
            if original["bundle_sha256"] != self._observed_from:
                raise _invalid()
            bundle, sidecar = self._readback["bundle"], self._readback["evidence"]
            self._write("verified.json", _json(bundle))
            self._write("readback-evidence.json", _json(sidecar))
        text = summarize_evidence(bundle, readback_evidence=sidecar)
        outcome = dict(schema_version="thin-harness-handoff-result.v0", local_only=True,
                       retry_allowed=False, inspection=inspect_evidence(bundle),
                       diagnostic=self._diagnostic, human=text,
                       run_directory=str(self.root), session_state=self._session.state)
        self._write("result.json", _json(outcome))
        self._write("RESULT.md", ("# Local injected handoff\n\n" + text +
                                   "\nNo live or human acceptance claim. No retry.\n").encode())
        for path in (self.authority_path, self.attempts_path):
            try:
                self._artifacts[path.name] = _hash(read_regular(path, 262144))
            except FileNotFoundError:
                pass
        self._write("manifest.json", _json(dict(
            schema_version="thin-harness-handoff-manifest.v0", source_authenticated=False,
            live_verified=False, request_id=self.request["request_id"],
            request_sha256=self.request["request_sha256"],
            action_id=self.request["action"]["action_id"], action_sha256=self.request["action_sha256"],
            preview_target_equivalence="not_verified", artifacts=dict(self._artifacts))))
        return outcome

    def __copy__(self):
        raise TypeError("live owners cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("live owners cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("live owners cannot be restored")
