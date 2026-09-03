from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import unittest
import venv
import zipfile


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HAS_BUILD = importlib.util.find_spec("build") is not None


class DistributionMetadataTests(unittest.TestCase):
    def test_build_tooling_is_optional_and_runtime_dependencies_remain_empty(self) -> None:
        project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text("utf-8"))[
            "project"
        ]
        self.assertEqual([], project["dependencies"])
        self.assertEqual(
            ["build>=1.2", "setuptools>=77"],
            project["optional-dependencies"]["test"],
        )


@unittest.skipUnless(HAS_BUILD, "install the test extra to run distribution verification")
class BuiltDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name).resolve()
        cls.source = cls.root / "source"
        shutil.copytree(
            PACKAGE_ROOT,
            cls.source,
            ignore=shutil.ignore_patterns(
                ".git",
                ".worktrees",
                "__pycache__",
                "*.pyc",
                "build",
                "dist",
                "*.egg-info",
            ),
        )
        cls.dist = cls.root / "dist"
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--sdist",
                "--no-isolation",
                "--outdir",
                str(cls.dist),
            ],
            cwd=cls.source,
            env=environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr.decode("utf-8", "replace"))
        wheels = tuple(cls.dist.glob("*.whl"))
        sdists = tuple(cls.dist.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise AssertionError("build must produce exactly one wheel and one sdist")
        cls.wheel = wheels[0]
        cls.sdist = sdists[0]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_wheel_contains_public_code_and_every_inventory_resource(self) -> None:
        with zipfile.ZipFile(self.wheel) as archive:
            names = set(archive.namelist())
            self.assertIn("mothership/__init__.py", names)
            self.assertIn("mothership/cli.py", names)
            self.assertIn("orchestration/lib/paths.py", names)
            self.assertIn("frontdoor/route.py", names)
            self.assertIn("safety/policy.py", names)
            compatibility_resources = (
                "evidence/contracts/approval-event.schema.json",
                "evidence/contracts/authority-action-approval.v0.schema.json",
                "evidence/contracts/authority-action-consume.v0.schema.json",
                "frontdoor/contracts/decision.schema.json",
                "frontdoor/contracts/task.schema.json",
                "orchestration/config/executors.json",
                "orchestration/contracts/executor-registry.schema.json",
                "orchestration/contracts/invocation-request.schema.json",
            "safety/contracts/assessment.schema.json",
            "evidence/contracts/decision-card.v0.schema.json",
            "evidence/contracts/decision-approval.v0.schema.json",
            )
            for resource in compatibility_resources:
                self.assertIn(resource, names)
            inventory = json.loads(archive.read("mothership/resources/inventory.json"))
            for entry in inventory["resources"]:
                self.assertIn(f"mothership/resources/{entry['path']}", names)
            self.assertFalse(any(name.startswith("tests/") for name in names))
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
            for name in names:
                if not name.endswith("/"):
                    raw = archive.read(name)
                    self.assertNotIn(b"/private" + b"/", raw)
                    self.assertNotIn(b"/Users/", raw)

    def test_wheel_authority_facade_freezes_without_ledger_or_execution(self) -> None:
        _environment, binary = self._environment("authority-facade", editable=False)
        script = b"""
from mothership.action_authority import action_sha256, freeze_action

parameters = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}
frozen = freeze_action("act-pkg-001", "github.merge_pr", parameters)
assert frozen.action["operation"] == "github.merge_pr"
assert action_sha256(dict(frozen.action)) == frozen.action_sha256
assert frozen.expires_at.endswith("Z")
print("AUTHORITY_FACADE_OK")
"""
        result = self._run([str(binary), "-c", script], self.root)
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"AUTHORITY_FACADE_OK", result.stdout)

    def test_wheel_metadata_has_version_python_license_and_no_runtime_requirement(self) -> None:
        with zipfile.ZipFile(self.wheel) as archive:
            metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            metadata = archive.read(metadata_name).decode("utf-8")
        self.assertIn("Name: mothership-control-plane\n", metadata)
        self.assertIn("Version: 0.4.1\n", metadata)
        self.assertIn("Requires-Python: >=3.12\n", metadata)
        self.assertIn("License-Expression: MIT\n", metadata)
        runtime_requirements = [
            line
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
        self.assertEqual([], runtime_requirements)

    def _environment(self, name: str, *, editable: bool) -> tuple[Path, Path]:
        root = self.root / name
        builder = venv.EnvBuilder(with_pip=True, system_site_packages=editable)
        builder.create(root)
        binary = root / "bin/python"
        pip = [str(binary), "-m", "pip", "install", "--no-deps"]
        target = self.source if editable else self.wheel
        if editable:
            pip.extend(["--no-build-isolation", "-e"])
        install_environment = dict(os.environ)
        if editable:
            install_environment["PYTHONPATH"] = sysconfig.get_paths()["purelib"]
        completed = subprocess.run(
            [*pip, str(target)],
            cwd=self.root,
            env=install_environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", "replace"))
        return root, binary

    def _run(self, argv: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        environment = {
            "HOME": str(cwd),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        return subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_installed_package_validates_decision_card_and_approval_outside_source(self) -> None:
        """Prove decision-card and decision-approval schemas are usable after wheel install."""
        environment, binary = self._environment("decision-wheel-env", editable=False)

        script = (
            "from orchestration.lib.contracts import validate_contract; "
            "from orchestration.lib.canonical import canonical_json_sha256; "
            "from orchestration.lib.decision import validate_decision_approval_binding; "
            "card = {"
            "  'schema_version': 'decision-card.v0',"
            "  'decision_id': 'dc-pkg-001',"
            "  'task_id': 'task-pkg-001',"
            "  'question': 'Installed?',"
            "  'recommendation': 'Yes.',"
            "  'reasons': ['wheel test'],"
            "  'evidence_refs': [],"
            "  'unknowns': [],"
            "  'risk': 'low',"
            "  'authority_required': 'human',"
            "  'consequence_if_approved': 'Package is verified.',"
            "  'authority_effect': False,"
            "  'execution_effect': False,"
            "}; "
            "validated_card = validate_contract('decision-card', card); "
            "digest = canonical_json_sha256(validated_card); "
            "approval = {"
            "  'schema_version': 'decision-approval.v0',"
            "  'approval_id': 'ap-pkg-001',"
            "  'decision_id': 'dc-pkg-001',"
            "  'decision_card_sha256': digest,"
            "  'approver_class': 'human',"
            "  'event': 'approve',"
            "  'recorded_at': '2026-08-20T00:00:00Z',"
            "  'expires_at': '2026-08-21T00:00:00Z',"
            "}; "
            "validate_decision_approval_binding(card, approval); "
            "print('DECISION_BINDING_OK')"
        )
        result = self._run([str(binary), "-c", script], self.root)
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"DECISION_BINDING_OK", result.stdout)

    def test_wheel_console_and_module_forms_match_outside_repository(self) -> None:
        environment, binary = self._environment("wheel-env", editable=False)
        console = environment / "bin/mothership"
        for arguments in (("verify",), ("protocol", "list"), ("demo",)):
            with self.subTest(arguments=arguments):
                module = self._run([str(binary), "-m", "mothership", *arguments], self.root)
                entry = self._run([str(console), *arguments], self.root)
                self.assertEqual(0, module.returncode, module.stderr)
                self.assertEqual(module.stdout, entry.stdout)
                self.assertEqual(module.stderr, entry.stderr)
        invalid_doctor = self._run([str(console), "doctor", "invalid"], self.root)
        self.assertEqual(1, invalid_doctor.returncode)
        self.assertEqual("invalid_alias_selection", json.loads(invalid_doctor.stdout)["error"])

        fixture = self.source / "mothership/resources/golden-path/02-governance-handoff.json"
        arguments = ("protocol", "validate", "governance-handoff", str(fixture))
        module = self._run([str(binary), "-m", "mothership", *arguments], self.root)
        entry = self._run([str(console), *arguments], self.root)
        self.assertEqual(0, module.returncode, module.stderr)
        self.assertEqual(module.stdout, entry.stdout)

    def test_wheel_compatibility_apis_load_their_bundled_contracts(self) -> None:
        _environment, binary = self._environment("wheel-contracts", editable=False)
        script = b"""
from mothership.contracts import validate_contract
from safety.policy import assess

task = {
    \"schema_version\": \"0.1.0\",
    \"task_id\": \"installed-contract-test\",
    \"caller_id\": \"distribution-test\",
    \"invocation_id\": \"installed-contract-test\",
    \"requested_action\": \"advisory\",
    \"risk_class\": \"low\",
    \"required_capabilities\": [\"read-only\"],
    \"cost_ceiling_usd_micros\": 0,
    \"context_files\": [],
    \"max_context_files\": 1,
    \"max_context_bytes\": 1,
    \"prompt_file\": \"prompt.md\",
    \"mutation_class\": \"none\",
    \"retry\": {\"enabled\": False},
    \"fallback\": {\"enabled\": False},
    \"max_attempts\": 1,
}
validate_contract(\"task\", task)
result = assess(task, \"dry-run\", None, 0, None)
assert result[\"classification\"] == \"unclassified\"
"""
        completed = subprocess.run(
            [str(binary), "-I", "-c", script],
            cwd=self.root,
            env={
                "HOME": str(self.root),
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", "replace"))

    def test_editable_install_matches_wheel_for_read_only_commands(self) -> None:
        wheel_environment, wheel_binary = self._environment("wheel-compare", editable=False)
        editable_environment, editable_binary = self._environment("editable-env", editable=True)
        for arguments in (("verify",), ("protocol", "list"), ("demo",)):
            wheel_result = self._run([str(wheel_binary), "-m", "mothership", *arguments], self.root)
            editable_result = self._run([str(editable_binary), "-m", "mothership", *arguments], self.root)
            with self.subTest(arguments=arguments):
                self.assertEqual(0, wheel_result.returncode, wheel_result.stderr)
                self.assertEqual(wheel_result.stdout, editable_result.stdout)


if __name__ == "__main__":
    unittest.main()
