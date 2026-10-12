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
            code = evidence_cli_main(argv)
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
