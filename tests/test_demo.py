from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from orchestration.lib.canonical import canonical_json_bytes


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "schema_version": "mothership.demo.v1",
    "status": "passed",
    "task_id": "demo-review-001",
    "capability": "code-review",
    "stages": [
        {"kind": "frontdoor-task", "schema_version": "intake.v0", "valid": True},
        {"kind": "governance-handoff", "schema_version": "1.0", "valid": True},
        {"kind": "router-manifest", "schema_version": "1.0", "valid": True},
        {"kind": "observation-snapshot", "schema_version": "1.0", "valid": True},
    ],
    "authority_effect": False,
    "execution_effect": False,
    "claim": "protocol-composition-only",
}


class DemoTests(unittest.TestCase):
    def test_demo_matches_the_bundled_expected_summary(self) -> None:
        from mothership.demo import run_demo

        result = run_demo()
        self.assertEqual(EXPECTED, result)
        expected_file = (
            PACKAGE_ROOT / "mothership/resources/golden-path/expected-summary.json"
        )
        self.assertEqual(
            canonical_json_bytes(EXPECTED),
            canonical_json_bytes(json.loads(expected_file.read_text("utf-8"))),
        )

    def test_each_golden_stage_is_closed_and_valid(self) -> None:
        from mothership.demo import _load_stage_documents
        from mothership.protocols import validate_protocol

        stages = _load_stage_documents()
        self.assertEqual(4, len(stages))
        for kind, document in stages:
            with self.subTest(kind=kind):
                self.assertEqual(document, validate_protocol(kind, document))

    def test_transition_drift_fails_closed_for_the_intended_class(self) -> None:
        from mothership import demo

        original = demo._load_stage_documents()

        def changed(index: int, **fields: object):
            stages = [(kind, copy.deepcopy(document)) for kind, document in original]
            stages[index][1].update(fields)
            return tuple(stages)

        private_prefix = "/" + "private/"
        mutations = {
            "order": tuple((original[1], original[0], *original[2:])),
            "stale_version": changed(1, schema_version="0"),
            "task_id": changed(2, task_id="drifted-task"),
            "capability": changed(2, capability="implementation"),
            "status": changed(3, status="no_ready_executor"),
            "authority": changed(2, authority_effect=True),
            "execution": changed(3, execution_effect=True),
            "secret_key": changed(3, meta={"api_key": "hidden"}),
            "private_path": changed(1, evidence_references=[private_prefix + "hidden"]),
            "raw_content": changed(3, prompt="hidden"),
        }
        for name, stages in mutations.items():
            with self.subTest(name=name):
                with mock.patch.object(demo, "_load_stage_documents", return_value=stages):
                    with self.assertRaises(demo.DemoError) as caught:
                        demo.run_demo()
                self.assertNotIn("hidden", str(caught.exception))
                self.assertNotIn(private_prefix, str(caught.exception))

    def test_output_is_byte_identical_across_process_environments(self) -> None:
        script = (
            "from mothership.demo import run_demo;"
            "from orchestration.lib.canonical import canonical_json_bytes;"
            "import sys;sys.stdout.buffer.write(canonical_json_bytes(run_demo())+b'\\n')"
        )
        outputs = []
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for index, cwd in enumerate((first, second)):
                environment = {
                    "HOME": cwd,
                    "LANG": "C" if index == 0 else "ja_JP.UTF-8",
                    "LC_ALL": "C" if index == 0 else "ja_JP.UTF-8",
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "PYTHONHASHSEED": str(index + 1),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(PACKAGE_ROOT),
                }
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(b"", result.stderr)
                outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(canonical_json_bytes(EXPECTED) + b"\n", outputs[0])


if __name__ == "__main__":
    unittest.main()
