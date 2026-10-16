"""Tests for the bounded, non-authorizing evidence projection."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from mothership.action_authority import freeze_action
from mothership.action_review import build_review_request
from mothership.contracts import ContractError, canonical_json_bytes, canonical_json_sha256
from mothership_github import receipts
from orchestration.lib import action_authority_ledger

from mothership_adapters.evidence import (
    EvidenceError,
    MAX_DEPTH,
    MAX_ENCODED_BYTES,
    export_evidence,
    inspect_evidence,
)
from mothership_adapters import evidence as evidence_module


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

    def verification(self, *, status: str, summary: str) -> dict[str, object]:
        receipt = self.full()["receipt"]
        return {
            "schema_version": "external-action-verification.v0",
            "action_id": self.action.action["action_id"],
            "action_sha256": self.action.action_sha256,
            "verification_method": "read_only_external_observation",
            "observed_state": {"summary": summary, "state_sha256": "d" * 64},
            "evidence_refs": [{"ref_id": "observation:synthetic", "sha256": "e" * 64}],
            "observed_at": self.finished["recorded_at"],
            "status": status,
            "receipt_ref": {
                "ref_id": "receipt:" + self.action.action["action_id"],
                "sha256": canonical_json_sha256(receipt),
            },
        }

    def _readback_artifacts(
        self,
        *,
        status: str = "UNKNOWN",
        reason: str = "unmerged_pr",
        state: dict[str, object] | None = None,
        observations: list[dict[str, str]] | None = None,
        transport: str = "default_tokenless",
    ) -> tuple[dict[str, object], dict[str, object]]:
        if state is None:
            state = {"pull_request": None, "commit": None}
        if observations is None:
            observations = []
        sidecar: dict[str, object] = {
            "version": "github-merge-readback.v0",
            "action_id": self.action.action["action_id"],
            "action_sha256": self.action.action_sha256,
            "transport": transport,
            "observations": copy.deepcopy(observations),
            "state": copy.deepcopy(state),
            "reason": reason,
        }
        verification = self.verification(
            status=status, summary=f"synthetic {status.lower()} read-back"
        )
        verification["observed_state"]["state_sha256"] = (
            None
            if state["pull_request"] is None and state["commit"] is None
            else canonical_json_sha256(state)
        )
        sidecar_digest = canonical_json_sha256(sidecar)
        verification["evidence_refs"] = [
            {
                "ref_id": "github-readback:" + sidecar_digest,
                "sha256": sidecar_digest,
            }
        ]
        return self.full(verification=verification), sidecar

    def _rebind_readback_sidecar(
        self,
        bundle: dict[str, object],
        sidecar: dict[str, object],
        *,
        status: str | None = None,
        rebind_state: bool = False,
    ) -> tuple[dict[str, object], dict[str, object]]:
        candidate = copy.deepcopy(sidecar)
        verification = copy.deepcopy(bundle["verification"])
        if status is not None:
            verification["status"] = status
        if rebind_state:
            state = candidate["state"]
            verification["observed_state"]["state_sha256"] = (
                None
                if state["pull_request"] is None and state["commit"] is None
                else canonical_json_sha256(state)
            )
        digest = canonical_json_sha256(candidate)
        verification["evidence_refs"] = [
            {"ref_id": "github-readback:" + digest, "sha256": digest}
        ]
        rebuilt = self.full(
            response=bundle["response"],
            decision=bundle["decision"],
            consume=bundle["consume"],
            started=bundle["started"],
            finished=bundle["finished"],
            executor_ref=bundle["executor_ref"],
            verification=verification,
        )
        return rebuilt, candidate


class EvidenceTests(EvidenceFixture):
    def test_export_and_inspection_preserve_nested_inputs_and_fixture_files(self) -> None:
        bundle, sidecar = self._readback_artifacts()
        inputs = {
            "request": self.request, "response": self.response,
            "decision": self.decision, "consume": self.consume,
            "started": self.started, "finished": self.finished,
            "executor_ref": copy.deepcopy(EXECUTOR_REF),
            "verification": bundle["verification"],
        }
        root = pathlib.Path(self.temp.name)
        for name, value in (("bundle.json", bundle), ("sidecar.json", sidecar)):
            (root / name).write_bytes(canonical_json_bytes(value))
        before_inputs = copy.deepcopy((inputs, bundle, sidecar))
        before_files = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

        exported = export_evidence(**inputs)
        projection = inspect_evidence(bundle)
        evidence_module.summarize_evidence(bundle, readback_evidence=sidecar)
        # A caller may edit outputs; that must not alter retained evidence.
        exported["request"]["host_context"]["scope"].append("synthetic-poison")
        projection["missing"].append("synthetic-poison")

        self.assertEqual(before_inputs, (inputs, bundle, sidecar))
        self.assertEqual(before_files, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})
        self.assertEqual([], inspect_evidence(bundle)["missing"])

    def test_inspection_repeats_independently_of_other_trial_order(self) -> None:
        cases = (
            (self.full(verification=self.verification(status="CONFIRMED", summary="synthetic positive control")), "SUCCESS", "CONFIRMED", []),
            (self.full(finished=None), None, None, ["finished", "verification"]),
            (self.full(verification=self.verification(status="UNKNOWN", summary="synthetic unavailable observation")), "SUCCESS", "UNKNOWN", []),
            (self.full(verification=self.verification(status="MISMATCH", summary="synthetic mismatch")), "SUCCESS", "MISMATCH", []),
            (self.full(consume=None, started=None, finished=None), None, None, ["consume", "started", "finished", "verification"]),
        )
        before = copy.deepcopy(cases)
        texts: dict[int, str] = {}
        for order in (range(len(cases)), reversed(range(len(cases)))):
            for index in order:
                bundle, receipt_status, verification_status, missing = cases[index]
                for repeat in range(2):
                    with self.subTest(case=index, repeat=repeat):
                        result = inspect_evidence(bundle)
                        self.assertEqual(receipt_status, result["receipt_status"])
                        self.assertEqual(verification_status, result["verification_status"])
                        self.assertEqual(missing, result["missing"])
                        self.assertEqual("source-unverified", result["source_status"])
                        for flag in ("authority", "source_authenticated", "external_effect_verified"):
                            self.assertIs(False, result[flag])
                        text = evidence_module.summarize_evidence(bundle)
                        if index in texts:
                            self.assertEqual(texts[index], text)
                        texts[index] = text
        self.assertEqual(before, cases)

    def test_mid_validation_exception_leaves_the_next_inspection_clean(self) -> None:
        bundle = self.full(verification=self.verification(status="CONFIRMED", summary="synthetic positive control"))
        before = copy.deepcopy(bundle)
        before_files = (self.authority_path.read_bytes(), self.receipt_path.read_bytes())
        with mock.patch.object(
            evidence_module, "validate_receipt_verification_binding",
            side_effect=ContractError("synthetic binding interruption"),
        ):
            with self.assertRaises(EvidenceError):
                inspect_evidence(bundle)
        self.assertEqual(before, bundle)
        self.assertEqual(before_files, (self.authority_path.read_bytes(), self.receipt_path.read_bytes()))
        result = inspect_evidence(bundle)
        self.assertEqual("CONFIRMED", result["verification_status"])
        self.assertIs(False, result["external_effect_verified"])
        incomplete = inspect_evidence(self.full(finished=None))
        self.assertIsNone(incomplete["receipt_status"])
        self.assertEqual(["finished", "verification"], incomplete["missing"])

    def test_rejected_substitution_does_not_contaminate_the_next_inspection(self) -> None:
        bundle, sidecar = self._readback_artifacts()
        before = copy.deepcopy((bundle, sidecar))
        expected = evidence_module.summarize_evidence(bundle, readback_evidence=sidecar)
        swapped = copy.deepcopy(sidecar)
        swapped["action_id"] = "act-foreign-trial"
        foreign_bundle, foreign_sidecar = self._rebind_readback_sidecar(bundle, swapped)
        changed_content = copy.deepcopy(sidecar)
        changed_content["reason"] = "merge_confirmed"
        changed_row = copy.deepcopy(bundle)
        changed_row["verification"]["observed_state"]["summary"] = "different schema-valid observation"
        # Rehashing the envelope must not bypass source-row reconstruction.
        changed_row["bundle_sha256"] = canonical_json_sha256(
            {k: v for k, v in changed_row.items() if k != "bundle_sha256"}
        )
        for name, candidate, original in (
            ("foreign-action-even-after-rehash", foreign_bundle, foreign_sidecar),
            ("sidecar-content-hash-mismatch", bundle, changed_content),
            ("source-row-hash-mismatch", changed_row, sidecar),
        ):
            with self.subTest(substitution=name):
                with self.assertRaises(EvidenceError):
                    evidence_module.summarize_evidence(candidate, readback_evidence=original)
                self.assertEqual(expected, evidence_module.summarize_evidence(bundle, readback_evidence=sidecar))
                self.assertEqual("UNKNOWN", inspect_evidence(bundle)["verification_status"])
        self.assertEqual(before, (bundle, sidecar))

    def test_human_summary_without_sidecar_and_explicit_none_match(self) -> None:
        bundle, _sidecar = self._readback_artifacts()
        implicit = evidence_module.summarize_evidence(bundle)
        explicit = evidence_module.summarize_evidence(bundle, readback_evidence=None)
        self.assertEqual(implicit, explicit)
        self.assertIn("structured reason: unavailable in bundle", implicit)
        self.assertIn(
            "compare the referenced evidence's canonical hash with verification.evidence_refs",
            implicit,
        )

    def test_human_summary_with_sidecar_reports_structural_bindings_and_guidance(self) -> None:
        state = {
            "pull_request": {
                "repository": PARAMETERS["repository"],
                "number": PARAMETERS["pull_request"],
                "state": "closed",
                "merged": True,
                "merged_at": "2026-10-13T02:54:10Z",
                "head_sha": "f" * 40,
                "base_ref": PARAMETERS["expected_base"],
                "merge_commit_sha": "c" * 40,
            },
            "commit": {"sha": "c" * 40, "parents": ["a" * 40, "f" * 40]},
        }
        bundle, sidecar = self._readback_artifacts(
            status="MISMATCH",
            reason="head_or_base_mismatch",
            state=state,
            observations=[
                {
                    "endpoint": "pull_request",
                    "started_at": "2026-10-13T02:54:00Z",
                    "finished_at": "2026-10-13T02:54:01Z",
                },
                {
                    "endpoint": "commit",
                    "started_at": "2026-10-13T02:54:02Z",
                    "finished_at": "2026-10-13T02:54:03Z",
                },
            ],
        )
        summary = evidence_module.summarize_evidence(
            bundle, readback_evidence=sidecar
        )
        lines = summary.splitlines()

        self.assertIn(
            "structured reason: head_or_base_mismatch (caller-reported)", lines
        )
        self.assertNotIn("structured reason: unavailable in bundle", lines)
        self.assertNotIn(
            "next read-only check: compare the referenced evidence's canonical hash with verification.evidence_refs",
            lines,
        )
        self.assertIn("readback: structurally valid sidecar (source-unverified)", lines)
        self.assertIn("readback evidence hash binding: match (structural)", lines)
        self.assertIn("readback action binding: match (structural)", lines)
        self.assertIn("readback state hash binding: match (structural)", lines)
        self.assertIn(
            "readback verification method (caller-reported): read_only_external_observation",
            lines,
        )
        self.assertIn("readback transport (caller-reported): default_tokenless", lines)
        self.assertIn(
            "readback reason (caller-reported): head_or_base_mismatch", lines
        )
        self.assertIn(
            "readback observed_at (caller-reported): "
            + str(bundle["verification"]["observed_at"]),
            lines,
        )
        self.assertIn(
            "next read-only check: compare action expected_head_sha/expected_base with retained PR projection; no automatic retry/re-execution/reconsume",
            lines,
        )
        self.assertNotIn("readback guidance:", summary)
        self.assertIn("source: source-unverified", lines)
        self.assertIn(
            "authority: false (this inspection grants no execution permission)", lines
        )
        self.assertIn(
            "external effect verified: false (this inspection does not observe external state)",
            lines,
        )

    def test_human_summary_rejects_sidecar_binding_and_shape_mismatches(self) -> None:
        state = {
            "pull_request": {
                "repository": PARAMETERS["repository"],
                "number": PARAMETERS["pull_request"],
                "state": "closed",
                "merged": True,
                "merged_at": "2026-10-13T02:54:10Z",
                "head_sha": "f" * 40,
                "base_ref": PARAMETERS["expected_base"],
                "merge_commit_sha": "c" * 40,
            },
            "commit": {"sha": "c" * 40, "parents": ["a" * 40, "f" * 40]},
        }
        bundle, sidecar = self._readback_artifacts(
            status="MISMATCH",
            reason="head_or_base_mismatch",
            state=state,
            observations=[
                {
                    "endpoint": "pull_request",
                    "started_at": "2026-10-13T02:54:00Z",
                    "finished_at": "2026-10-13T02:54:01Z",
                }
            ],
        )
        cases: list[tuple[str, dict[str, object], dict[str, object]]] = []
        changed_action = copy.deepcopy(sidecar)
        changed_action["action_id"] = "act-other"
        rebound_bundle, rebound_action = self._rebind_readback_sidecar(
            bundle, changed_action
        )
        cases.append(("action_id_after_ref_rehash", rebound_bundle, rebound_action))
        changed_digest = copy.deepcopy(sidecar)
        changed_digest["action_sha256"] = "0" * 64
        rebound_bundle, rebound_digest = self._rebind_readback_sidecar(
            bundle, changed_digest
        )
        cases.append(("action_sha256_after_ref_rehash", rebound_bundle, rebound_digest))
        changed_state = copy.deepcopy(sidecar)
        changed_state["state"]["commit"]["sha"] = "1" * 40
        rebound_bundle, rebound_state = self._rebind_readback_sidecar(
            bundle, changed_state
        )
        cases.append(("state_hash_after_ref_rehash", rebound_bundle, rebound_state))
        changed_ref = copy.deepcopy(sidecar)
        changed_ref["reason"] = "future_extension_reason"
        cases.append(("sidecar_hash_without_ref_rehash", bundle, changed_ref))
        extra_key = copy.deepcopy(sidecar)
        extra_key["extra"] = True
        cases.append(("extra_key", bundle, extra_key))
        bad_reason = copy.deepcopy(sidecar)
        bad_reason["reason"] = "Not a bounded code"
        cases.append(("reason", bundle, bad_reason))
        bad_observation = copy.deepcopy(sidecar)
        bad_observation["observations"][0]["started_at"] = "not-a-time"
        cases.append(("timestamp", bundle, bad_observation))

        for name, candidate_bundle, candidate in cases:
            with self.subTest(name=name):
                with self.assertRaises(EvidenceError):
                    evidence_module.summarize_evidence(
                        candidate_bundle, readback_evidence=candidate
                    )

    def test_human_summary_rejects_noncanonical_utc_timestamp_syntax(self) -> None:
        bundle, sidecar = self._readback_artifacts(
            observations=[
                {
                    "endpoint": "pull_request",
                    "started_at": "2026-10-13T02:54:00Z",
                    "finished_at": "2026-10-13T02:54:01Z",
                }
            ]
        )
        malformed_timestamps = (
            ("month", "2026-1-13T02:54:00Z"),
            ("day", "2026-10-3T02:54:00Z"),
            ("hour", "2026-10-13T2:54:00Z"),
            ("minute", "2026-10-13T02:4:00Z"),
            ("second", "2026-10-13T02:54:0Z"),
            ("lowercase_z", "2026-10-13T02:54:00z"),
        )
        for name, timestamp in malformed_timestamps:
            with self.subTest(name=name):
                candidate = copy.deepcopy(sidecar)
                candidate["observations"][0]["started_at"] = timestamp
                candidate_bundle, candidate = self._rebind_readback_sidecar(
                    bundle, candidate
                )
                with self.assertRaises(EvidenceError):
                    evidence_module.summarize_evidence(
                        candidate_bundle, readback_evidence=candidate
                    )

    def test_human_summary_accepts_unknown_reason_and_clock_rollback_without_rechecking_semantics(
        self,
    ) -> None:
        bundle, sidecar = self._readback_artifacts()
        unknown = copy.deepcopy(sidecar)
        unknown["reason"] = "future_extension_reason"
        unknown_bundle, unknown = self._rebind_readback_sidecar(bundle, unknown)
        unknown_summary = evidence_module.summarize_evidence(
            unknown_bundle, readback_evidence=unknown
        )
        self.assertIn(
            "readback reason (caller-reported): future_extension_reason",
            unknown_summary,
        )
        self.assertIn(
            "next read-only check: check provenance and recorded status; no automatic retry/re-execution/reconsume",
            unknown_summary,
        )
        self.assertIn("verification: UNKNOWN", unknown_summary)

        rollback = copy.deepcopy(sidecar)
        rollback["reason"] = "clock_rollback"
        rollback["observations"] = [
            {
                "endpoint": "pull_request",
                "started_at": "2026-10-13T03:00:00Z",
                "finished_at": "2026-10-13T02:00:00Z",
            }
        ]
        rollback_bundle, rollback = self._rebind_readback_sidecar(
            bundle, rollback, status="UNKNOWN"
        )
        rollback_summary = evidence_module.summarize_evidence(
            rollback_bundle, readback_evidence=rollback
        )
        self.assertIn("verification: UNKNOWN", rollback_summary)
        self.assertIn("readback reason (caller-reported): clock_rollback", rollback_summary)
        self.assertIn(
            "next read-only check: review retained timing records; do not infer freshness; no automatic retry/re-execution/reconsume",
            rollback_summary,
        )

    def test_human_summary_guidance_preserves_reason_and_named_fields(self) -> None:
        cases = (
            ("ambiguous_merge_time", "receipt started_at"),
            ("preexisting_merge", "retained PR merged_at"),
            ("receipt_not_finished", "receipt finished_at"),
            ("head_or_base_mismatch", "expected_head_sha/expected_base"),
            ("merge_topology_mismatch", "commit parents"),
            ("invalid_pr_observation", "PR visibility"),
            ("invalid_commit_observation", "merge_commit_sha"),
            ("unmerged_pr", "state/merged/merged_at"),
            ("merge_confirmed", "source provenance"),
        )
        for reason, fragment in cases:
            with self.subTest(reason=reason):
                bundle, sidecar = self._readback_artifacts(reason=reason)
                summary = evidence_module.summarize_evidence(
                    bundle, readback_evidence=sidecar
                )
                self.assertIn(
                    f"structured reason: {reason} (caller-reported)", summary
                )
                self.assertIn(fragment, summary)
                self.assertIn(
                    "no automatic retry/re-execution/reconsume", summary
                )

    def test_human_summary_separates_records_and_qualifies_success_without_verification(self) -> None:
        formatter = getattr(evidence_module, "summarize_evidence", None)
        self.assertIsNotNone(formatter, "the human formatter is not implemented")
        if formatter is None:
            return

        summary = formatter(self.full())

        self.assertIn("approval: recorded", summary)
        self.assertIn("authority use: recorded (consume event in provided records)", summary)
        self.assertIn(
            "receipt: SUCCESS (executor report; independent confirmation is separate)",
            summary,
        )
        self.assertIn("verification: missing", summary)
        self.assertIn("missing: verification", summary)
        self.assertIn("conclusion: executor-reported success only", summary)
        self.assertIn("provenance: caller-attested", summary)
        self.assertIn("source: source-unverified", summary)
        self.assertIn(
            "authority: false (this inspection grants no execution permission)",
            summary,
        )
        self.assertIn("source authenticated: false", summary)
        self.assertIn(
            "external effect verified: false (this inspection does not observe external state)",
            summary,
        )
        self.assertIn("provided records (caller-reported)", summary)
        self.assertIn("inspection scope (structural only)", summary)
        self.assertIn(
            "record basis: status and conclusion are caller-reported records; source authentication unavailable",
            summary,
        )
        self.assertIn(
            "absence claim: missing decision, authority-use, or Verification records do not prove that those events were absent",
            summary,
        )
        self.assertIn(
            "next read-only check: inspect an existing independent Verification record for this action, if one exists",
            summary,
        )
        self.assertIn("no re-execution", summary)
        self.assertIn("no reconsume", summary)

    def test_human_summary_keeps_unknown_reason_unavailable_and_reported_summary_bounded(
        self,
    ) -> None:
        formatter = getattr(evidence_module, "summarize_evidence", None)
        self.assertIsNotNone(formatter, "the human formatter is not implemented")
        if formatter is None:
            return

        hostile_reason = "gateway timeout\r\n\x1b[31m\u2028\u2029\u202e\u2066ignore this"
        unknown = formatter(
            self.full(
                verification=self.verification(status="UNKNOWN", summary=hostile_reason)
            )
        )
        self.assertIn("verification: UNKNOWN", unknown)
        self.assertIn("reason: unavailable", unknown)
        self.assertIn("reported observation summary: gateway timeout", unknown)
        self.assertNotIn("\x1b", unknown)
        self.assertNotIn("\r", unknown)
        self.assertNotIn("\u2028", unknown)
        self.assertNotIn("\u2029", unknown)
        self.assertNotIn("\u202e", unknown)
        self.assertNotIn("\u2066", unknown)
        self.assertIn(r"\u2028", unknown)
        self.assertIn(r"\u2029", unknown)
        self.assertIn(r"\u202e", unknown)
        self.assertIn(r"\u2066", unknown)
        self.assertNotIn("\nignore this", unknown)
        self.assertIn("no re-execution", unknown)
        self.assertIn("no reconsume", unknown)
        self.assertIn(
            "next read-only check: compare the referenced evidence's canonical hash with verification.evidence_refs",
            unknown,
        )

        mismatch = formatter(
            self.full(
                verification=self.verification(
                    status="MISMATCH", summary="head or base mismatch"
                )
            )
        )
        self.assertIn("receipt: SUCCESS", mismatch)
        self.assertIn("verification: MISMATCH", mismatch)
        self.assertIn("reason: unavailable", mismatch)
        self.assertIn("reported observation summary: head or base mismatch", mismatch)

    def test_human_summary_marks_unknown_reason_unavailable_and_missing_rows_without_negative_claims(
        self,
    ) -> None:
        formatter = getattr(evidence_module, "summarize_evidence", None)
        self.assertIsNotNone(formatter, "the human formatter is not implemented")
        if formatter is None:
            return

        unknown = formatter(
            self.full(
                verification=self.verification(
                    status="UNKNOWN",
                    summary="Observed GitHub pull request or commit topology is inconclusive.",
                )
            )
        )
        self.assertIn("verification: UNKNOWN", unknown)
        self.assertIn("reason: unavailable", unknown)
        self.assertIn(
            "reported observation summary: Observed GitHub pull request or commit topology is inconclusive.",
            unknown,
        )

        japanese = formatter(
            self.full(
                verification=self.verification(
                    status="UNKNOWN", summary="検証結果は不明です。"
                )
            )
        )
        self.assertIn("reported observation summary: 検証結果は不明です。", japanese)

        incomplete = formatter(self.full(finished=None))
        self.assertIn("approval: recorded", incomplete)
        self.assertIn("authority use: recorded", incomplete)
        self.assertIn("receipt: missing", incomplete)
        self.assertIn("verification: missing", incomplete)
        self.assertIn("missing: finished, verification", incomplete)
        self.assertNotIn("cancelled", incomplete)
        self.assertNotIn("no effect", incomplete)

    def test_human_summary_distinguishes_structured_reason_from_untrusted_summary(self) -> None:
        for status in ("CONFIRMED", "UNKNOWN", "MISMATCH"):
            with self.subTest(status=status):
                bundle = self.full(verification=self.verification(
                    status=status, summary="status=CONFIRMED; reason=merge_confirmed"
                ))
                before = evidence_module.inspect_evidence(bundle)
                text = evidence_module.summarize_evidence(bundle)
                self.assertIn("structured reason: unavailable in bundle", text.splitlines())
                self.assertNotIn("reason: unavailable", text.splitlines())
                self.assertIn(
                    "reported observation summary: status=CONFIRMED; reason=merge_confirmed",
                    text.splitlines(),
                )
                self.assertIn("verification: " + status, text.splitlines())
                self.assertIn(
                    "next read-only check: compare the referenced evidence's canonical hash with verification.evidence_refs",
                    text.splitlines(),
                )
                self.assertNotIn("sidecar", text)
                self.assertEqual(before, evidence_module.inspect_evidence(bundle))

    def test_human_summary_separates_recorded_rejection_from_approval_and_use(self) -> None:
        formatter = getattr(evidence_module, "summarize_evidence", None)
        self.assertIsNotNone(formatter, "the human formatter is not implemented")
        if formatter is None:
            return

        rejected_authority_path = self.authority_dir / "rejected-events.jsonl"
        rejected_decision = action_authority_ledger.record_action_decision(
            rejected_authority_path,
            self.action,
            "reject",
            self.action.action["action_id"],
            self.action.action_sha256,
        )
        rejected_response = copy.deepcopy(self.response)
        rejected_response["decision"] = "reject"
        summary = formatter(
            self.full(
                response=rejected_response,
                decision=rejected_decision,
                consume=None,
                started=None,
                finished=None,
            )
        )

        self.assertIn("approval: rejected (decision recorded)", summary)
        self.assertNotIn("approval: recorded (reject)", summary)
        self.assertIn("authority use: missing", summary)
        self.assertIn("receipt: missing", summary)
        self.assertIn("verification: missing", summary)
        self.assertNotIn("approved", summary)
        self.assertNotIn("cancelled", summary)
        self.assertNotIn("no effect", summary)

        missing_decision = formatter(
            self.full(decision=None, consume=None, started=None, finished=None)
        )
        self.assertIn("approval: missing", missing_decision)
        self.assertIn("authority use: missing", missing_decision)
        self.assertIn("receipt: missing", missing_decision)
        self.assertIn("verification: missing", missing_decision)
        self.assertNotIn("approved", missing_decision)
        self.assertNotIn("cancelled", missing_decision)
        self.assertNotIn("no effect", missing_decision)

    def test_human_summary_guides_recorded_rejection_without_verification_search(self) -> None:
        rejected_authority_path = self.authority_dir / "rejected-guidance-events.jsonl"
        rejected_decision = action_authority_ledger.record_action_decision(
            rejected_authority_path,
            self.action,
            "reject",
            self.action.action["action_id"],
            self.action.action_sha256,
        )
        rejected_response = copy.deepcopy(self.response)
        rejected_response["decision"] = "reject"

        summary = evidence_module.summarize_evidence(
            self.full(
                response=rejected_response,
                decision=rejected_decision,
                consume=None,
                started=None,
                finished=None,
            )
        )

        self.assertIn("provided records (caller-reported)", summary)
        self.assertIn("inspection scope (structural only)", summary)
        self.assertIn("conclusion: rejection recorded for this request", summary)
        self.assertIn(
            "rejection scope: post-execution Verification is not a completion requirement for a reject decision; this is not proof of global event absence",
            summary,
        )
        self.assertIn(
            "next read-only check: review the recorded rejection; no independent Verification search is needed for this request",
            summary,
        )
        self.assertNotIn(
            "next read-only check: inspect an existing independent Verification record",
            summary,
        )

    def test_human_summary_guides_incomplete_execution_to_source_records(self) -> None:
        bundle = self.full(finished=None)
        before_projection = evidence_module.inspect_evidence(bundle)
        before_authority = self.authority_path.read_bytes()
        before_receipt = self.receipt_path.read_bytes()

        summary = evidence_module.summarize_evidence(bundle)

        self.assertIn("provided records (caller-reported)", summary)
        self.assertIn("inspection scope (structural only)", summary)
        self.assertIn("conclusion: execution records incomplete; outcome unknown", summary)
        self.assertIn("authority use: recorded (consume event in provided records)", summary)
        self.assertIn(
            "authority: false (this inspection grants no execution permission)",
            summary,
        )
        self.assertIn(
            "external effect verified: false (this inspection does not observe external state)",
            summary,
        )
        self.assertIn(
            "next read-only check: inspect existing authority and attempt records before seeking independent Verification",
            summary,
        )
        self.assertNotIn(
            "next read-only check: inspect an existing independent Verification record",
            summary,
        )
        self.assertEqual(before_projection, evidence_module.inspect_evidence(bundle))
        self.assertEqual(before_authority, self.authority_path.read_bytes())
        self.assertEqual(before_receipt, self.receipt_path.read_bytes())

    def test_human_summary_has_no_ledger_side_effect(self) -> None:
        formatter = getattr(evidence_module, "summarize_evidence", None)
        self.assertIsNotNone(formatter, "the human formatter is not implemented")
        if formatter is None:
            return

        before_authority = self.authority_path.read_bytes()
        before_receipt = self.receipt_path.read_bytes()
        formatter(self.full())
        self.assertEqual(before_authority, self.authority_path.read_bytes())
        self.assertEqual(before_receipt, self.receipt_path.read_bytes())

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
        self.assertEqual(
            ("bundle", "readback_evidence"),
            tuple(inspect.signature(evidence_module.summarize_evidence).parameters),
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
