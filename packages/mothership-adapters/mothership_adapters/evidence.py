"""Bounded, deterministic, non-authorizing host evidence export.

The exporter accepts detached JSON rows that were produced by Core and the
GitHub companion.  It validates their public shapes and relationships, but it
does not read a ledger, restore a live action, authenticate a source, or infer
that an external effect occurred.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import math
import re
import unicodedata as _unicodedata
from collections.abc import Iterable

from mothership.contracts import (
    ContractError,
    canonical_json_sha256,
    validate_contract,
    validate_receipt_verification_binding,
)
from mothership_github.external_action import build_external_action_receipt
from mothership_github import receipts as _attempt_receipts

from orchestration.lib import action_authority


SCHEMA_VERSION = "host-evidence-bundle.v0"

MAX_ENCODED_BYTES = 262_144
MAX_DEPTH = 24
MAX_NODES = 8_192
MAX_CONTAINER_ENTRIES = 1_024
MAX_STRING_BYTES = 65_536

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "request",
        "response",
        "decision",
        "consume",
        "started",
        "finished",
        "executor_ref",
        "receipt",
        "verification",
        "source_sha256",
        "missing",
        "bundle_sha256",
    }
)
_SOURCE_KEYS = (
    "request",
    "response",
    "decision",
    "consume",
    "started",
    "finished",
    "executor_ref",
    "verification",
)
_MISSING_KEYS = ("response", "decision", "consume", "started", "finished", "verification")
_DIGEST = re.compile(r"^[0-9a-f]{64}$\Z")
_ACTION_ID = re.compile(r"^act-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_EVENT_ID = re.compile(r"^event-[0-9a-f]{32}\Z")
_REF_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_UTC = "%Y-%m-%dT%H:%M:%SZ"
_MAX_DISPLAY_SUMMARY_CHARS = 256


class EvidenceError(ContractError):
    """A public, sanitized evidence validation failure."""


EvidenceValidationError = EvidenceError


def _invalid() -> EvidenceError:
    return EvidenceError("invalid bounded evidence input")


def _bounded_plain(value: object, *, max_bytes: int = MAX_ENCODED_BYTES) -> object:
    """Validate plain JSON values iteratively before any recursive validator.

    The MCP surface receives already-decoded values, so this check closes the
    object model and supplies the same depth/node/container/string limits used
    by the CLI's strict JSON decoder.  Shared (acyclic) containers are fine;
    an active back-edge is a cycle and is rejected.
    """

    if type(max_bytes) is not int or max_bytes <= 0:
        raise _invalid()
    stack: list[tuple[object, int, bool]] = [(value, 1, False)]
    active: set[int] = set()
    nodes = 0
    try:
        while stack:
            current, depth, leaving = stack.pop()
            if leaving:
                active.discard(id(current))
                continue
            nodes += 1
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                raise _invalid()
            current_type = type(current)
            if current is None or current_type is bool or current_type is int:
                continue
            if current_type is float:
                if not math.isfinite(current):
                    raise _invalid()
                continue
            if current_type is str:
                if len(current.encode("utf-8")) > MAX_STRING_BYTES:
                    raise _invalid()
                continue
            if current_type is dict:
                marker = id(current)
                if marker in active:
                    raise _invalid()
                if len(current) > MAX_CONTAINER_ENTRIES:
                    raise _invalid()
                active.add(marker)
                stack.append((current, depth, True))
                for key, item in reversed(tuple(current.items())):
                    if type(key) is not str:
                        raise _invalid()
                    if len(key.encode("utf-8")) > MAX_STRING_BYTES:
                        raise _invalid()
                    stack.append((item, depth + 1, False))
                continue
            if current_type is list:
                marker = id(current)
                if marker in active:
                    raise _invalid()
                if len(current) > MAX_CONTAINER_ENTRIES:
                    raise _invalid()
                active.add(marker)
                stack.append((current, depth, True))
                for item in reversed(current):
                    stack.append((item, depth + 1, False))
                continue
            raise _invalid()
    except (UnicodeEncodeError, RuntimeError):
        raise _invalid() from None

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise _invalid() from None
    if len(encoded) > max_bytes:
        raise _invalid()
    return value


def _detach(value: object) -> object:
    """Detach a value after :func:`_bounded_plain` has closed its types."""

    if type(value) is dict:
        return {key: _detach(item) for key, item in value.items()}
    if type(value) is list:
        return [_detach(item) for item in value]
    return value


def _canonical(value: object) -> tuple[object, bytes]:
    _bounded_plain(value)
    detached = _detach(value)
    try:
        encoded = json.dumps(
            detached,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise _invalid() from None
    if len(encoded) > MAX_ENCODED_BYTES:
        raise _invalid()
    return detached, encoded


def _hash(value: object) -> str:
    _, encoded = _canonical(value)
    return hashlib.sha256(encoded).hexdigest()


def _copy_checked_contract(kind: str, value: object) -> dict[str, object]:
    detached, _ = _canonical(value)
    try:
        checked = validate_contract(kind, detached)
    except (ContractError, TypeError, ValueError, RecursionError):
        raise _invalid() from None
    return _detach(checked)  # type: ignore[return-value]


def _parse_utc(value: object) -> _datetime.datetime:
    if type(value) is not str:
        raise _invalid()
    try:
        return _datetime.datetime.strptime(value, _UTC).replace(tzinfo=_datetime.UTC)
    except (TypeError, ValueError):
        raise _invalid() from None


def _require_digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise _invalid()
    return value


def _require_event_id(value: object) -> str:
    if type(value) is not str or _EVENT_ID.fullmatch(value) is None:
        raise _invalid()
    return value


def _require_action_id(value: object) -> str:
    if type(value) is not str or _ACTION_ID.fullmatch(value) is None:
        raise _invalid()
    return value


def _validate_request(value: object) -> dict[str, object]:
    request = _copy_checked_contract("authority-action-review-request", value)
    unsigned = {key: request[key] for key in request if key != "request_sha256"}
    if canonical_json_sha256(unsigned) != request["request_sha256"]:
        raise _invalid()
    action = request.get("action")
    digest = request.get("action_sha256")
    try:
        action_digest = action_authority.action_sha256(action)  # type: ignore[arg-type]
    except (ContractError, TypeError, ValueError, RecursionError):
        raise _invalid() from None
    if action_digest != digest:
        raise _invalid()
    _parse_utc(request["expires_at"])
    return request


def _validate_response(value: object, request: dict[str, object]) -> dict[str, object]:
    response = _copy_checked_contract("authority-action-review-response", value)
    if (
        response["request_id"] != request["request_id"]
        or response["request_sha256"] != request["request_sha256"]
        or response["action_id"] != request["action"]["action_id"]
        or response["action_sha256"] != request["action_sha256"]
    ):
        raise _invalid()
    return response


def _validate_executor_ref(value: object) -> dict[str, object]:
    detached, _ = _canonical(value)
    if type(detached) is not dict or set(detached) != {"ref_id", "sha256"}:
        raise _invalid()
    ref_id = detached["ref_id"]
    digest = detached["sha256"]
    if (
        type(ref_id) is not str
        or not 1 <= len(ref_id) <= 256
        or _REF_ID.fullmatch(ref_id) is None
        or type(digest) is not str
        or _DIGEST.fullmatch(digest) is None
    ):
        raise _invalid()
    return detached


def _validate_decision(
    value: object,
    request: dict[str, object],
    response: dict[str, object] | None,
) -> dict[str, object]:
    decision = _copy_checked_contract("authority-action-approval", value)
    action = request["action"]
    if (
        decision["action"] != action
        or decision["action_sha256"] != request["action_sha256"]
        or decision["expires_at"] != request["expires_at"]
    ):
        raise _invalid()
    _require_event_id(decision["event_id"])
    recorded = _parse_utc(decision["recorded_at"])
    expires = _parse_utc(request["expires_at"])
    if recorded >= expires:
        raise _invalid()
    if response is not None and decision["decision"] != response["decision"]:
        raise _invalid()
    return decision


def _validate_consume(
    value: object,
    request: dict[str, object],
    decision: dict[str, object] | None,
    response: dict[str, object] | None,
) -> dict[str, object]:
    consume = _copy_checked_contract("authority-action-consume", value)
    if decision is None or response is None or decision["decision"] != "approve":
        raise _invalid()
    if (
        consume["approval_event_id"] != decision["event_id"]
        or consume["action_id"] != request["action"]["action_id"]
        or consume["action_sha256"] != request["action_sha256"]
        or consume["expires_at"] != request["expires_at"]
    ):
        raise _invalid()
    _require_event_id(consume["event_id"])
    consumed_at = _parse_utc(consume["consumed_at"])
    decision_at = _parse_utc(decision["recorded_at"])
    expires = _parse_utc(request["expires_at"])
    if consumed_at < decision_at or consumed_at >= expires:
        raise _invalid()
    return consume


def _validate_attempt_row(value: object, *, event_type: str) -> dict[str, object]:
    detached, _ = _canonical(value)
    if type(detached) is not dict:
        raise _invalid()
    try:
        checked = _attempt_receipts._validate_event(detached)
    except (
        _attempt_receipts.ReceiptError,
        ContractError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        raise _invalid() from None
    if checked.get("event_type") != event_type:
        raise _invalid()
    return _detach(checked)  # type: ignore[return-value]


def _validate_lineage(
    request: dict[str, object],
    response: dict[str, object] | None,
    decision: dict[str, object] | None,
    consume: dict[str, object] | None,
    started: dict[str, object] | None,
    finished: dict[str, object] | None,
) -> None:
    action = request["action"]
    action_id = action["action_id"]
    digest = request["action_sha256"]
    expires = _parse_utc(request["expires_at"])

    if decision is not None:
        if response is None:
            raise _invalid()
        if decision["decision"] == "reject" and (
            consume is not None or started is not None or finished is not None
        ):
            raise _invalid()
    if consume is not None:
        if decision is None or response is None or decision["decision"] != "approve":
            raise _invalid()
    if started is not None:
        if consume is None or decision is None or response is None or decision["decision"] != "approve":
            raise _invalid()
        if (
            started["action_id"] != action_id
            or started["action_sha256"] != digest
            or started["consume_event_id"] != consume["event_id"]
        ):
            raise _invalid()
        if _parse_utc(started["recorded_at"]) < _parse_utc(consume["consumed_at"]):
            raise _invalid()
    if finished is not None:
        if started is None:
            raise _invalid()
        if (
            finished["action_id"] != action_id
            or finished["action_sha256"] != digest
            or finished["consume_event_id"] != consume["event_id"]  # type: ignore[union-attr]
            or finished["attempt_started_event_id"] != started["event_id"]
        ):
            raise _invalid()
        try:
            _attempt_receipts._validate_history([started, finished])
        except (
            _attempt_receipts.ReceiptError,
            ContractError,
            TypeError,
            ValueError,
            RecursionError,
        ):
            raise _invalid() from None
    if decision is not None:
        # The response was checked before the decision, but retain the exact
        # action/request binding here so a future refactor cannot weaken it.
        if response is None or response["action_id"] != action_id or response["action_sha256"] != digest:
            raise _invalid()
    if decision is not None and _parse_utc(decision["recorded_at"]) >= expires:
        raise _invalid()


def _derive_receipt(
    request: dict[str, object],
    consume: dict[str, object] | None,
    started: dict[str, object] | None,
    finished: dict[str, object] | None,
    executor_ref: dict[str, object],
) -> dict[str, object] | None:
    if finished is None:
        return None
    if consume is None or started is None:
        raise _invalid()
    try:
        result = build_external_action_receipt(
            started,
            finished,
            expected_action_id=request["action"]["action_id"],
            expected_action_sha256=request["action_sha256"],
            expected_consume_event_id=consume["event_id"],
            executor_ref=executor_ref,
        )
    except (ContractError, TypeError, ValueError, RecursionError):
        raise _invalid() from None
    return _detach(result)  # type: ignore[return-value]


def _derive_missing(values: dict[str, object | None]) -> list[str]:
    return [name for name in _MISSING_KEYS if values[name] is None]


def _bundle_without_hash(bundle: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in bundle.items() if key != "bundle_sha256"}


def _build_bundle(
    request: dict[str, object],
    response: dict[str, object] | None,
    decision: dict[str, object] | None,
    consume: dict[str, object] | None,
    started: dict[str, object] | None,
    finished: dict[str, object] | None,
    executor_ref: dict[str, object],
    receipt: dict[str, object] | None,
    verification: dict[str, object] | None,
) -> dict[str, object]:
    sources: dict[str, object | None] = {
        "request": request,
        "response": response,
        "decision": decision,
        "consume": consume,
        "started": started,
        "finished": finished,
        "executor_ref": executor_ref,
        "verification": verification,
    }
    source_sha256 = {
        name: None if sources[name] is None else _hash(sources[name]) for name in _SOURCE_KEYS
    }
    bundle: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "request": _detach(request),
        "response": _detach(response),
        "decision": _detach(decision),
        "consume": _detach(consume),
        "started": _detach(started),
        "finished": _detach(finished),
        "executor_ref": _detach(executor_ref),
        "receipt": _detach(receipt),
        "verification": _detach(verification),
        "source_sha256": source_sha256,
        "missing": _derive_missing(sources),
        "bundle_sha256": "",
    }
    try:
        bundle["bundle_sha256"] = _hash(_bundle_without_hash(bundle))
        _bounded_plain(bundle)
    except EvidenceError:
        raise
    except (TypeError, ValueError, RecursionError):
        raise _invalid() from None
    return bundle


def export_evidence(
    request: object,
    *,
    response: object = None,
    decision: object = None,
    consume: object = None,
    started: object = None,
    finished: object = None,
    executor_ref: object,
    verification: object = None,
) -> dict[str, object]:
    """Export one closed, deterministic, detached evidence bundle.

    The function is intentionally data-only.  Every fact is caller-attested;
    no supplied row is treated as proof of Core ledger membership, identity,
    or a real external effect.
    """

    try:
        request_checked = _validate_request(request)
        response_checked = (
            None if response is None else _validate_response(response, request_checked)
        )
        decision_checked = (
            None
            if decision is None
            else _validate_decision(decision, request_checked, response_checked)
        )
        consume_checked = (
            None
            if consume is None
            else _validate_consume(consume, request_checked, decision_checked, response_checked)
        )
        started_checked = (
            None
            if started is None
            else _validate_attempt_row(started, event_type="attempt_started")
        )
        finished_checked = (
            None
            if finished is None
            else _validate_attempt_row(finished, event_type="attempt_finished")
        )
        executor_checked = _validate_executor_ref(executor_ref)
        _validate_lineage(
            request_checked,
            response_checked,
            decision_checked,
            consume_checked,
            started_checked,
            finished_checked,
        )
        receipt_checked = _derive_receipt(
            request_checked,
            consume_checked,
            started_checked,
            finished_checked,
            executor_checked,
        )
        verification_checked: dict[str, object] | None
        if verification is None:
            verification_checked = None
        else:
            if receipt_checked is None:
                raise _invalid()
            verification_checked = _copy_checked_contract(
                "external-action-verification.v0", verification
            )
            try:
                _, verification_checked = validate_receipt_verification_binding(
                    receipt_checked,
                    verification_checked,
                    expected_action_id=request_checked["action"]["action_id"],
                    expected_action_sha256=request_checked["action_sha256"],
                )
            except (ContractError, TypeError, ValueError, RecursionError):
                raise _invalid() from None
            verification_checked = _detach(verification_checked)  # type: ignore[assignment]
        return _build_bundle(
            request_checked,
            response_checked,
            decision_checked,
            consume_checked,
            started_checked,
            finished_checked,
            executor_checked,
            receipt_checked,
            verification_checked,
        )
    except EvidenceError:
        raise
    except (ContractError, TypeError, ValueError, RecursionError, OverflowError):
        raise _invalid() from None


def _validate_bundle_shape(bundle: object) -> dict[str, object]:
    detached, _ = _canonical(bundle)
    if type(detached) is not dict or set(detached) != _TOP_LEVEL_KEYS:
        raise _invalid()
    if detached.get("schema_version") != SCHEMA_VERSION:
        raise _invalid()
    for key in ("request", "executor_ref"):
        if detached.get(key) is None:
            raise _invalid()
    if type(detached.get("source_sha256")) is not dict:
        raise _invalid()
    source_hashes = detached["source_sha256"]
    if set(source_hashes) != set(_SOURCE_KEYS):
        raise _invalid()
    for name in _SOURCE_KEYS:
        digest = source_hashes[name]
        if digest is not None:
            _require_digest(digest)
    missing = detached.get("missing")
    if type(missing) is not list or any(type(item) is not str for item in missing):
        raise _invalid()
    if missing != [name for name in _MISSING_KEYS if detached.get(name) is None]:
        raise _invalid()
    bundle_digest = detached.get("bundle_sha256")
    _require_digest(bundle_digest)
    if _hash(_bundle_without_hash(detached)) != bundle_digest:
        raise _invalid()
    return detached  # type: ignore[return-value]


def inspect_evidence(bundle: object) -> dict[str, object]:
    """Validate and inspect a bundle without authenticating its source.

    The returned projection is deliberately finite and carries the same
    non-authorizing qualification even when every detached row is internally
    self-consistent.
    """

    try:
        checked = _validate_bundle_shape(bundle)
        rebuilt = export_evidence(
            checked["request"],
            response=checked["response"],
            decision=checked["decision"],
            consume=checked["consume"],
            started=checked["started"],
            finished=checked["finished"],
            executor_ref=checked["executor_ref"],
            verification=checked["verification"],
        )
        if _canonical(rebuilt)[1] != _canonical(checked)[1]:
            raise _invalid()
        receipt = checked["receipt"]
        verification = checked["verification"]
        return {
            "schema_version": "host-evidence-inspection.v0",
            "bundle_sha256": checked["bundle_sha256"],
            "provenance": "caller-attested",
            "source_status": "source-unverified",
            "authority": False,
            "source_authenticated": False,
            "external_effect_verified": False,
            "missing": list(checked["missing"]),
            "receipt_status": None if receipt is None else receipt["status"],
            "verification_status": (
                None if verification is None else verification["status"]
            ),
        }
    except EvidenceError:
        raise
    except (ContractError, TypeError, ValueError, RecursionError, OverflowError):
        raise _invalid() from None


def _escape_display_summary(value: object) -> str:
    """Return bounded, single-line text for caller-supplied evidence context."""

    if type(value) is not str or not value:
        return "unavailable"
    pieces: list[str] = []
    for char in value[:_MAX_DISPLAY_SUMMARY_CHARS]:
        code = ord(char)
        if char == "\\":
            pieces.append("\\\\")
        elif char == "\n":
            pieces.append("\\n")
        elif char == "\r":
            pieces.append("\\r")
        elif char == "\t":
            pieces.append("\\t")
        elif code < 0x20 or 0x7F <= code <= 0x9F:
            pieces.append(f"\\x{code:02x}")
        elif _unicodedata.category(char).startswith("C") or _unicodedata.category(char) in {
            "Zl",
            "Zp",
        }:
            if code <= 0xFFFF:
                pieces.append(f"\\u{code:04x}")
            else:
                pieces.append(f"\\U{code:08x}")
        else:
            pieces.append(char)
    return "".join(pieces) or "unavailable"


def summarize_evidence(bundle: object) -> str:
    """Render one validated bundle as bounded human-facing Terminal text.

    This is a display-only view over the existing detached bundle.  It does
    not add fields to the JSON inspection/MCP contracts and does not read a
    ledger, authenticate a source, or initiate recovery.
    """

    try:
        checked = _validate_bundle_shape(bundle)
        # Reuse the existing full projection check so human text has exactly
        # the same validation boundary as the default JSON/MCP inspection.
        inspect_evidence(checked)
        decision = checked["decision"]
        consume = checked["consume"]
        receipt = checked["receipt"]
        verification = checked["verification"]
        missing = checked["missing"]

        if decision is None:
            approval_text = "missing"
        elif decision["decision"] == "approve":
            approval_text = "recorded (approve)"
        else:
            approval_text = "rejected (decision recorded)"
        authority_text = "recorded" if consume is not None else "missing"
        receipt_status = "missing" if receipt is None else str(receipt["status"])
        verification_status = (
            "missing" if verification is None else str(verification["status"])
        )

        if verification is None and receipt is not None and receipt["status"] == "SUCCESS":
            conclusion = "executor-reported success only"
        elif verification is None:
            conclusion = "evidence incomplete"
        elif verification["status"] == "MISMATCH":
            conclusion = "independent verification mismatch"
        elif verification["status"] == "UNKNOWN":
            conclusion = "independent verification unknown"
        else:
            conclusion = "independent verification recorded"

        # The closed bundle carries only observed_state.summary.  The
        # structured reason code lives in verify_merge_pr's sibling evidence
        # object and is intentionally unavailable on this stdin-only route.
        reason = "unavailable"
        action = checked["request"]["action"]
        parameters = action["execution_parameters"]
        target_text = (
            f"target: action_id={action['action_id']}; operation={action['operation']}; "
            f"repository={parameters['repository']}; pull_request={parameters['pull_request']}; "
            f"expected_head_sha={parameters['expected_head_sha']}; "
            f"expected_base={parameters['expected_base']}; merge_method={parameters['merge_method']}"
        )

        if verification is None:
            next_check = (
                "inspect an existing independent Verification record for this action, "
                "if one exists"
            )
        else:
            next_check = (
                "inspect the referenced read-back evidence for the recorded reason code"
            )

        missing_text = "none" if not missing else ", ".join(str(item) for item in missing)
        lines = [
            f"bundle: {checked['bundle_sha256']}",
            target_text,
            f"approval: {approval_text}",
            f"authority use: {authority_text}",
            f"receipt: {receipt_status}",
            f"verification: {verification_status}",
            f"missing: {missing_text}",
            f"conclusion: {conclusion}",
            f"reason: {reason}",
            *(
                [
                    "reported observation summary: "
                    + _escape_display_summary(verification["observed_state"]["summary"])
                ]
                if verification is not None
                else []
            ),
            "provenance: caller-attested",
            "source: source-unverified",
            "authority: false",
            "source authenticated: false",
            "external effect verified: false",
            "record basis: status and conclusion are caller-reported records; source authentication unavailable",
            "absence claim: missing decision, authority-use, or Verification records do not prove that those events were absent",
            f"next read-only check: {next_check}",
            "recovery: no re-execution; no reconsume",
        ]
        return "\n".join(lines) + "\n"
    except EvidenceError:
        raise
    except (ContractError, TypeError, ValueError, RecursionError, OverflowError):
        raise _invalid() from None


def decode_json(raw: bytes | str) -> object:
    """Decode one bounded strict JSON document for the CLI surface."""

    if type(raw) is bytes:
        if len(raw) > MAX_ENCODED_BYTES:
            raise _invalid()
        source = raw
    elif type(raw) is str:
        try:
            source = raw.encode("utf-8")
        except UnicodeEncodeError:
            raise _invalid() from None
        if len(source) > MAX_ENCODED_BYTES:
            raise _invalid()
    else:
        raise _invalid()
    try:
        value = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except EvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise _invalid() from None
    _bounded_plain(value)
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise _invalid()


__all__ = [
    "EvidenceError",
    "EvidenceValidationError",
    "MAX_CONTAINER_ENTRIES",
    "MAX_DEPTH",
    "MAX_ENCODED_BYTES",
    "MAX_NODES",
    "MAX_STRING_BYTES",
    "SCHEMA_VERSION",
    "decode_json",
    "export_evidence",
    "inspect_evidence",
]
