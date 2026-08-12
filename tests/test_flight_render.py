from __future__ import annotations

import copy
import json
import unittest

from orchestration.lib.canonical import canonical_json_bytes
from tests.test_flight_verify import complete_events, index_for


class FlightRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        from mothership.flight_io import FlightBundle
        from mothership.flight_verify import evaluate_flight

        events = complete_events()
        self.bundle = FlightBundle(
            __import__("pathlib").Path("/explicit/bundle"),
            index_for(events),
            tuple(copy.deepcopy(events)),
            b"".join(canonical_json_bytes(item) + b"\n" for item in events),
            (),
        )
        self.evaluation = evaluate_flight(self.bundle)

    def test_replay_document_is_detached_and_has_fixed_projection(self) -> None:
        from mothership.flight_render import replay_document

        document = replay_document(self.bundle, self.evaluation)
        self.assertEqual("mothership.flight-replay.v1", document["schema_version"])
        self.assertEqual("run-complete-001", document["run_id"])
        self.assertEqual("COMPLETE", document["verdict"])
        self.assertEqual(False, document["authority_effect"])
        self.assertEqual(False, document["execution_effect"])
        self.assertEqual(
            [
                {key: event[key] for key in (
                    "event_id", "stage", "event_type", "occurred_at",
                    "predecessor_event_ids", "action_class", "outcome_status",
                )} | {"subject_sha256": event["subject"]["sha256"]}
                for event in self.bundle.events
            ],
            document["timeline"],
        )
        document["timeline"].clear()  # type: ignore[union-attr]
        self.assertEqual(8, len(self.bundle.events))

    def test_markdown_report_is_safe_ordered_and_concise(self) -> None:
        from mothership.flight_render import render_markdown_report

        report = render_markdown_report(self.bundle, self.evaluation)
        self.assertEqual(report, report.encode("utf-8").decode("utf-8"))
        self.assertTrue(report.endswith("\n"))
        sections = ["# Mothership Flight Report", "## Verdict", "## Authority", "## Timeline", "## Findings", "## Evidence boundary"]
        self.assertEqual(sections, [line for line in report.splitlines() if line.startswith("#")])
        self.assertIn("COMPLETE", report)
        self.assertIn("run-complete-001", report)
        self.assertIn("8/8 required stages present", report)
        self.assertIn("file_write / bbbbbbbbbbbb", report)
        self.assertIn("This report verifies supplied records; it does not grant authority or prove unobserved real-world actions.", report)
        self.assertNotIn("refs/", report)
        self.assertNotIn("/explicit", report)
        self.assertNotIn("a" * 13, report)

    def test_markdown_escapes_table_values_and_reports_findings_in_stable_order(self) -> None:
        from mothership.flight_render import render_markdown_report
        from mothership.flight_verify import Finding, FlightEvaluation

        event = dict(self.bundle.events[0])
        event["event_id"] = "e|\\\n\u0001"
        event["stage"] = "s|\\\n\u0002"
        bundle = type(self.bundle)(self.bundle.root, self.bundle.index, (event,), self.bundle.events_bytes, ())
        evaluation = FlightEvaluation("run-complete-001", "INVALID", ("intent",), ("intent",), (
            Finding("RULE.B", None, "detail|\\\n\u0003"),
            Finding("RULE.A", "e|\\\n\u0001", "first"),
        ))
        report = render_markdown_report(bundle, evaluation)
        self.assertIn("- RULE.B (None): detail\\|\\\\\\n\\x03", report)
        self.assertIn("- RULE.A (e\\|\\\\\\n\\x01): first", report)
        self.assertNotIn("\x01", report)

    def test_no_findings_and_missing_approval_are_explicit(self) -> None:
        from mothership.flight_render import render_markdown_report
        from mothership.flight_verify import FlightEvaluation

        events = tuple(event for event in self.bundle.events if event["stage"] != "approval")
        bundle = type(self.bundle)(self.bundle.root, self.bundle.index, events, self.bundle.events_bytes, ())
        evaluation = FlightEvaluation("run-complete-001", "INCOMPLETE", ("intent",), ("intent",), ())
        report = render_markdown_report(bundle, evaluation)
        self.assertIn("- None.", report)
        self.assertIn("Approval: None / None", report)


if __name__ == "__main__":
    unittest.main()
