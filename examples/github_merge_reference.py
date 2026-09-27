"""Human-operated reference consumer for one GitHub PR merge.

This example deliberately keeps the ceremony in one process: a read-only PR
fetch supplies the exact values passed to Core, Core issues one retained
``FrozenAction``, the action is displayed as JSON, a trusted local operator
enters the exact action-bound response, and the existing companion executor is
called once only after Core records an approval.  The example has no resume,
retry, credential discovery, or approval bypass path.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
import warnings

from mothership import action_authority
from mothership_github import executor
from mothership_github.transport import GitHubRestTransport


_DEFAULT_REPOSITORY = "UMEBOSHIISAN/mothership"
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_BASE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_LEDGER_NAMES = ("authority.jsonl", "attempts.jsonl")
_STATUSES = frozenset({"success", "failure", "reconciliation_required"})
_CONSUMER_SOURCE_REF_ID = "consumer-source:github_merge_reference.py"
_RECEIPT_UNAVAILABLE = "receipt_unavailable"
_VERIFICATION_UNAVAILABLE = "verification_unavailable"


class _UsageError(Exception):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise _UsageError


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="github_merge_reference.py",
        description="Human-operated one-shot reference consumer for github.merge_pr",
    )
    parser.add_argument("--repo", default=_DEFAULT_REPOSITORY)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--ledger-dir", required=True)
    # Core 0.4.3.dev0 intentionally exposes only the merge method.
    parser.add_argument("--merge-method", choices=("merge",), default="merge")
    parser.add_argument(
        "--verify-result",
        action="store_true",
        help="build a Receipt and perform one independent tokenless read-back",
    )
    return parser


def _is_tty(stream: object) -> bool:
    try:
        return bool(stream.isatty()) and callable(getattr(stream, "readline", None))
    except BaseException:
        return False


def _is_output_tty(stream: object) -> bool:
    try:
        return bool(stream.isatty()) and callable(getattr(stream, "write", None)) and callable(
            getattr(stream, "flush", None)
        )
    except BaseException:
        return False


def _json_value(value: object) -> object:
    """Convert Core's immutable mappings to JSON values without stringifying them."""

    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _emit(output_stream: object, payload: Mapping[str, object]) -> bool:
    """Write one JSON line; dynamic values are escaped by the JSON encoder."""

    try:
        line = json.dumps(
            _json_value(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        output_stream.write(line + "\n")
        output_stream.flush()
        return True
    except BaseException:
        return False


def _paths(ledger_dir: Path) -> dict[str, str]:
    return {
        "authority": os.fspath(ledger_dir / _LEDGER_NAMES[0]),
        "attempts": os.fspath(ledger_dir / _LEDGER_NAMES[1]),
    }


def _terminal_failure(
    output_stream: object,
    ledger_dir: Path,
    reason: str,
    *,
    status: str = "pre_execution_failure",
) -> int:
    _emit(
        output_stream,
        {
            "event": "stopped",
            "status": status,
            "reason": reason,
            "mutation_attempted": False if status == "pre_execution_failure" else "unknown",
            "paths": _paths(ledger_dir),
        },
    )
    return 1


def _validate_ledger_dir(value: object) -> Path:
    if type(value) is not str or not value:
        raise ValueError
    if "\x00" in value or not os.path.isabs(value) or os.path.normpath(value) != value:
        raise ValueError
    if value == os.path.sep or not os.path.lexists(value):
        raise ValueError

    path = Path(value)
    try:
        info = os.lstat(path)
    except OSError:
        raise ValueError from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError

    # Compare the real path, but never replace the caller's path with it.  A
    # symlink in any parent component is an alias and is rejected as well.
    try:
        if os.path.realpath(value) != value:
            raise ValueError
    except OSError:
        raise ValueError from None

    for name in _LEDGER_NAMES:
        if os.path.lexists(path / name):
            raise ValueError
    return path


def _validate_snapshot(snapshot: object) -> tuple[str, str]:
    if not isinstance(snapshot, Mapping):
        raise ValueError
    if type(snapshot.get("http_status")) is not int or snapshot["http_status"] != 200:
        raise ValueError
    if snapshot.get("state") != "open":
        raise ValueError
    if type(snapshot.get("merged")) is not bool or snapshot["merged"] is not False:
        raise ValueError
    head_sha = snapshot.get("head_sha")
    base_ref = snapshot.get("base_ref")
    if type(head_sha) is not str or _SHA_PATTERN.fullmatch(head_sha) is None:
        raise ValueError
    if (
        type(base_ref) is not str
        or not 1 <= len(base_ref) <= 128
        or _BASE_PATTERN.fullmatch(base_ref) is None
    ):
        raise ValueError
    return head_sha, base_ref


def _manual_token_prompt(prompt: str) -> str:
    # A warning means getpass could not disable terminal echo.  Treat it as a
    # hard stop rather than falling back to visible input.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        token = getpass.getpass(prompt)
    if type(token) is not str or not token or token != token.strip():
        raise ValueError
    return token


def _approval_line(input_stream: object, output_stream: object, frozen) -> str | None:
    action_id = frozen.action["action_id"]
    digest = frozen.action_sha256
    exact = f"approve {action_id} {digest}"
    reject = f"reject {action_id} {digest}"
    if not _emit(
        output_stream,
        {
            "event": "approval_required",
            "consume_deadline": frozen.expires_at,
            "limits": {
                "ttl": "expires_at is the deadline for Core consume; no renewal or retry",
                "base": "base is checked during preflight only; the PUT has no atomic base condition",
                "operator": "trusted local operator; this example does not authenticate identity",
            },
            "exact_input": f"{exact} OR {reject}",
        },
    ):
        return None
    try:
        line = input_stream.readline()
    except EOFError:
        _emit(output_stream, {"event": "stopped", "reason": "approval_eof"})
        return None
    except KeyboardInterrupt:
        _emit(output_stream, {"event": "stopped", "reason": "approval_interrupted"})
        return None
    except BaseException:
        _emit(output_stream, {"event": "stopped", "reason": "approval_read_failed"})
        return None
    if type(line) is not str:
        _emit(output_stream, {"event": "stopped", "reason": "approval_mismatch"})
        return None
    if line == "":
        _emit(output_stream, {"event": "stopped", "reason": "approval_eof"})
        return None
    response = line.rstrip("\r\n")
    if response == exact:
        return "approve"
    if response == reject:
        return "reject"
    _emit(output_stream, {"event": "stopped", "reason": "approval_mismatch"})
    return None


def _execution_payload(result: object, ledger_dir: Path) -> tuple[dict[str, object], int]:
    if not isinstance(result, Mapping) or type(result.get("status")) is not str:
        return _reconciliation_payload(ledger_dir, "unknown")
    status = result["status"]
    if status not in _STATUSES:
        return _reconciliation_payload(ledger_dir, "unknown")
    required = ("http_status", "merged", "merge_commit_sha")
    if any(name not in result for name in required):
        return _reconciliation_payload(ledger_dir, "unknown")
    http_status = result["http_status"]
    merged = result["merged"]
    merge_commit_sha = result["merge_commit_sha"]
    if type(http_status) is not int or (http_status != 0 and not 100 <= http_status <= 599):
        return _reconciliation_payload(ledger_dir, "unknown")
    if merged is not None and type(merged) is not bool:
        return _reconciliation_payload(ledger_dir, "unknown")
    if merge_commit_sha is not None and (
        type(merge_commit_sha) is not str or _SHA_PATTERN.fullmatch(merge_commit_sha) is None
    ):
        return _reconciliation_payload(ledger_dir, "unknown")
    # Keep the same outcome/fact invariants as the companion's receipt rows.
    # A returned label alone must not turn contradictory facts into success
    # or failure. Explicit reconciliation remains unresolved even when its
    # observation resembles success; this consumer does not verify GitHub.
    if status == "success" and not (
        http_status == 200 and merged is True and merge_commit_sha is not None
    ):
        return _reconciliation_payload(ledger_dir, "unknown")
    if status == "failure" and (merged is True or merge_commit_sha is not None):
        return _reconciliation_payload(ledger_dir, "unknown")
    payload = {
        "event": "execution_result",
        "status": status,
        # The executor returned after entering its mutation stage.  This is
        # not proof that a network request reached GitHub.
        "mutation_attempted": True,
        "http_status": http_status,
        "merged": merged,
        "merge_commit_sha": merge_commit_sha,
        "paths": _paths(ledger_dir),
    }
    return payload, 0 if status == "success" else 1


def _reconciliation_payload(
    ledger_dir: Path, mutation_attempted: bool | str
) -> tuple[dict[str, object], int]:
    return (
        {
            "event": "execution_result",
            "status": "reconciliation_required",
            "mutation_attempted": mutation_attempted,
            "paths": _paths(ledger_dir),
        },
        1,
    )


def _consumer_source_reference() -> dict[str, str]:
    """Freeze a caller-attested hash of this consumer before execution."""

    try:
        source = Path(__file__).read_bytes()
        digest = hashlib.sha256(source).hexdigest()
    except BaseException:
        raise ValueError from None
    return {"ref_id": _CONSUMER_SOURCE_REF_ID, "sha256": digest}


def _verification_payload(
    ledger_dir: Path,
    execution_status: str,
    source_pair: object,
    receipt: object,
    *,
    status: str,
    reason: str | None = None,
    bundle: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Shape one output-only verification event without adding persistence."""

    payload: dict[str, object] = {
        "event": "verification_result",
        "execution_status": execution_status,
        "status": status,
        "source_pair": source_pair,
        "receipt": receipt,
        "verification": None,
        "evidence": None,
        "paths": _paths(ledger_dir),
    }
    if reason is not None:
        payload["reason"] = reason
    if bundle is not None:
        payload["verification"] = bundle.get("verification")
        payload["evidence"] = bundle.get("evidence")
    return payload


def _run_verification(
    frozen,
    result: object,
    ledger_dir: Path,
    executor_ref: Mapping[str, str],
    *,
    execution_status: str,
    readback_opener=None,
) -> tuple[dict[str, object], object]:
    """Build one receipt and perform one independent read-back.

    Imports stay inside this opt-in path so execution-only callers never reach
    the adapter or verifier modules.  Exceptions become fixed, non-diagnostic
    output reasons; the original attempt records remain untouched.
    """

    started = result.get("attempt_started") if isinstance(result, Mapping) else None
    finished = result.get("attempt_finished") if isinstance(result, Mapping) else None
    consume_event = result.get("consume_event") if isinstance(result, Mapping) else None
    receipt = None

    try:
        if not isinstance(consume_event, Mapping) or type(consume_event.get("event_id")) is not str:
            raise ValueError
        if not isinstance(started, Mapping) or not isinstance(finished, Mapping):
            raise ValueError
        expected_action = frozen.action
        expected_action_id = expected_action["action_id"]
        expected_action_sha256 = frozen.action_sha256
        from mothership_github.external_action import build_external_action_receipt

        receipt = build_external_action_receipt(
            started,
            finished,
            expected_action_id=expected_action_id,
            expected_action_sha256=expected_action_sha256,
            expected_consume_event_id=consume_event["event_id"],
            executor_ref=executor_ref,
        )
    except BaseException:
        return (
            _verification_payload(
                ledger_dir,
                execution_status,
                None,
                None,
                status="unavailable",
                reason=_RECEIPT_UNAVAILABLE,
            ),
            None,
        )

    source_pair = {"started": started, "finished": finished}

    try:
        from mothership_github.verification import verify_merge_pr

        if readback_opener is None:
            bundle = verify_merge_pr(frozen, receipt)
        else:
            bundle = verify_merge_pr(frozen, receipt, opener=readback_opener)
        if not isinstance(bundle, Mapping):
            raise ValueError
        verification = bundle.get("verification")
        evidence = bundle.get("evidence")
        if not isinstance(verification, Mapping) or not isinstance(evidence, Mapping):
            raise ValueError
        status = verification.get("status")
        if status not in {"CONFIRMED", "MISMATCH", "UNKNOWN"}:
            raise ValueError
    except BaseException:
        return (
            _verification_payload(
                ledger_dir,
                execution_status,
                source_pair,
                receipt,
                status="unavailable",
                reason=_VERIFICATION_UNAVAILABLE,
            ),
            receipt,
        )

    return (
        _verification_payload(
            ledger_dir,
            execution_status,
            source_pair,
            receipt,
            status=status,
            bundle=bundle,
        ),
        receipt,
    )


def main(
    argv: list[str] | None = None,
    *,
    transport=None,
    input_stream=None,
    output_stream=None,
    token_prompt=None,
    readback_opener=None,
) -> int:
    """Run one human-operated merge ceremony.

    ``transport``, streams, and ``token_prompt`` are explicit test seams.  The
    normal path uses a terminal and constructs ``GitHubRestTransport`` from
    one manually entered token; no environment or config lookup is performed.
    """

    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    # This check intentionally precedes parsing, ledger inspection, prompts,
    # and all other I/O.  Tests use terminal-shaped in-memory streams.
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    if "--help" in raw_arguments or "-h" in raw_arguments:
        try:
            _parser().print_help(file=output_stream)
            output_stream.flush()
        except BaseException:
            return 1
        return 0
    if not _is_tty(input_stream) or not _is_output_tty(output_stream):
        return 2

    try:
        arguments = _parser().parse_args(argv)
    except _UsageError:
        _emit(output_stream, {"event": "stopped", "reason": "invalid_arguments"})
        return 2
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2

    try:
        ledger_dir = _validate_ledger_dir(arguments.ledger_dir)
    except BaseException:
        # Paths are shown only through _emit's JSON encoder; exception text is
        # deliberately never exposed to the terminal.
        ledger_dir = Path(arguments.ledger_dir) if type(arguments.ledger_dir) is str else Path(".")
        return _terminal_failure(output_stream, ledger_dir, "ledger_unavailable")

    active_transport = transport
    if active_transport is None:
        prompt = token_prompt if token_prompt is not None else _manual_token_prompt
        if not callable(prompt):
            return _terminal_failure(output_stream, ledger_dir, "token_unavailable")
        if not _emit(
            output_stream,
            {"event": "token_required", "message": "enter a GitHub token manually; it is not stored"},
        ):
            return 1
        try:
            token = prompt("GitHub token (manual input; not stored): ")
            active_transport = GitHubRestTransport(token)
        except BaseException:
            return _terminal_failure(output_stream, ledger_dir, "token_unavailable")

    if not callable(getattr(active_transport, "get_pull_request", None)):
        return _terminal_failure(output_stream, ledger_dir, "transport_unavailable")
    try:
        snapshot = active_transport.get_pull_request(arguments.repo, arguments.pr)
        expected_head_sha, expected_base = _validate_snapshot(snapshot)
    except BaseException:
        return _terminal_failure(output_stream, ledger_dir, "preflight_unavailable")

    action_id = f"act-reference-github-merge-pr-{arguments.pr}-{uuid.uuid4().hex}"
    try:
        # Keep this object alive through record and executor.  The approval is
        # always derived from this exact Core-issued context.
        frozen = action_authority.freeze_action(
            action_id,
            "github.merge_pr",
            {
                "repository": arguments.repo,
                "pull_request": arguments.pr,
                "expected_head_sha": expected_head_sha,
                "expected_base": expected_base,
                "merge_method": arguments.merge_method,
            },
        )
    except BaseException:
        return _terminal_failure(output_stream, ledger_dir, "action_unavailable")

    if not _emit(
        output_stream,
        {
            "event": "frozen_action",
            "action": _json_value(frozen.action),
            "action_sha256": frozen.action_sha256,
            "expires_at": frozen.expires_at,
        },
    ):
        return 1
    decision = _approval_line(input_stream, output_stream, frozen)
    if decision is None:
        return 0

    try:
        approval = action_authority.record_action_decision(
            ledger_dir / _LEDGER_NAMES[0],
            frozen,
            decision,
            frozen.action["action_id"],
            frozen.action_sha256,
        )
        approval_event_id = approval.get("event_id") if isinstance(approval, Mapping) else None
        if type(approval_event_id) is not str:
            raise ValueError
    except BaseException:
        return _terminal_failure(output_stream, ledger_dir, "decision_record_failed")

    if decision == "reject":
        if not _emit(
            output_stream,
            {
                "event": "decision_recorded",
                "status": "rejected",
                "approval_event_id": approval_event_id,
                "paths": _paths(ledger_dir),
            },
        ):
            return 1
        return 0

    executor_ref = None
    if arguments.verify_result:
        try:
            executor_ref = _consumer_source_reference()
        except BaseException:
            return _terminal_failure(output_stream, ledger_dir, "consumer_source_unavailable")

    try:
        result = executor.execute_action_merge_pr(
            ledger_dir / _LEDGER_NAMES[0],
            ledger_dir / _LEDGER_NAMES[1],
            frozen,
            approval_event_id,
            active_transport,
        )
    except BaseException:
        # An executor interruption or receipt write fault may follow a PUT.
        # Never turn that uncertainty into success or an unmerged claim.
        _emit(
            output_stream,
            {
                "event": "execution_result",
                "status": "reconciliation_required",
                "mutation_attempted": "unknown",
                "paths": _paths(ledger_dir),
            },
        )
        return 1

    payload, code = _execution_payload(result, ledger_dir)
    if not _emit(output_stream, payload):
        return 1
    if not arguments.verify_result:
        return code

    verification_payload, receipt = _run_verification(
        frozen,
        result,
        ledger_dir,
        executor_ref,
        execution_status=payload["status"],
        readback_opener=readback_opener,
    )
    if not _emit(output_stream, verification_payload):
        return 1
    if code != 0:
        return 1
    if receipt is None:
        return 3
    if not isinstance(receipt, Mapping) or receipt.get("status") != "SUCCESS":
        return 1
    if verification_payload.get("status") == "CONFIRMED":
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
