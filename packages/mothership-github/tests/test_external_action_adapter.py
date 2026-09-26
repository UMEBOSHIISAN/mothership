from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
import unittest
from unittest.mock import patch

from mothership.contracts import ContractError, validate_external_action_receipt
from orchestration.lib import action_authority_ledger


ACTION_ID = "act-adapter-001"
DIGEST = "a" * 64
CONSUME_ID = "event-" + "3" * 32
EXECUTOR_REF = {"ref_id": "executor:synthetic", "sha256": "b" * 64}


def attempt_pair(outcome="success", http_status=200, merged=True, sha="c" * 40):
    started = {
        "schema_version": "github-execution-attempt.v1",
        "event_type": "attempt_started",
        "event_id": "event-" + "1" * 32,
        "action_id": ACTION_ID,
        "action_sha256": DIGEST,
        "consume_event_id": CONSUME_ID,
        "recorded_at": "2026-09-26T00:00:00Z",
    }
    finished = {
        **started,
        "event_type": "attempt_finished",
        "event_id": "event-" + "2" * 32,
        "attempt_started_event_id": started["event_id"],
        "outcome": outcome,
        "observation": {"http_status": http_status, "merged": merged, "merge_commit_sha": sha},
        "recorded_at": "2026-09-26T00:00:01Z",
    }
    return started, finished


class ExternalActionAdapterTests(unittest.TestCase):
    def build(self, pair=None, **overrides):
        try:
            from mothership_github.external_action import build_external_action_receipt
        except ImportError:
            self.fail("receipt conversion adapter is not implemented")
        expected = dict(
            expected_action_id=ACTION_ID,
            expected_action_sha256=DIGEST,
            expected_consume_event_id=CONSUME_ID,
            executor_ref=copy.deepcopy(EXECUTOR_REF),
        )
        expected.update(overrides)
        return build_external_action_receipt(*(attempt_pair() if pair is None else pair), **expected)

    def test_exact_projection_and_public_core_validation(self):
        start, finish = attempt_pair()
        evidence_digest = hashlib.sha256(json.dumps(
            {"started": start, "finished": finish}, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        receipt = self.build((start, finish))
        self.assertEqual({
            "schema_version": "external-action-receipt.v0",
            "action_id": ACTION_ID, "action_sha256": DIGEST,
            "executor_ref": EXECUTOR_REF,
            "started_at": "2026-09-26T00:00:00Z",
            "finished_at": "2026-09-26T00:00:01Z",
            "status": "SUCCESS",
            "executor_observation_ref": {
                "ref_id": "github-attempt:event-" + "1" * 32,
                "sha256": evidence_digest,
            },
        }, receipt)
        self.assertEqual(receipt, validate_external_action_receipt(receipt))

    def test_validated_outcomes_preserve_uncertainty(self):
        cases = [
            ("success", 200, True, "c" * 40, "SUCCESS"),
            ("failure", 409, None, None, "FAILED"),
            ("reconciliation_required", 200, True, "c" * 40, "UNKNOWN"),
            ("reconciliation_required", 409, None, None, "UNKNOWN"),
        ] + [("failure", status, None, None, "UNKNOWN") for status in (0, 503, 302, 200)]
        for outcome, status, merged, sha, want in cases:
            with self.subTest(outcome=outcome, http=status):
                self.assertEqual(want, self.build(attempt_pair(outcome, status, merged, sha))["status"])

    def test_inconsistent_observation_or_unknown_fields_reject(self):
        for outcome, status, merged, sha in (
            ("success", 503, None, None), ("failure", 409, True, None),
            ("failure", 409, None, "c" * 40), ("success", True, True, "c" * 40),
            ("success", 200, True, "C" * 40), ("success", 99, True, "c" * 40),
        ):
            with self.subTest(outcome=outcome, status=status, merged=merged, sha=sha):
                with self.assertRaises(ContractError):
                    self.build(attempt_pair(outcome, status, merged, sha))
        for index, field, value in ((0, "extra", True), (1, "schema_version", "v2"),
                                    (1, "event_type", "attempt_started")):
            pair = attempt_pair()
            pair[index][field] = value
            with self.subTest(index=index, field=field), self.assertRaises(ContractError):
                self.build(pair)
        start, finish = attempt_pair()
        finish["observation"]["extra"] = True
        with self.assertRaises(ContractError):
            self.build((start, finish))
        start, finish = attempt_pair()
        start["action"] = start.pop("action_id")
        with self.assertRaises(ContractError):
            self.build((start, finish))

    def test_missing_swapped_or_foreign_records_reject(self):
        start, finish = attempt_pair()
        for pair in ((start, None), (None, finish), (finish, start), ([], finish), (start, [])):
            with self.subTest(pair=pair), self.assertRaises(ContractError):
                self.build(pair)

    def test_start_finish_linkage_is_exact(self):
        for key, value in (
            ("attempt_started_event_id", "event-" + "4" * 32),
            ("event_id", "event-" + "1" * 32),
            ("action_id", "act-other"), ("action_sha256", "d" * 64),
            ("consume_event_id", "event-" + "4" * 32),
        ):
            start, finish = attempt_pair()
            finish[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.build((start, finish))

    def test_trusted_expectations_reject_foreign_pair_even_when_pair_agrees(self):
        for key, value in (("action_id", "act-other"), ("action_sha256", "d" * 64),
                           ("consume_event_id", "event-" + "4" * 32)):
            start, finish = attempt_pair()
            start[key] = finish[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.build((start, finish))

    def test_expected_values_are_strict_and_diagnostics_do_not_echo_inputs(self):
        for key in ("expected_action_id", "expected_action_sha256", "expected_consume_event_id"):
            for value in (None, True, 123, [], "INPUT_MARKER", "A" * 64):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ContractError) as cm:
                        self.build(**{key: value})
                    self.assertNotIn("INPUT_MARKER", str(cm.exception))

    def test_real_dates_order_and_equal_timestamps(self):
        for date in ("2026-02-30T00:00:00Z", "2026-09-25T23:59:59Z", "2026-09-26T00:00:00+00:00"):
            start, finish = attempt_pair()
            finish["recorded_at"] = date
            with self.subTest(date=date), self.assertRaises(ContractError):
                self.build((start, finish))
        start, finish = attempt_pair()
        finish["recorded_at"] = start["recorded_at"]
        receipt = self.build((start, finish))
        self.assertEqual(receipt["started_at"], receipt["finished_at"])

    def test_executor_reference_is_closed(self):
        for ref in (None, [], {"ref_id": "executor:x"}, {**EXECUTOR_REF, "extra": True},
                    {**EXECUTOR_REF, "ref_id": "INPUT_MARKER/private"},
                    {**EXECUTOR_REF, "sha256": "bad"}):
            with self.subTest(ref=ref):
                with self.assertRaises(ContractError) as cm:
                    self.build(executor_ref=ref)
                self.assertNotIn("INPUT_MARKER", str(cm.exception))

    def test_canonical_digest_is_order_independent_and_binds_both_rows(self):
        start, finish = attempt_pair()
        original = self.build((start, finish))["executor_observation_ref"]["sha256"]
        reverse_finish = dict(reversed(list(finish.items())))
        reverse_finish["observation"] = dict(reversed(list(finish["observation"].items())))
        self.assertEqual(original, self.build((dict(reversed(list(start.items()))), reverse_finish))
                         ["executor_observation_ref"]["sha256"])
        for index, date in ((0, "2026-09-25T23:59:59Z"), (1, "2026-09-26T00:00:02Z")):
            pair = attempt_pair()
            pair[index]["recorded_at"] = date
            self.assertNotEqual(original, self.build(pair)["executor_observation_ref"]["sha256"])

    def test_inputs_and_returned_nested_references_are_isolated(self):
        start, finish = attempt_pair()
        ref = copy.deepcopy(EXECUTOR_REF)
        before = copy.deepcopy((start, finish, ref))
        receipt = self.build((start, finish), executor_ref=ref)
        self.assertEqual(before, (start, finish, ref))
        expected = copy.deepcopy(receipt)
        start["action_id"] = "act-other"
        finish["observation"]["merged"] = False
        ref["ref_id"] = "executor:other"
        self.assertEqual(expected, receipt)
        receipt["executor_ref"]["ref_id"] = "executor:output-change"
        self.assertEqual("executor:other", ref["ref_id"])

    def test_long_action_id_keeps_observation_reference_bounded(self):
        start, finish = attempt_pair()
        start["action_id"] = finish["action_id"] = "act-" + "a" * 300
        receipt = self.build((start, finish), expected_action_id=start["action_id"])
        self.assertEqual(start["action_id"], receipt["action_id"])
        self.assertLessEqual(len(receipt["executor_observation_ref"]["ref_id"]), 256)

    def test_projected_receipt_cannot_be_an_authority_ledger_event(self):
        receipt = self.build()
        with self.assertRaises(action_authority_ledger.ActionEventValidationError):
            action_authority_ledger._validated_event(receipt)

    def test_conversion_never_uses_effectful_helpers_or_clock(self):
        targets = (
            "mothership_github.executor.consume_action",
            "mothership_github.receipts.record_attempt_started",
            "mothership_github.receipts.record_attempt_finished",
            "mothership_github.receipts._utc_now",
            "orchestration.lib.action_authority_ledger._locked_ledger",
            "urllib.request.urlopen", "socket.socket", "subprocess.Popen", "time.time",
        )
        with ExitStack() as stack:
            for target in targets:
                stack.enter_context(patch(target, side_effect=AssertionError("unexpected effect")))
            self.assertEqual("SUCCESS", self.build()["status"])
            self.assertEqual(self.build(), self.build())


if __name__ == "__main__":
    unittest.main()
