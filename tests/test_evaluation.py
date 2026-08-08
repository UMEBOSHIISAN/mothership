from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evaluation/corpus/protocol-validation.v1.json"
RESULT = ROOT / "evaluation/results/mothership-0.2.0.json"
RUNNER = ROOT / "tools/run_evaluation.py"


class EvaluationTests(unittest.TestCase):
    def _run(self, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        environment = {
            "HOME": str(cwd),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "random",
        }
        return subprocess.run(
            [sys.executable, str(RUNNER)],
            cwd=cwd,
            env=environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )

    def test_evaluator_matches_the_frozen_machine_readable_result(self) -> None:
        expected = RESULT.read_bytes()
        self.assertTrue(expected.endswith(b"\n"))
        self.assertFalse(expected.endswith(b"\n\n"))

        completed = self._run(ROOT)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(b"", completed.stderr)
        self.assertEqual(expected, completed.stdout)

    def test_result_records_separate_bounded_measurements(self) -> None:
        result = json.loads(RESULT.read_text("utf-8"))
        self.assertEqual("mothership.evaluation.v1", result["schema_version"])
        self.assertEqual("mothership-control-plane", result["subject"])
        self.assertEqual("0.2.0", result["subject_version"])
        self.assertEqual("synthetic-conformance-only", result["claim_scope"])
        self.assertEqual(
            hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            result["corpus_sha256"],
        )
        self.assertEqual(
            {
                "valid_cases": 4,
                "valid_accepted": 4,
                "invalid_cases": 20,
                "invalid_rejected": 20,
                "cases_passed": 24,
                "cases_total": 24,
            },
            result["protocol_conformance"],
        )
        self.assertEqual(
            {"runs": 8, "distinct_outputs": 1, "byte_identical": True},
            result["demo_determinism"],
        )
        self.assertEqual({"status": "passed"}, result["resource_integrity"])
        self.assertEqual(
            {
                "demo_authority_effect": False,
                "demo_execution_effect": False,
                "protocols_authority_capable": 0,
                "protocols_execution_capable": 0,
                "protocols_total": 4,
            },
            result["authority_boundary"],
        )

    def test_corpus_is_exact_balanced_and_credential_free(self) -> None:
        corpus = json.loads(CORPUS.read_text("utf-8"))
        self.assertEqual("mothership.protocol-evaluation-corpus.v1", corpus["schema_version"])
        cases = corpus["cases"]
        self.assertEqual(24, len(cases))
        self.assertEqual(24, len({case["id"] for case in cases}))
        for kind in (
            "frontdoor-task",
            "governance-handoff",
            "router-manifest",
            "observation-snapshot",
        ):
            selected = [case for case in cases if case["kind"] == kind]
            self.assertEqual(6, len(selected))
            self.assertEqual(1, sum(case["expected"] == "accepted" for case in selected))
            self.assertEqual(5, sum(case["expected"] == "rejected" for case in selected))
        raw = CORPUS.read_bytes().lower()
        for forbidden in (b"api_key", b"password", b"credential", b"access_token"):
            self.assertNotIn(forbidden, raw)

    def test_evaluator_has_no_network_model_or_mutation_surface(self) -> None:
        source = RUNNER.read_text("utf-8")
        for forbidden in (
            "import socket",
            "import urllib",
            "import requests",
            "subprocess.run([\"git\"",
            "write_text(",
            "write_bytes(",
            "open(\"w",
            "open('w",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
