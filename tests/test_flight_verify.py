from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from orchestration.lib.canonical import canonical_json_bytes


REQUIRED_STAGES = (
    "intent",
    "scope",
    "decision",
    "approval",
    "execution",
    "result",
    "verification",
    "persistence",
)
REGISTRY_SHA256 = "cb5000ca90a1395c5efdf7362b5d9928fea70915a96af3c3b10542a7abbf0a14"
SCOPE_SHA256 = "b" * 64
RESULT_SHA256 = "c" * 64
OTHER_SHA256 = "d" * 64


def event(stage: str, number: int) -> dict[str, object]:
    return {
        "schema_version": "mothership.flight-event.v1",
        "event_id": f"event-{stage}",
        "run_id": "run-complete-001",
        "event_type": "record_recorded",
        "stage": stage,
        "occurred_at": f"2026-08-12T00:00:0{number}Z",
        "producer_class": "synthetic",
        "tool_id": None,
        "predecessor_event_ids": [] if number == 0 else [f"event-{REQUIRED_STAGES[number - 1]}"],
        "subject": {
            "storage": "external",
            "protocol_kind": "frontdoor-task",
            "schema_version": "intake.v0",
            "location": f"refs/{stage}.json",
            "sha256": "a" * 64,
        },
        "scope_sha256": None,
        "action_class": "none",
        "authority_effect": False,
        "execution_effect": False,
        "outcome_status": "recorded",
        "redaction": {"profile": "metadata-only", "removed_fields": 0},
        "extension": None,
    }


def complete_events() -> list[dict[str, object]]:
    events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
    by_stage = {item["stage"]: item for item in events}
    for stage in ("scope", "approval", "execution"):
        by_stage[stage]["scope_sha256"] = SCOPE_SHA256
        by_stage[stage]["action_class"] = "file_write"
    by_stage["approval"]["outcome_status"] = "approved"
    by_stage["approval"]["authority_effect"] = True
    by_stage["execution"]["outcome_status"] = "started"
    by_stage["execution"]["execution_effect"] = True
    for stage, outcome in (("result", "succeeded"), ("verification", "verified"), ("persistence", "persisted")):
        by_stage[stage]["outcome_status"] = outcome
        by_stage[stage]["subject"] = dict(by_stage[stage]["subject"], sha256=RESULT_SHA256)  # type: ignore[arg-type]
    return events


def index_for(events: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "mothership.flight-index.v1",
        "run_id": "run-complete-001",
        "created_at": events[0]["occurred_at"],
        "producer_class": "synthetic",
        "event_ids": [item["event_id"] for item in events],
        "required_stages": list(REQUIRED_STAGES),
        "protocol_registry_sha256": REGISTRY_SHA256,
        "privacy_profile": "metadata-only",
        "bundle_sha256": None,
        "declared_verdict": None,
    }


class FlightVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        from mothership.flight_contracts import FlightError
        from mothership.flight_io import FlightBundle, bundle_digest, load_flight_bundle
        from mothership.flight_verify import Finding, FlightEvaluation, evaluate_flight, evaluation_document

        self.FlightError = FlightError
        self.FlightBundle = FlightBundle
        self.bundle_digest = bundle_digest
        self.load_flight_bundle = load_flight_bundle
        self.Finding = Finding
        self.FlightEvaluation = FlightEvaluation
        self.evaluate_flight = evaluate_flight
        self.evaluation_document = evaluation_document

    def bundle(self, events: list[dict[str, object]] | None = None, *, index: dict[str, object] | None = None) -> object:
        events = copy.deepcopy(events or complete_events())
        index = copy.deepcopy(index or index_for(events))
        raw = b"".join(canonical_json_bytes(item) + b"\n" for item in events)
        return self.FlightBundle(Path("/explicit/bundle"), index, tuple(events), raw, ())

    def assert_rule(self, bundle: object, verdict: str, rule_id: str) -> None:
        evaluation = self.evaluate_flight(bundle)
        self.assertEqual(verdict, evaluation.verdict)
        self.assertIn(rule_id, [finding.rule_id for finding in evaluation.findings])

    def test_complete_run_has_no_findings_and_a_closed_evaluation_document(self) -> None:
        evaluation = self.evaluate_flight(self.bundle())

        self.assertIsInstance(evaluation, self.FlightEvaluation)
        self.assertEqual("run-complete-001", evaluation.run_id)
        self.assertEqual("COMPLETE", evaluation.verdict)
        self.assertEqual(REQUIRED_STAGES, evaluation.required_stages)
        self.assertEqual(REQUIRED_STAGES, evaluation.present_stages)
        self.assertEqual((), evaluation.findings)
        self.assertEqual(
            {
                "schema_version": "mothership.flight-verdict.v1",
                "run_id": "run-complete-001",
                "verdict": "COMPLETE",
                "required_stages": list(REQUIRED_STAGES),
                "present_stages": list(REQUIRED_STAGES),
                "findings": [],
                "authority_effect": False,
                "execution_effect": False,
            },
            self.evaluation_document(evaluation),
        )

    def test_public_output_types_are_frozen_and_findings_sort_deterministically(self) -> None:
        finding = self.Finding("FLIGHT.DRIFT.ACTION_CLASS", "event-approval", "action class differs")
        self.assertEqual(finding, self.Finding(finding.rule_id, finding.event_id, finding.detail))
        self.assertLess(self.Finding("A", None, "x"), self.Finding("B", None, "x"))
        with self.assertRaises(FrozenInstanceError):
            finding.rule_id = "changed"  # type: ignore[misc]
        evaluation = self.evaluate_flight(self.bundle())
        with self.assertRaises(FrozenInstanceError):
            evaluation.verdict = "INVALID"  # type: ignore[misc]

    def test_authority_and_evidence_mutation_matrix(self) -> None:
        cases: list[tuple[str, object, str, str]] = []

        missing_approval = complete_events()
        missing_approval = [item for item in missing_approval if item["stage"] != "approval"]
        next(item for item in missing_approval if item["stage"] == "execution")["predecessor_event_ids"] = ["event-decision"]
        cases.append(("missing approval", self.bundle(missing_approval), "INCOMPLETE", "FLIGHT.INCOMPLETE.APPROVAL"))

        stale_approval = complete_events()
        next(item for item in stale_approval if item["stage"] == "execution")["predecessor_event_ids"] = ["event-decision"]
        next(item for item in stale_approval if item["stage"] == "approval")["occurred_at"] = "2026-08-12T00:00:05Z"
        cases.append(("stale approval", self.bundle(stale_approval), "DRIFTED", "FLIGHT.DRIFT.AUTHORITY"))

        substituted_scope = complete_events()
        next(item for item in substituted_scope if item["stage"] == "approval")["scope_sha256"] = OTHER_SHA256
        cases.append(("substituted approval scope", self.bundle(substituted_scope), "DRIFTED", "FLIGHT.DRIFT.SCOPE"))

        action_escalation = complete_events()
        next(item for item in action_escalation if item["stage"] == "approval")["action_class"] = "process_execute"
        cases.append(("action escalation", self.bundle(action_escalation), "DRIFTED", "FLIGHT.DRIFT.ACTION_CLASS"))

        false_success = complete_events()
        next(item for item in false_success if item["stage"] == "execution")["outcome_status"] = "failed"
        cases.append(("result after failed execution", self.bundle(false_success), "DRIFTED", "FLIGHT.DRIFT.FALSE_SUCCESS"))

        substituted_result = complete_events()
        for stage in ("verification", "persistence"):
            item = next(item for item in substituted_result if item["stage"] == stage)
            item["subject"] = dict(item["subject"], sha256=OTHER_SHA256)  # type: ignore[arg-type]
        cases.append(("result digest substitution", self.bundle(substituted_result), "DRIFTED", "FLIGHT.DRIFT.RESULT"))

        missing_verification = complete_events()
        missing_verification = [item for item in missing_verification if item["stage"] != "verification"]
        next(item for item in missing_verification if item["stage"] == "persistence")["predecessor_event_ids"] = ["event-result"]
        cases.append(("missing verification", self.bundle(missing_verification), "INCOMPLETE", "FLIGHT.INCOMPLETE.VERIFICATION"))

        missing_persistence = [item for item in complete_events() if item["stage"] != "persistence"]
        cases.append(("missing persistence", self.bundle(missing_persistence), "INCOMPLETE", "FLIGHT.INCOMPLETE.PERSISTENCE"))

        mismatched_persistence = complete_events()
        item = next(item for item in mismatched_persistence if item["stage"] == "persistence")
        item["subject"] = dict(item["subject"], sha256=OTHER_SHA256)  # type: ignore[arg-type]
        cases.append(("persistence digest mismatch", self.bundle(mismatched_persistence), "DRIFTED", "FLIGHT.DRIFT.PERSISTENCE"))

        declared_drift = complete_events()
        declared_index = index_for(declared_drift)
        declared_index["declared_verdict"] = "DRIFTED"
        cases.append(("contradictory declared verdict", self.bundle(declared_drift, index=declared_index), "DRIFTED", "FLIGHT.DRIFT.DECLARED_VERDICT"))

        for name, bundle, verdict, rule_id in cases:
            with self.subTest(name=name):
                self.assert_rule(bundle, verdict, rule_id)

    def test_complete_requires_a_shared_scope_digest_non_none_action_and_execution_effect(self) -> None:
        no_scope_or_action = complete_events()
        for item in no_scope_or_action:
            if item["stage"] in {"scope", "approval", "execution"}:
                item["scope_sha256"] = None
                item["action_class"] = "none"
        evaluation = self.evaluate_flight(self.bundle(no_scope_or_action))
        self.assertEqual("DRIFTED", evaluation.verdict)
        self.assertEqual(
            {"FLIGHT.DRIFT.SCOPE", "FLIGHT.DRIFT.ACTION_CLASS"},
            {item.rule_id for item in evaluation.findings},
        )

        no_execution_effect = complete_events()
        next(item for item in no_execution_effect if item["stage"] == "execution")["execution_effect"] = False
        self.assert_rule(self.bundle(no_execution_effect), "INCOMPLETE", "FLIGHT.INCOMPLETE.EVIDENCE")

    def test_identity_and_graph_mutation_matrix(self) -> None:
        duplicate = complete_events()
        duplicate[5]["event_id"] = duplicate[4]["event_id"]
        duplicate_index = index_for(duplicate)

        broken_predecessor = complete_events()
        next(item for item in broken_predecessor if item["stage"] == "execution")["predecessor_event_ids"] = ["event-missing"]

        reversed_timestamp = complete_events()
        next(item for item in reversed_timestamp if item["stage"] == "execution")["occurred_at"] = "2026-08-12T00:00:02Z"

        mixed_run = complete_events()
        next(item for item in mixed_run if item["stage"] == "result")["run_id"] = "run-other-001"

        for name, bundle, rule_id in (
            ("duplicate event id", self.bundle(duplicate, index=duplicate_index), "FLIGHT.INVALID.IDENTITY"),
            ("broken predecessor", self.bundle(broken_predecessor), "FLIGHT.INVALID.GRAPH"),
            ("reversed timestamp", self.bundle(reversed_timestamp), "FLIGHT.INVALID.GRAPH"),
            ("mixed run id", self.bundle(mixed_run), "FLIGHT.INVALID.IDENTITY"),
        ):
            with self.subTest(name=name):
                self.assert_rule(bundle, "INVALID", rule_id)

    def test_loader_rejects_schema_registry_and_bundle_integrity_mutations(self) -> None:
        cases: list[tuple[str, list[dict[str, object]], dict[str, object], str]] = []
        unknown_version = complete_events()
        unknown_version[0]["schema_version"] = "mothership.flight-event.v2"
        cases.append(("unknown event version", unknown_version, index_for(unknown_version), "FLIGHT.INVALID.SCHEMA"))

        extra_field = complete_events()
        extra_field[0]["extra"] = "unexpected"
        cases.append(("extra event field", extra_field, index_for(extra_field), "FLIGHT.INVALID.SCHEMA"))

        changed_registry = complete_events()
        registry_index = index_for(changed_registry)
        registry_index["protocol_registry_sha256"] = OTHER_SHA256
        cases.append(("changed registry digest", changed_registry, registry_index, "FLIGHT.INVALID.REGISTRY"))

        changed_bundle = complete_events()
        bundle_index = index_for(changed_bundle)
        bundle_index["bundle_sha256"] = OTHER_SHA256
        cases.append(("changed bundle digest", changed_bundle, bundle_index, "FLIGHT.INVALID.DIGEST"))

        for name, events, index, rule_id in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(os.path.realpath(temporary)) / "bundle"
                root.mkdir()
                (root / "artifacts").mkdir()
                raw = b"".join(canonical_json_bytes(item) + b"\n" for item in events)
                if index["bundle_sha256"] is None:
                    index["bundle_sha256"] = self.bundle_digest(index, raw, ())
                (root / "flight.json").write_bytes(canonical_json_bytes(index))
                (root / "events.jsonl").write_bytes(raw)
                with self.assertRaises(self.FlightError) as raised:
                    self.load_flight_bundle(root)
                self.assertEqual("INVALID", raised.exception.verdict)
                self.assertEqual(rule_id, raised.exception.rule_id)

    def test_findings_are_sorted_and_declared_verdict_never_overrides_evidence(self) -> None:
        events = complete_events()
        next(item for item in events if item["stage"] == "approval")["scope_sha256"] = OTHER_SHA256
        next(item for item in events if item["stage"] == "approval")["action_class"] = "process_execute"
        index = index_for(events)
        index["declared_verdict"] = "COMPLETE"
        evaluation = self.evaluate_flight(self.bundle(events, index=index))

        self.assertEqual("DRIFTED", evaluation.verdict)
        self.assertEqual(
            sorted(evaluation.findings, key=lambda item: (item.rule_id, item.event_id or "", item.detail)),
            list(evaluation.findings),
        )
        self.assertIn("FLIGHT.DRIFT.DECLARED_VERDICT", [item.rule_id for item in evaluation.findings])


if __name__ == "__main__":
    unittest.main()
