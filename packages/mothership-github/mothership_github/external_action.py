"""Opt-in, non-authorizing projection of closed GitHub attempt records."""

from __future__ import annotations

import copy

from mothership.contracts import (
    ContractError,
    canonical_json_sha256,
    validate_external_action_receipt,
)

from . import executor, receipts


_INVALID = "invalid GitHub attempt receipt input"


def _snapshot(value: object) -> object:
    """Copy only the plain JSON types used by the closed attempt contracts."""

    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _snapshot(item) for key, item in value.items()}
    raise ContractError(_INVALID)


def build_external_action_receipt(
    started: object,
    finished: object,
    *,
    expected_action_id: str,
    expected_action_sha256: str,
    expected_consume_event_id: str,
    executor_ref: object,
) -> dict[str, object]:
    """Project a matching terminal attempt pair into the Core receipt contract.

    Expected identities are caller-attested: obtain them from trusted execution
    context, not from the records being checked. This function does not access
    the authority ledger or prove durable consumption, executor authenticity,
    or external truth. SUCCESS remains an executor-local report.

    Retain exactly {"started": started, "finished": finished} as the referenced
    evidence object. No evidence storage or resolution is performed here. Only
    Core's bundled schema-resource reads are needed; no execution or retries.
    """

    try:
        for value, pattern in (
            (expected_action_id, receipts._ACTION_ID),
            (expected_action_sha256, receipts._DIGEST),
            (expected_consume_event_id, receipts._EVENT_ID),
        ):
            if type(value) is not str or pattern.fullmatch(value) is None:
                raise ContractError(_INVALID)
        if any(type(value) is not dict for value in (started, finished, executor_ref)):
            raise ContractError(_INVALID)
        start = receipts._validate_event(_snapshot(started))
        finish = receipts._validate_event(_snapshot(finished))
        ref = _snapshot(executor_ref)
        if start["event_type"] != "attempt_started" or finish["event_type"] != "attempt_finished":
            raise ContractError(_INVALID)
        receipts._validate_history([start, finish])
        if (
            start["action_id"] != expected_action_id
            or start["action_sha256"] != expected_action_sha256
            or start["consume_event_id"] != expected_consume_event_id
        ):
            raise ContractError(_INVALID)

        status = "UNKNOWN"
        if finish["outcome"] == "success":
            status = "SUCCESS"
        elif finish["outcome"] == "failure":
            outcome, _ = executor._normalized_observation(finish["observation"])
            if outcome == "failure":
                status = "FAILED"

        result = {
            "schema_version": "external-action-receipt.v0",
            "action_id": start["action_id"],
            "action_sha256": start["action_sha256"],
            "executor_ref": ref,
            "started_at": start["recorded_at"],
            "finished_at": finish["recorded_at"],
            "status": status,
            "executor_observation_ref": {
                "ref_id": "github-attempt:" + start["event_id"],
                "sha256": canonical_json_sha256({"started": start, "finished": finish}),
            },
        }
        return copy.deepcopy(validate_external_action_receipt(result))
    except (ContractError, receipts.ReceiptError, TypeError, ValueError, RecursionError):
        raise ContractError(_INVALID) from None


__all__ = ["build_external_action_receipt"]
