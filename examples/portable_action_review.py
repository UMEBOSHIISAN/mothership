"""Offline reference host: portable review -> real Core/companion -> evidence.

All decisions here are SIMULATED. No host product, human authentication or real
GitHub transport is used. Run from a source checkout with both packages on
PYTHONPATH. A production host must guard the actual effect boundary itself;
the unchanged companion executor has no host-context callback.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

from mothership.action_authority import (
    ActionAuthorityError, ActionLedgerError, freeze_action, record_action_decision,
)
from mothership.action_review import build_review_request, validate_review_response
from mothership.contracts import canonical_json_sha256, validate_receipt_verification_binding
from mothership_github.executor import execute_action_merge_pr
from mothership_github.external_action import build_external_action_receipt


PARAMETERS = dict(repository="example/repository", pull_request=7,
                  expected_head_sha="a" * 40, expected_base="main", merge_method="merge")
CONTEXT = dict(host_id="offline-example", session_id="session-demo", actor_id="operator-demo",
               runtime_generation="generation-1", scope=["github.merge_pr"])


class SyntheticTransport:
    """Only count calls and return fixed synthetic observations."""

    def __init__(self):
        self.gets = 0
        self.puts = 0

    def get_pull_request(self, repository, pull_request):
        self.gets += 1
        return dict(http_status=200, state="open", merged=False,
                    head_sha="a" * 40, base_ref="main")

    def merge_pull_request(self, **parameters):
        self.puts += 1
        return dict(http_status=200, merged=True, merge_commit_sha="b" * 40)


def response_for(request):
    """Explicitly SIMULATED approval; a real host obtains its human's decision."""
    return dict(schema_version="authority-action-review-response.v0",
                request_id=request["request_id"], request_sha256=request["request_sha256"],
                action_id=request["action"]["action_id"], action_sha256=request["action_sha256"],
                decision="approve")


def run_reviewed_merge(action, expected_request, response, current_context,
                       authority_path, attempts_path, transport):
    """Reference sequence, not a runtime adapter or an effect-time fence.

    The caller retains the original action and expected_request. It supplies a
    fresh host-owned context after its pause. Context can still change inside
    preflight/consume; this example does not close that later race.
    """
    decision = validate_review_response(action, expected_request, response,
                                        current_host_context=current_context)
    approval = record_action_decision(authority_path, action, decision["decision"],
                                     decision["action_id"], decision["action_sha256"])
    if decision["decision"] == "reject":
        return {"status": "rejected"}
    result = execute_action_merge_pr(authority_path, attempts_path, action,
                                    approval["event_id"], transport)
    receipt = build_external_action_receipt(
        result["attempt_started"], result["attempt_finished"],
        expected_action_id=decision["action_id"], expected_action_sha256=decision["action_sha256"],
        expected_consume_event_id=result["consume_event"]["event_id"],
        executor_ref={"ref_id": "executor:offline-review", "sha256": "c" * 64})
    verification = dict(
        schema_version="external-action-verification.v0", action_id=decision["action_id"],
        action_sha256=decision["action_sha256"], verification_method="read_only_external_observation",
        observed_state={"summary": "Offline example: no external state observed.", "state_sha256": None},
        evidence_refs=[], observed_at=result["attempt_finished"]["recorded_at"], status="UNKNOWN",
        receipt_ref={"ref_id": "receipt:" + decision["action_id"], "sha256": canonical_json_sha256(receipt)})
    receipt, verification = validate_receipt_verification_binding(
        receipt, verification, expected_action_id=decision["action_id"],
        expected_action_sha256=decision["action_sha256"])
    return {"status": result["status"], "receipt": receipt, "verification": verification}


def run_demo():
    with tempfile.TemporaryDirectory(prefix="mothership-review-") as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        authority, attempts = root / "authority.jsonl", root / "attempts.jsonl"
        # One issuance per isolated demo, never reconstructed from request JSON.
        action = freeze_action("act-portable-demo", "github.merge_pr", dict(PARAMETERS))
        expected = build_review_request(action, request_id="review-demo", host_context=CONTEXT)
        response = response_for(expected)
        transport = SyntheticTransport()
        blocked = []
        for field in CONTEXT:
            resumed_context = copy.deepcopy(CONTEXT)
            resumed_context[field] = [] if field == "scope" else "changed"
            try:
                run_reviewed_merge(action, expected, response, resumed_context,
                                   authority, attempts, transport)
            except ActionAuthorityError:
                blocked.append(field)
            else:
                raise AssertionError("changed context passed the reference host check")
        assert not authority.exists() and not attempts.exists()
        assert transport.gets == transport.puts == 0
        result = run_reviewed_merge(action, expected, response, copy.deepcopy(CONTEXT),
                                    authority, attempts, transport)
        try:
            run_reviewed_merge(action, expected, response, copy.deepcopy(CONTEXT),
                               authority, attempts, transport)
        except ActionLedgerError:
            replay = "blocked"
        else:
            raise AssertionError("a second consume was accepted")
        assert transport.puts == 1
        return dict(mode="offline", simulated_human_response=True,
                    context_drift_blocked=blocked, replay=replay, fake_puts=transport.puts,
                    receipt_status=result["receipt"]["status"],
                    verification_status=result["verification"]["status"])


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, sort_keys=True))
