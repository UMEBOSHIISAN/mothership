"""Stdin-only evidence adapter CLI tests."""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from test_evidence import EvidenceFixture

from mothership_adapters.cli import main as evidence_cli_main
from mothership_adapters.evidence import MAX_ENCODED_BYTES


class AdapterEvidenceCLITests(EvidenceFixture):
    def _run(self, argv: list[str], payload: object) -> tuple[int, str, str]:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            try:
                code = evidence_cli_main(argv)
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_export_envelope_and_inspect_summary(self) -> None:
        envelope = {
            "request": self.request,
            "export": {
                "response": self.response,
                "decision": self.decision,
                "consume": self.consume,
                "started": self.started,
                "finished": self.finished,
                "executor_ref": {"ref_id": "executor:synthetic", "sha256": "b" * 64},
            },
        }
        code, output, error = self._run(["export"], envelope)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        bundle = json.loads(output)
        self.assertEqual("host-evidence-bundle.v0", bundle["schema_version"])

        code, output, error = self._run(["inspect"], bundle)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        summary = json.loads(output)
        self.assertEqual("caller-attested", summary["provenance"])
        self.assertEqual("source-unverified", summary["source_status"])
        self.assertFalse(summary["authority"])
        self.assertFalse(summary["source_authenticated"])
        self.assertFalse(summary["external_effect_verified"])
        self.assertEqual("SUCCESS", summary["receipt_status"])

    def test_unknown_envelope_field_and_oversized_input_fail_closed(self) -> None:
        envelope = {
            "request": self.request,
            "export": {"executor_ref": {"ref_id": "executor:synthetic", "sha256": "b" * 64}},
            "path": "/tmp/forbidden",
        }
        code, output, error = self._run(["export"], envelope)
        self.assertEqual(2, code)
        self.assertEqual("", output)
        self.assertEqual("invalid bounded evidence input\n", error)

        oversized = b"{" + b'\"x\":\"' + b"x" * MAX_ENCODED_BYTES + b'\"}'
        stdin = io.TextIOWrapper(io.BytesIO(oversized), encoding="utf-8")
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", stderr):
            code = evidence_cli_main(["inspect"])
        self.assertEqual(2, code)
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_inspect_human_is_bounded_text_and_default_json_remains_json(self) -> None:
        bundle = self.full()
        code, output, error = self._run(["inspect", "--human"], bundle)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        self.assertIn("approval: recorded", output)
        self.assertIn("receipt: SUCCESS", output)
        self.assertIn("verification: missing", output)
        self.assertIn("next read-only check:", output)
        self.assertIn("no re-execution", output)
        self.assertIn("no reconsume", output)
        self.assertIn(
            "target: action_id=act-evidence-test; operation=github.merge_pr; repository=UMEBOSHIISAN/mothership; pull_request=5",
            output,
        )
        self.assertNotIn('"schema_version"', output)

        code, output, error = self._run(["inspect"], bundle)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        self.assertEqual("host-evidence-inspection.v0", json.loads(output)["schema_version"])

    def test_inspect_human_rejects_invalid_input_without_side_effects(self) -> None:
        code, output, error = self._run(["inspect", "--human"], {"invalid": True})
        self.assertEqual(2, code)
        self.assertEqual("", output)
        self.assertEqual("invalid bounded evidence input\n", error)

    def test_inspect_human_short_write_fails_without_retry(self) -> None:
        bundle = self.full()
        raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stderr = io.StringIO()

        class ShortWriter:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.flush_calls = 0

            def write(self, text: str) -> int:
                self.calls.append(text)
                return len(text) - 1

            def flush(self) -> None:
                self.flush_calls += 1

        stdout = ShortWriter()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            code = evidence_cli_main(["inspect", "--human"])

        self.assertEqual(2, code)
        self.assertEqual(1, len(stdout.calls))
        self.assertEqual(0, stdout.flush_calls)
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_inspect_human_flush_failure_is_invalid_without_retry(self) -> None:
        bundle = self.full()
        raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stderr = io.StringIO()

        class FlushFailureWriter:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.flush_calls = 0

            def write(self, text: str) -> int:
                self.calls.append(text)
                return len(text)

            def flush(self) -> None:
                self.flush_calls += 1
                raise OSError("flush failed")

        stdout = FlushFailureWriter()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            code = evidence_cli_main(["inspect", "--human"])

        self.assertEqual(2, code)
        self.assertEqual(1, len(stdout.calls))
        self.assertEqual(1, stdout.flush_calls)
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
