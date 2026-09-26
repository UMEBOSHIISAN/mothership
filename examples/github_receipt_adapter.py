#!/usr/bin/env python3
"""Synthetic receipt/verification binding only: no ledger or external effects."""

from __future__ import annotations

import copy

from mothership.contracts import (
    ContractError,
    canonical_json_sha256,
    validate_receipt_verification_binding,
)
from mothership_github.external_action import build_external_action_receipt


def main() -> int:
    # Fixed synthetic context, not identities derived from untrusted inputs.
    # Real callers must establish their own trusted context; comparison here
    # does not prove an authority ledger ever contained a consume event.
    action_id = "act-adapter-example"
    action_digest = "a" * 64
    consume_id = "event-" + "3" * 32
    started = {
        "schema_version": "github-execution-attempt.v1",
        "event_type": "attempt_started",
        "event_id": "event-" + "1" * 32,
        "action_id": action_id,
        "action_sha256": action_digest,
        "consume_event_id": consume_id,
        "recorded_at": "2026-09-26T00:00:00Z",
    }
    finished = {
        **started,
        "event_type": "attempt_finished",
        "event_id": "event-" + "2" * 32,
        "attempt_started_event_id": started["event_id"],
        "recorded_at": "2026-09-26T00:00:01Z",
        "outcome": "reconciliation_required",
        "observation": {"http_status": 0, "merged": None, "merge_commit_sha": None},
    }
    receipt = build_external_action_receipt(
        started, finished,
        expected_action_id=action_id,
        expected_action_sha256=action_digest,
        expected_consume_event_id=consume_id,
        executor_ref={"ref_id": "executor:synthetic", "sha256": "b" * 64},
    )
    # This is a separate SYNTHETIC fixture, not independent read-back evidence.
    verification = {
        "schema_version": "external-action-verification.v0",
        "action_id": action_id,
        "action_sha256": action_digest,
        "verification_method": "read_only_external_observation",
        "observed_state": {"summary": "Synthetic: external state was not read.", "state_sha256": None},
        "evidence_refs": [],
        "observed_at": "2026-09-26T00:00:02Z",
        "status": "UNKNOWN",
        "receipt_ref": {
            "ref_id": "receipt:" + action_id,
            "sha256": canonical_json_sha256(receipt),
        },
    }
    expected = {"expected_action_id": action_id, "expected_action_sha256": action_digest}
    bound_receipt, bound_verification = validate_receipt_verification_binding(
        receipt, verification, **expected,
    )
    if bound_receipt["status"] != "UNKNOWN" or bound_verification["status"] != "UNKNOWN":
        raise RuntimeError("binding unexpectedly promoted an unknown result")
    altered = copy.deepcopy(verification)
    altered["receipt_ref"]["sha256"] = "d" * 64
    for observation, context in (
        (verification, {**expected, "expected_action_sha256": "e" * 64}),
        (altered, expected),
    ):
        try:
            validate_receipt_verification_binding(receipt, observation, **context)
        except ContractError:
            continue
        raise RuntimeError("binding unexpectedly accepted a digest mismatch")
    print("SYNTHETIC ONLY")
    print("binding: accepted")
    print("mismatch: rejected")
    print("receipt status: UNKNOWN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
