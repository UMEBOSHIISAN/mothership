from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools import run_evaluation


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evaluation/corpus/protocol-validation.v1.json"
RESULT = ROOT / "evaluation/results/mothership-0.5.0.dev0.json"
RUNNER = ROOT / "tools/run_evaluation.py"


class EvaluationTests(unittest.TestCase):
    def test_mutation_cases_leave_source_fixture_and_instructions_unchanged(self) -> None:
        corpus = run_evaluation._load_corpus()
        before_corpus = copy.deepcopy(corpus)
        paths = [CORPUS, RESULT, *run_evaluation.GOLDEN.glob("*.json")]
        before_files = {path: path.read_bytes() for path in paths}
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                source = run_evaluation._load_json(run_evaluation.GOLDEN / case["fixture"])
                before_source = copy.deepcopy(source)
                result = run_evaluation._mutate(source, case["mutation"])
                # Modifying the returned trial must not poison the cached source.
                result["synthetic-contamination"] = True
                self.assertEqual(before_source, source)
                self.assertEqual(before_corpus, corpus)
        self.assertEqual(before_files, {path: path.read_bytes() for path in paths})

    def test_protocol_measurement_repeats_independently_of_case_order(self) -> None:
        corpus = run_evaluation._load_corpus()
        before = copy.deepcopy(corpus)
        expected = {
            "valid_cases": 4, "valid_accepted": 4,
            "invalid_cases": 20, "invalid_rejected": 20,
            "cases_passed": 24, "cases_total": 24,
        }
        cases = corpus["cases"]
        for order in (cases, list(reversed(cases)), cases[::2] + cases[1::2]):
            trial = {**corpus, "cases": order}
            for repeat in range(2):
                with self.subTest(order=order[0]["id"], repeat=repeat):
                    self.assertEqual(expected, run_evaluation._protocol_measurement(trial))
                    self.assertEqual(before, corpus)

    def test_scoring_exception_does_not_contaminate_the_next_measurement(self) -> None:
        corpus = run_evaluation._load_corpus()
        before = copy.deepcopy(corpus)
        paths = [CORPUS, *run_evaluation.GOLDEN.glob("*.json")]
        before_files = {path: path.read_bytes() for path in paths}
        validate = run_evaluation.validate_protocol
        calls = 0

        def fail_midway(kind, document):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("synthetic scoring interruption")
            return validate(kind, document)

        with mock.patch.object(run_evaluation, "validate_protocol", side_effect=fail_midway):
            with self.assertRaisesRegex(RuntimeError, "synthetic scoring interruption"):
                run_evaluation._protocol_measurement(corpus)
        self.assertEqual(before, corpus)
        self.assertEqual(before_files, {path: path.read_bytes() for path in paths})
        self.assertEqual(
            {"valid_cases": 4, "valid_accepted": 4, "invalid_cases": 20,
             "invalid_rejected": 20, "cases_passed": 24, "cases_total": 24},
            run_evaluation._protocol_measurement(corpus),
        )

    def test_unavailable_corpus_cannot_reuse_a_previous_success(self) -> None:
        # A completed prior measurement must not stand in for unreadable input.
        run_evaluation._protocol_measurement(run_evaluation._load_corpus())
        with tempfile.TemporaryDirectory() as directory:
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8")
            stderr = io.StringIO()
            with (
                mock.patch.object(run_evaluation, "CORPUS", Path(directory) / "absent.json"),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = run_evaluation.main()
            stdout.flush()
            self.assertEqual(1, code)
            self.assertEqual(b"", output.getvalue())
            self.assertEqual("evaluation failed closed\n", stderr.getvalue())
        self.assertEqual(24, run_evaluation._protocol_measurement(run_evaluation._load_corpus())["cases_passed"])

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
        self.assertEqual("0.5.0.dev0", result["subject_version"])
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

    def test_malformed_enum_fields_fail_closed_without_a_traceback(self) -> None:
        original = json.loads(CORPUS.read_text("utf-8"))
        corruptions = {
            "expected-array": ("expected", []),
            "mutation-op-array": ("mutation", {"op": [], "path": ["request_id"]}),
        }
        for name, (field, value) in corruptions.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                corpus = json.loads(json.dumps(original))
                corpus["cases"][1][field] = value
                path = Path(directory) / "corpus.json"
                path.write_text(json.dumps(corpus), encoding="utf-8")
                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    mock.patch.object(run_evaluation, "CORPUS", path),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    exit_code = run_evaluation.main()
                self.assertEqual(1, exit_code)
                self.assertEqual("", stdout.getvalue())
                self.assertEqual("evaluation failed closed\n", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
