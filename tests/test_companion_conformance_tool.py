from __future__ import annotations

import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orchestration.lib.canonical import canonical_json_bytes
from tools import check_companion_conformance as tool


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "mothership/resources"
COMMITS = {
    "agent-frontdoor": "296c49be801b6573abf54daa81b828df95e8e84f",
    "workflow-governance-model": "faec3725781547cc64e58b3eb14177885bd315f6",
    "mothership-router": "e4669fb9534bf97030134d4305caa492c87f7ed3",
    "secretary-tui": "bd933d5dee7dbe4b9ca8057f7848c2ef70261b2d",
}
OWNERS = (
    {
        "repository": "agent-frontdoor",
        "kind": "frontdoor-task",
        "version": "intake.v0",
        "schema_path": "src/frontdoor/schema/intake.v0.json",
        "snapshot": "protocols/schemas/frontdoor-task.intake.v0.schema.json",
        "example_path": "examples/mothership-task.json",
        "fixture": "golden-path/01-frontdoor-task.json",
    },
    {
        "repository": "workflow-governance-model",
        "kind": "governance-handoff",
        "version": "1.1",
        "schema_path": "schemas/workflow-handoff.1.1.schema.json",
        "snapshot": "protocols/schemas/governance-handoff.1.1.schema.json",
        "example_path": "examples/handoff.valid.json",
        "fixture": "golden-path/02-governance-handoff.json",
    },
    {
        "repository": "mothership-router",
        "kind": "router-manifest",
        "version": "1.0",
        "schema_path": "src/mothership_router/schema/router-manifest.1.0.schema.json",
        "snapshot": "protocols/schemas/router-manifest.1.0.schema.json",
        "example_path": "examples/router-manifest.json",
        "fixture": "golden-path/03-router-manifest.json",
    },
    {
        "repository": "secretary-tui",
        "kind": "observation-snapshot",
        "version": "1.0",
        "schema_path": "schemas/observation-snapshot.1.0.schema.json",
        "snapshot": "protocols/schemas/observation-snapshot.1.0.schema.json",
        "example_path": "examples/observation-snapshot.json",
        "fixture": "golden-path/04-observation-snapshot.json",
    },
)


class CompanionConformanceToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.roots: list[Path] = []
        for owner in OWNERS:
            repository_root = self.root / owner["repository"]
            self.roots.append(repository_root)
            schema = (RESOURCE_ROOT / owner["snapshot"]).read_bytes()
            example = (RESOURCE_ROOT / owner["fixture"]).read_bytes()
            self._write(repository_root / owner["schema_path"], schema)
            self._write(repository_root / owner["example_path"], example)
            manifest = {
                "schema_version": "mothership.conformance.v1",
                "suite_release": "0.2.0",
                "repository": owner["repository"],
                "protocol_kind": owner["kind"],
                "protocol_version": owner["version"],
                "schema_path": owner["schema_path"],
                "schema_sha256": hashlib.sha256(schema).hexdigest(),
                "example_path": owner["example_path"],
                "authority_effect": False,
                "execution_effect": False,
            }
            self._write(
                repository_root / "suite/mothership-0.2-conformance.json",
                json.dumps(manifest, indent=2).encode() + b"\n",
            )
        router_example = (RESOURCE_ROOT / OWNERS[2]["fixture"]).read_bytes()
        self._write(self.roots[3] / "examples/router-manifest.json", router_example)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _heads(self, _root: Path) -> str:
        return COMMITS[_root.name]

    def _audit(self) -> dict[str, object]:
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            return tool.audit_companions(tuple(self.roots))

    def test_explicit_four_owner_audit_returns_closed_path_free_report(self) -> None:
        report = self._audit()
        self.assertEqual(
            {
                "schema_version",
                "status",
                "suite_release",
                "owners",
                "chain",
            },
            set(report),
        )
        self.assertEqual("mothership.companion-conformance.v1", report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual("0.2.0", report["suite_release"])
        self.assertEqual(
            [owner["repository"] for owner in OWNERS],
            [owner["repository"] for owner in report["owners"]],
        )
        for owner in report["owners"]:
            self.assertEqual(
                {
                    "repository",
                    "commit",
                    "protocol_kind",
                    "protocol_version",
                    "schema_sha256",
                    "valid",
                },
                set(owner),
            )
            self.assertIs(True, owner["valid"])
        self.assertEqual(
            {
                "status": "passed",
                "task_id": "demo-review-001",
                "capability": "code-review",
                "authority_effect": False,
                "execution_effect": False,
            },
            report["chain"],
        )
        serialized = canonical_json_bytes(report)
        self.assertNotIn(str(self.root).encode(), serialized)
        self.assertNotIn(b"/Users/", serialized)

    def test_cli_emits_one_canonical_json_document(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        arguments = [
            "--frontdoor-root",
            str(self.roots[0]),
            "--wgm-root",
            str(self.roots[1]),
            "--router-root",
            str(self.roots[2]),
            "--secretary-root",
            str(self.roots[3]),
        ]
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            exit_code = tool.main(arguments, stdout=stdout, stderr=stderr)
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr.getvalue())
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(canonical_json_bytes(parsed) + b"\n", stdout.getvalue().encode())

    def test_wrong_repository_order_fails_closed(self) -> None:
        wrong = (self.roots[1], self.roots[0], self.roots[2], self.roots[3])
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            with self.assertRaises(tool.ConformanceError):
                tool.audit_companions(wrong)

    def test_stale_commit_fails_closed(self) -> None:
        with mock.patch.object(tool, "_git_head", return_value="0" * 40):
            with self.assertRaises(tool.ConformanceError):
                tool.audit_companions(tuple(self.roots))

    def test_symlink_root_fails_closed(self) -> None:
        link = self.root / "frontdoor-link"
        link.symlink_to(self.roots[0], target_is_directory=True)
        roots = (link, *self.roots[1:])
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            with self.assertRaises(tool.ConformanceError):
                tool.audit_companions(roots)

    def test_path_traversal_and_missing_artifacts_fail_closed(self) -> None:
        manifest_path = self.roots[0] / "suite/mothership-0.2-conformance.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["schema_path"] = "../outside.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            with self.assertRaises(tool.ConformanceError):
                tool.audit_companions(tuple(self.roots))

    def test_effect_escalation_fails_closed(self) -> None:
        example_path = self.roots[3] / "examples/observation-snapshot.json"
        example = json.loads(example_path.read_text("utf-8"))
        example["execution_effect"] = True
        example_path.write_text(json.dumps(example), encoding="utf-8")
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            with self.assertRaises(tool.ConformanceError):
                tool.audit_companions(tuple(self.roots))

    def test_secretary_router_input_must_match_router_owner_example(self) -> None:
        input_path = self.roots[3] / "examples/router-manifest.json"
        document = json.loads(input_path.read_text("utf-8"))
        document["task_id"] = "drifted"
        input_path.write_text(json.dumps(document), encoding="utf-8")
        with mock.patch.object(tool, "_git_head", side_effect=self._heads):
            with self.assertRaises(tool.ConformanceError):
                tool.audit_companions(tuple(self.roots))

    def test_cli_failure_is_fixed_and_does_not_echo_paths(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        missing = self.root / "private-customer-repository"
        exit_code = tool.main(
            [
                "--frontdoor-root",
                str(missing),
                "--wgm-root",
                str(self.roots[1]),
                "--router-root",
                str(self.roots[2]),
                "--secretary-root",
                str(self.roots[3]),
            ],
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(1, exit_code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("conformance_error: companion audit failed\n", stderr.getvalue())
        self.assertNotIn(str(missing), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
