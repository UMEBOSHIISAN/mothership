"""Tests for the bounded, non-authorizing evidence projection."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import pathlib
import tempfile
import unittest

from mothership.action_authority import freeze_action
from mothership.action_review import build_review_request
from mothership.contracts import canonical_json_bytes, canonical_json_sha256
from mothership_github import receipts
from orchestration.lib import action_authority_ledger

from mothership_adapters.evidence import (
    EvidenceError,
    MAX_DEPTH,
    MAX_ENCODED_BYTES,
    export_evidence,
    inspect_evidence,
)


PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}
EXECUTOR_REF = {"ref_id": "executor:synthetic", "sha256": "b" * 64}


class EvidenceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mothership-evidence-")
        root = pathlib.Path(self.temp.name)
        self.authority_dir = root / "authority"
        self.receipt_dir = root / "receipts"
        self.authority_dir.mkdir(mode=0o700)
        self.receipt_dir.mkdir(mode=0o700)
        self.authority_path = self.authority_dir / "events.jsonl"
        self.receipt_path = self.receipt_dir / "events.jsonl"
        self.action = freeze_action(
            "act-evidence-test", "github.merge_pr", copy.deepcopy(PARAMETERS)
        )
        self.request = build_review_request(
            self.action,
            request_id="request-evidence-test",
            host_context={
                "host_id": "host-test",
                "session_id": "session-test",
                "actor_id": "actor-test",
                "runtime_generation": "generation-test",
                "scope": ["github.merge_pr"],
            },
        )
        self.response = {
            "schema_version": "authority-action-review-response.v0",
            "request_id": self.request["request_id"],
            "request_sha256": self.request["request_sha256"],
            "action_id": self.request["action"]["action_id"],
            "action_sha256": self.request["action_sha256"],
            "decision": "approve",
        }
        self.decision = action_authority_ledger.record_action_decision(
            self.authority_path,
            self.action,
            "approve",
            self.action.action["action_id"],
            self.action.action_sha256,
        )
        self.consume, self.consumed_action = action_authority_ledger.consume_action(
            self.authority_path,
            self.decision["event_id"],
            self.action.action["action_id"],
            self.action.action_sha256,
        )
        self.started = receipts.record_attempt_started(
            self.receipt_path,
            self.authority_path,
            self.consume,
            self.action.action,
        )
        self.finished = receipts.record_attempt_finished(
            self.receipt_path,
            self.started,
            "success",
            {"http_status": 200, "merged": True, "merge_commit_sha": "c" * 40},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def full(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "request": copy.deepcopy(self.request),
            "response": copy.deepcopy(self.response),
            "decision": copy.deepcopy(self.decision),
            "consume": copy.deepcopy(self.consume),
            "started": copy.deepcopy(self.started),
            "finished": copy.deepcopy(self.finished),
            "executor_ref": copy.deepcopy(EXECUTOR_REF),
        }
        values.update(overrides)
        return export_evidence(**values)  # type: ignore[arg-type]


class EvidenceTests(EvidenceFixture):
    def test_public_signatures_are_exact(self) -> None:
        self.assertEqual(
            (
                "request",
                "response",
                "decision",
                "consume",
                "started",
                "finished",
                "executor_ref",
                "verification",
            ),
            tuple(inspect.signature(export_evidence).parameters),
        )
        self.assertEqual(("bundle",), tuple(inspect.signature(inspect_evidence).parameters))

    def test_repeated_export_is_byte_deterministic_and_closed(self) -> None:
        first = self.full()
        second = self.full()
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual(
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
            },
            set(first),
        )
        self.assertEqual([], first["missing"][:-1])
        self.assertEqual(["verification"], first["missing"][-1:])
        self.assertIsNone(first["verification"])
        self.assertEqual("SUCCESS", first["receipt"]["status"])

    def test_source_hashes_cover_exact_rows_and_bundle_hash_excludes_only_itself(self) -> None:
        bundle = self.full()
        self.assertEqual(
            canonical_json_sha256(self.request), bundle["source_sha256"]["request"]
        )
        self.assertEqual(
            canonical_json_sha256(self.decision), bundle["source_sha256"]["decision"]
        )
        without_hash = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
        self.assertEqual(canonical_json_sha256(without_hash), bundle["bundle_sha256"])

    def test_missing_finish_never_invents_receipt(self) -> None:
        bundle = self.full(finished=None)
        self.assertIsNone(bundle["receipt"])
        self.assertEqual(["finished", "verification"], bundle["missing"])
        summary = inspect_evidence(bundle)
        self.assertIsNone(summary["receipt_status"])
        self.assertIsNone(summary["verification_status"])

    def test_verification_is_separate_and_binds_derived_receipt(self) -> None:
        receipt = self.full()["receipt"]
        verification = {
            "schema_version": "external-action-verification.v0",
            "action_id": self.action.action["action_id"],
            "action_sha256": self.action.action_sha256,
            "verification_method": "read_only_external_observation",
            "observed_state": {"summary": "synthetic mismatch", "state_sha256": "d" * 64},
            "evidence_refs": [{"ref_id": "observation:synthetic", "sha256": "e" * 64}],
            "observed_at": self.finished["recorded_at"],
            "status": "MISMATCH",
            "receipt_ref": {
                "ref_id": "receipt:" + self.action.action["action_id"],
                "sha256": canonical_json_sha256(receipt),
            },
        }
        bundle = self.full(verification=verification)
        self.assertEqual("SUCCESS", bundle["receipt"]["status"])
        self.assertEqual("MISMATCH", bundle["verification"]["status"])
        self.assertEqual([], bundle["missing"])
        summary = inspect_evidence(bundle)
        self.assertEqual("SUCCESS", summary["receipt_status"])
        self.assertEqual("MISMATCH", summary["verification_status"])

    def test_changed_request_digest_and_foreign_consume_reject(self) -> None:
        changed_request = copy.deepcopy(self.request)
        changed_request["request_sha256"] = "0" * 64
        with self.assertRaises(EvidenceError):
            self.full(request=changed_request)
        foreign_consume = copy.deepcopy(self.consume)
        foreign_consume["action_sha256"] = "f" * 64
        with self.assertRaises(EvidenceError):
            self.full(consume=foreign_consume)

    def test_unknown_fields_and_contradictory_outcome_reject(self) -> None:
        extra = copy.deepcopy(self.request)
        extra["extra"] = True
        with self.assertRaises(EvidenceError):
            self.full(request=extra)
        contradictory = copy.deepcopy(self.finished)
        contradictory["outcome"] = "failure"
        contradictory["observation"] = {
            "http_status": 200,
            "merged": True,
            "merge_commit_sha": "c" * 40,
        }
        with self.assertRaises(EvidenceError):
            self.full(finished=contradictory)

    def test_bounds_and_strict_json_fail_closed(self) -> None:
        oversized = copy.deepcopy(self.request)
        oversized["host_context"]["host_id"] = "x" * 65_537
        with self.assertRaises(EvidenceError):
            self.full(request=oversized)
        deep = "leaf"
        for _ in range(MAX_DEPTH + 2):
            deep = [deep]
        with self.assertRaises(EvidenceError):
            self.full(executor_ref={"ref_id": "executor:test", "sha256": "b" * 64, "deep": deep})
        from mothership_adapters.evidence import decode_json

        with self.assertRaises(EvidenceError):
            decode_json(b'{"a":1,"a":2}')
        with self.assertRaises(EvidenceError):
            decode_json(b"{" + b'\"x\":' + b'\"a\"' * MAX_ENCODED_BYTES)
        with self.assertRaises(EvidenceError):
            decode_json((b"{" + b'\"x\":NaN}'))

    def test_export_does_not_write_existing_ledgers(self) -> None:
        before_authority = self.authority_path.read_bytes()
        before_receipt = self.receipt_path.read_bytes()
        self.full()
        self.assertEqual(before_authority, self.authority_path.read_bytes())
        self.assertEqual(before_receipt, self.receipt_path.read_bytes())

    def test_decision_and_consume_at_expiry_reject_but_late_finish_is_valid(self) -> None:
        for row, field in (("decision", "recorded_at"), ("consume", "consumed_at")):
            value = copy.deepcopy(getattr(self, row))
            value[field] = self.request["expires_at"]
            with self.subTest(row=row), self.assertRaises(EvidenceError):
                self.full(**{row: value}, started=None, finished=None)
        late = copy.deepcopy(self.finished)
        late["recorded_at"] = self.request["expires_at"]
        self.assertEqual("SUCCESS", self.full(finished=late)["receipt"]["status"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
