"""Offline inspection of the reference consumer's existing finite JSONL.

These saved events are not a portable review bundle. Missing authority rows
stay missing. No path resolution, observation, action issuance or recovery is
performed here, and structural consistency does not authenticate the source.
"""

from __future__ import annotations

import hashlib

from mothership.contracts import (
    ContractError, canonical_json_sha256, validate_external_action_receipt,
    validate_receipt_verification_binding,
)
from mothership_github.external_action import build_external_action_receipt
from orchestration.lib.action_authority import action_sha256

from .evidence import (
    EvidenceError, MAX_ENCODED_BYTES, _SHA40, _bounded_plain,
    _escape_display_summary, _invalid, _parse_utc, _readback_guidance,
    _require_digest, _validate_readback_for_action, decode_json,
)


_EVENTS = ("frozen_action", "execution_result", "verification_result")
_SAVED_RESULT_SCHEMA = "mothership.reference-result.v1"
_V1_FIELDS = frozenset({"saved_result_schema", "action_id", "action_sha256"})
_EXECUTION = frozenset({"event", "status", "mutation_attempted", "paths"})
_FACTS = frozenset({"http_status", "merged", "merge_commit_sha"})
_VERIFICATION = frozenset({
    "event", "execution_status", "status", "source_pair", "receipt",
    "verification", "evidence", "paths",
})


def _version(rows: list[dict[str, object]]) -> str:
    """Select one closed row format before any row-specific validation."""

    if not rows:
        return "legacy"
    first_has_marker = "saved_result_schema" in rows[0]
    if first_has_marker:
        if rows[0].get("saved_result_schema") != _SAVED_RESULT_SCHEMA:
            raise _invalid()
        version = "v1"
    else:
        version = "legacy"
    for row in rows:
        has_marker = "saved_result_schema" in row
        if has_marker and row.get("saved_result_schema") != _SAVED_RESULT_SCHEMA:
            raise _invalid()
        if has_marker != (version == "v1"):
            raise _invalid()
    return version


def _v1_identity(
    row: dict[str, object], expected_action_id: object, expected_action_sha256: object
) -> None:
    if type(row.get("saved_result_schema")) is not str:
        raise _invalid()
    if type(row.get("action_id")) is not str or type(row.get("action_sha256")) is not str:
        raise _invalid()
    if row["action_id"] != expected_action_id or row["action_sha256"] != expected_action_sha256:
        raise _invalid()


def _without_v1_fields(row: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key not in _V1_FIELDS}


def _validate_v1_execution(
    row: dict[str, object], expected_action_id: object, expected_action_sha256: object
) -> None:
    if set(row) not in {
        _EXECUTION | _V1_FIELDS,
        _EXECUTION | _FACTS | _V1_FIELDS,
    }:
        raise _invalid()
    _v1_identity(row, expected_action_id, expected_action_sha256)
    _execution(_without_v1_fields(row))


def _validate_v1_verification(
    frozen: dict[str, object],
    execution: dict[str, object],
    row: dict[str, object],
    expected_action_id: object,
    expected_action_sha256: object,
) -> object:
    if set(row) not in {
        _VERIFICATION | _V1_FIELDS,
        _VERIFICATION | {"reason"} | _V1_FIELDS,
    }:
        raise _invalid()
    _v1_identity(row, expected_action_id, expected_action_sha256)
    return _verification(frozen, execution, _without_v1_fields(row))


def _rows(raw: bytes | str) -> tuple[bytes, list[dict[str, object]]]:
    if type(raw) is str:
        raw = raw.encode("utf-8")
    if type(raw) is not bytes or len(raw) > MAX_ENCODED_BYTES:
        raise _invalid()
    if not raw:
        return raw, []
    # The producer writes one complete LF-terminated line per saved event.
    # Never salvage a prefix by silently discarding a torn final write.
    if not raw.endswith(b"\n"):
        raise _invalid()
    lines = raw[:-1].split(b"\n")
    if not 1 <= len(lines) <= len(_EVENTS):
        raise _invalid()
    rows = [decode_json(line) for line in lines]
    _bounded_plain(rows)  # Aggregate depth/node/byte bounds, not just per-line.
    for index, row in enumerate(rows):
        if type(row) is not dict or row.get("event") != _EVENTS[index]:
            raise _invalid()
    return raw, rows


def _paths(value: object) -> None:
    if type(value) is not dict or set(value) != {"authority", "attempts"}:
        raise _invalid()
    if any(type(item) is not str or not item for item in value.values()):
        raise _invalid()
    # Opaque hints only. Do not open, normalize, or print these input paths.


def _execution(row: dict[str, object]) -> None:
    _paths(row.get("paths"))
    if set(row) == _EXECUTION:
        if row["status"] != "reconciliation_required" or row["mutation_attempted"] != "unknown":
            raise _invalid()
        return
    if set(row) != _EXECUTION | _FACTS or row["mutation_attempted"] is not True:
        raise _invalid()
    status = row["status"]
    if type(status) is not str or status not in {"success", "failure", "reconciliation_required"}:
        raise _invalid()
    http = row["http_status"]
    merged, sha = row["merged"], row["merge_commit_sha"]
    if type(http) is not int or not (http == 0 or 100 <= http <= 599):
        raise _invalid()
    if merged is not None and type(merged) is not bool:
        raise _invalid()
    if sha is not None and (type(sha) is not str or _SHA40.fullmatch(sha) is None):
        raise _invalid()
    if status == "success" and not (http == 200 and merged is True and sha is not None):
        raise _invalid()
    if status == "failure" and (merged is True or sha is not None):
        raise _invalid()


def _verification(frozen, execution, row):
    status = row.get("status")
    if status == "unavailable":
        if set(row) != _VERIFICATION | {"reason"}:
            raise _invalid()
        reason = row["reason"]
        if type(reason) is not str or reason not in {"receipt_unavailable", "verification_unavailable"}:
            raise _invalid()
        if row["verification"] is not None or row["evidence"] is not None:
            raise _invalid()
        if reason == "receipt_unavailable":
            if row["receipt"] is not None or row["source_pair"] is not None:
                raise _invalid()
    elif type(status) is not str or status not in {"CONFIRMED", "MISMATCH", "UNKNOWN"} or set(row) != _VERIFICATION:
        raise _invalid()
    if row["execution_status"] != execution["status"] or row["paths"] != execution["paths"]:
        raise _invalid()

    receipt = row["receipt"]
    if receipt is None:
        if status != "unavailable" or row["reason"] != "receipt_unavailable":
            raise _invalid()
        return None
    checked_receipt = validate_external_action_receipt(receipt)
    action, digest = frozen["action"], frozen["action_sha256"]
    if checked_receipt["action_id"] != action["action_id"] or checked_receipt["action_sha256"] != digest:
        raise _invalid()
    pair = row["source_pair"]
    if type(pair) is not dict or set(pair) != {"started", "finished"}:
        raise _invalid()
    # Compare an ALREADY SUPPLIED Receipt. Never fill an absent Receipt or row.
    comparison = build_external_action_receipt(
        pair["started"], pair["finished"], expected_action_id=action["action_id"],
        expected_action_sha256=digest, expected_consume_event_id=pair["started"]["consume_event_id"],
        executor_ref=checked_receipt["executor_ref"],
    )
    if canonical_json_sha256(comparison) != canonical_json_sha256(checked_receipt):
        raise _invalid()
    if _FACTS <= set(execution):
        finished = pair["finished"]
        if execution["status"] != finished["outcome"] or any(
            execution[key] != finished["observation"][key] for key in _FACTS
        ):
            raise _invalid()
    if status == "unavailable":
        if row["reason"] != "verification_unavailable":
            raise _invalid()
        return None
    _, verification = validate_receipt_verification_binding(
        checked_receipt, row["verification"], expected_action_id=action["action_id"],
        expected_action_sha256=digest,
    )
    if verification["status"] != status:
        raise _invalid()
    return _validate_readback_for_action(action, digest, verification, row["evidence"])


def inspect_saved_result(
    raw: bytes | str, *, expected_action_sha256: object = None
) -> dict[str, object]:
    """Validate all supplied saved events before returning a detached summary."""
    try:
        if expected_action_sha256 is not None:
            expected_action_sha256 = _require_digest(expected_action_sha256)
        encoded, rows = _rows(raw)
        version = _version(rows)
        action = execution = verification = sidecar = None
        checked_action_sha256 = None
        if rows:
            frozen = rows[0]
            expected_frozen = {"event", "action", "action_sha256", "expires_at"}
            if version == "v1":
                expected_frozen.add("saved_result_schema")
            if set(frozen) != expected_frozen:
                raise _invalid()
            if action_sha256(frozen["action"]) != frozen["action_sha256"]:
                raise _invalid()
            _parse_utc(frozen["expires_at"])
            # Each call has already decoded its own detached plain JSON rows.
            action = frozen["action"]
            checked_action_sha256 = frozen["action_sha256"]
        if len(rows) >= 2:
            execution = rows[1]
            if version == "v1":
                _validate_v1_execution(execution, action["action_id"], rows[0]["action_sha256"])
            else:
                _execution(execution)
        if len(rows) == 3:
            verification = rows[2]
            if version == "v1":
                sidecar = _validate_v1_verification(
                    rows[0], execution, verification,
                    action["action_id"], rows[0]["action_sha256"],
                )
            else:
                sidecar = _verification(rows[0], execution, verification)
        if expected_action_sha256 is not None and (
            action is None or checked_action_sha256 != expected_action_sha256
        ):
            raise _invalid()
        receipt = None if verification is None else verification["receipt"]
        observed = None if verification is None else verification["verification"]
        binding = (
            "action ID and digest match (structural only; source-unverified)"
            if version == "v1" and execution is not None
            else "not supplied"
            if version == "v1"
            else "positional only; no action/run ID in execution row"
        )
        view = {
            "format": "reference-result-jsonl", "input_sha256": hashlib.sha256(encoded).hexdigest(),
            "record_count": len(rows), "action": action,
            "execution_status": None if execution is None else execution["status"],
            "receipt_status": None if receipt is None else receipt["status"],
            "verification_status": None if observed is None else observed["status"],
            "verification_reason": None if verification is None else verification.get("reason"),
            "readback_reason": None if sidecar is None else sidecar["reason"],
            "observed_at": None if observed is None else observed["observed_at"],
            "missing": ["review_request", "decision", "consume"] +
                (["source_pair", "receipt"] if receipt is None else []) +
                (["verification"] if observed is None else []),
            "provenance": "caller-attested", "source_status": "source-unverified",
            "authority": False, "source_authenticated": False, "external_effect_verified": False,
            "execution_summary_binding": binding,
        }
        if version == "v1":
            view["saved_result_schema"] = _SAVED_RESULT_SCHEMA
        return view
    except EvidenceError:
        raise
    except (ContractError, KeyError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise _invalid() from None


def summarize_saved_result(
    raw: bytes | str, *, expected_action_sha256: object = None
) -> str:
    """Explain recorded layers and missing evidence, without observing an effect."""
    view = inspect_saved_result(raw, expected_action_sha256=expected_action_sha256)
    action = view["action"]
    target = "target: unavailable in supplied input"
    if action is not None:
        params = action["execution_parameters"]
        target = (
            f"target: action_id={action['action_id']}; operation={action['operation']}; "
            f"repository={params['repository']}; pull_request={params['pull_request']}; "
            f"expected_head_sha={params['expected_head_sha']}; expected_base={params['expected_base']}; "
            f"merge_method={params['merge_method']}"
        )
    receipt, verification = view["receipt_status"], view["verification_status"]
    if receipt is None:
        conclusion = "outcome unknown; supplied summary is not a bound completion record"
        next_check = "inspect explicitly retained existing authority and attempt records for this action"
    elif verification is None:
        conclusion = "executor Receipt recorded; independent confirmation not established by this input"
        next_check = "inspect an existing independent Verification and its referenced evidence, if available"
    elif verification == "CONFIRMED":
        conclusion = "independent observation recorded; not proof of this attempt's causation or current state"
        next_check = _readback_guidance(view["readback_reason"])
    else:
        conclusion = "independent observation " + verification + "; completion not established"
        next_check = _readback_guidance(view["readback_reason"])
    binding = view["execution_summary_binding"]
    if binding == "positional only; no action/run ID in execution row":
        linkage = "execution linkage: unlabelled execution summary; sequence only, not authenticated run association"
    elif binding == "not supplied":
        linkage = "execution linkage: not supplied"
    else:
        linkage = "execution linkage: " + binding + "; not an authenticated run association"
    return "\n".join([
        f"saved result: {view['input_sha256']}", target,
        "provided records (caller-reported)",
        "approval: not supplied by this saved format", "authority use: not supplied by this saved format",
        f"consumer execution report: {view['execution_status'] or 'not supplied'}",
        f"receipt: {receipt or 'not supplied'} (executor report; independent observation is separate)",
        f"verification: {verification or 'not supplied'} (recorded observation)",
        "missing: " + ", ".join(view["missing"]),
        f"reason: {_escape_display_summary(view['readback_reason'] or view['verification_reason'])}",
        f"observed at (caller-reported): {view['observed_at'] or 'not supplied'}",
        "readback evidence hash binding: " + ("match (structural)" if verification else "not supplied"),
        linkage,
        "conclusion: " + conclusion,
        "inspection scope (structural only)", "provenance: caller-attested", "source: source-unverified",
        "authority: false", "source authenticated: false", "external effect verified: false",
        "absence of a record is not proof of absence of an operation or confirmation",
        "saved records do not establish successful process exit or record freshness",
        "next read-only check: " + next_check, "input paths: opaque hints; never opened",
        "recovery: no re-execution; no reconsume",
    ]) + "\n"


__all__ = ["inspect_saved_result", "summarize_saved_result"]
