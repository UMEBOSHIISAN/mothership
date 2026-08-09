from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


VALID = {
    "frontdoor-task": {
        "schema_version": "intake.v0",
        "request_id": "demo-review-001",
        "human_request": "Review the supplied fictional change",
        "task_class": "CODE_REVIEW",
        "risk_tags": [],
        "allowed_actions": ["read supplied files"],
        "forbidden_actions": ["modify files"],
        "required_evidence": ["review findings"],
        "required_manifest": None,
        "human_gate": "NONE",
        "predicted_worker_capability": "code-review",
        "unknowns": [],
        "assumptions": [],
        "next_safe_step": "Inspect the fictional change",
    },
    "governance-handoff": {
        "schema_version": "1.1",
        "task_id": "demo-review-001",
        "capability": "code-review",
        "risk": "low",
        "token_budget": 4000,
        "evidence_references": ["evidence:demo-change-v1"],
    },
    "router-manifest": {
        "schema_version": "1.0",
        "task_id": "demo-review-001",
        "capability": "code-review",
        "status": "approval_required",
        "recommended_alias": "local-review",
        "registry_sha256": "a" * 64,
        "reasons": ["manifest_only"],
        "authority_effect": False,
        "execution_effect": False,
    },
    "observation-snapshot": {
        "schema_version": "1.0",
        "task_id": "demo-review-001",
        "source_kind": "router-manifest",
        "source_schema_version": "1.0",
        "status": "approval_required",
        "summary": ["candidate: local-review", "authority: none"],
        "authority_effect": False,
        "execution_effect": False,
    },
}


class ProtocolValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, name: str, raw: bytes) -> Path:
        path = self.root / name
        path.write_bytes(raw)
        return path

    def test_list_protocols_returns_detached_ordered_metadata(self) -> None:
        from mothership.protocols import list_protocols

        first = list_protocols()
        second = list_protocols()
        self.assertEqual(
            (
                "frontdoor-task",
                "governance-handoff",
                "router-manifest",
                "observation-snapshot",
            ),
            tuple(entry["kind"] for entry in first),
        )
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertTrue(all(entry["authority_capable"] is False for entry in first))
        self.assertTrue(all(entry["execution_capable"] is False for entry in first))

    def test_each_protocol_accepts_its_exact_valid_shape(self) -> None:
        from mothership.protocols import validate_protocol

        for kind, document in VALID.items():
            with self.subTest(kind=kind):
                result = validate_protocol(kind, document)
                self.assertEqual(document, result)
                self.assertIsNot(document, result)

    def test_integer_schema_accepts_integral_json_number(self) -> None:
        from mothership.protocols import validate_protocol

        document = {
            **VALID["governance-handoff"],
            "token_budget": 4000.0,
        }
        self.assertEqual(
            document,
            validate_protocol("governance-handoff", document),
        )

    def test_validated_result_is_recursively_detached(self) -> None:
        from mothership.protocols import validate_protocol

        document = {
            **VALID["governance-handoff"],
            "evidence_references": ["evidence:demo-change-v1"],
        }
        result = validate_protocol("governance-handoff", document)

        document["evidence_references"][0] = "/" + "private/changed-after-validation"

        self.assertEqual(["evidence:demo-change-v1"], result["evidence_references"])
        self.assertIsNot(document["evidence_references"], result["evidence_references"])

    def test_deep_unknown_metadata_fails_closed_without_recursion_error(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol

        nested: object = 0
        for _ in range(2_000):
            nested = {"x": nested}
        document = {
            **VALID["governance-handoff"],
            "meta": nested,
        }

        with self.assertRaisesRegex(ProtocolError, "unknown field"):
            validate_protocol("governance-handoff", document)

    def test_unknown_kind_and_version_fail_before_other_validation(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol

        with self.assertRaisesRegex(ProtocolError, r"^\$: protocol kind is unknown$"):
            validate_protocol("unknown", {"password": "never"})
        with self.assertRaisesRegex(
            ProtocolError,
            r"^\$\.schema_version: protocol version is unsupported$",
        ):
            validate_protocol(
                "governance-handoff",
                {"schema_version": "0", "password": "never"},
            )

    def test_closed_schema_types_constraints_and_effects_fail(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol

        cases = {
            "unknown": ("governance-handoff", {**VALID["governance-handoff"], "extra": "x"}),
            "missing": (
                "governance-handoff",
                {key: value for key, value in VALID["governance-handoff"].items() if key != "risk"},
            ),
            "bool_integer": ("governance-handoff", {**VALID["governance-handoff"], "token_budget": True}),
            "minimum": ("governance-handoff", {**VALID["governance-handoff"], "token_budget": 0}),
            "enum": ("governance-handoff", {**VALID["governance-handoff"], "risk": "urgent"}),
            "governance_unc_task": (
                "governance-handoff",
                {**VALID["governance-handoff"], "task_id": r"\\server\share\private"},
            ),
            "governance_control": (
                "governance-handoff",
                {**VALID["governance-handoff"], "capability": "code\nreview"},
            ),
            "governance_true_end": (
                "governance-handoff",
                {**VALID["governance-handoff"], "task_id": "review-1\n"},
            ),
            "governance_c1_control": (
                "governance-handoff",
                {**VALID["governance-handoff"], "capability": "code\x85review"},
            ),
            "governance_drive_relative": (
                "governance-handoff",
                {**VALID["governance-handoff"], "task_id": "C:private"},
            ),
            "governance_non_ascii": (
                "governance-handoff",
                {**VALID["governance-handoff"], "task_id": "日本語"},
            ),
            "pattern": ("router-manifest", {**VALID["router-manifest"], "registry_sha256": "BAD"}),
            "router_path_task": (
                "router-manifest",
                {**VALID["router-manifest"], "task_id": "/Users/example/private.json"},
            ),
            "router_path_capability": (
                "router-manifest",
                {**VALID["router-manifest"], "capability": "../private.json"},
            ),
            "router_path_alias": (
                "router-manifest",
                {**VALID["router-manifest"], "recommended_alias": r"C:\Users\example"},
            ),
            "router_path_reason": (
                "router-manifest",
                {**VALID["router-manifest"], "reasons": [r"\\?\C:\private"]},
            ),
            "router_true_end_digest": (
                "router-manifest",
                {**VALID["router-manifest"], "registry_sha256": "a" * 64 + "\n"},
            ),
            "router_c1_control": (
                "router-manifest",
                {**VALID["router-manifest"], "reasons": ["private\x9bvalue"]},
            ),
            "one_of": ("router-manifest", {**VALID["router-manifest"], "task_id": 1}),
            "authority": ("router-manifest", {**VALID["router-manifest"], "authority_effect": True}),
            "control": (
                "observation-snapshot",
                {**VALID["observation-snapshot"], "summary": ["unsafe\nline"]},
            ),
            "observation_path_task": (
                "observation-snapshot",
                {**VALID["observation-snapshot"], "task_id": "private/path.json"},
            ),
            "observation_true_end": (
                "observation-snapshot",
                {**VALID["observation-snapshot"], "summary": ["safe line\n"]},
            ),
            "observation_c1_control": (
                "observation-snapshot",
                {**VALID["observation-snapshot"], "summary": ["unsafe\x85line"]},
            ),
            "observation_non_ascii": (
                "observation-snapshot",
                {**VALID["observation-snapshot"], "summary": ["日本語"]},
            ),
        }
        for name, (kind, document) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ProtocolError):
                    validate_protocol(kind, document)

    def test_secret_raw_content_and_private_paths_fail_without_value_leak(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol

        private_prefix = "/private" + "/"
        cases = (
            {**VALID["governance-handoff"], "meta": {"api_key": "never-print"}},
            {**VALID["governance-handoff"], "meta": [{"command": "never-print"}]},
            {
                **VALID["governance-handoff"],
                "evidence_references": [private_prefix + "never-print"],
            },
        )
        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(ProtocolError) as caught:
                    validate_protocol("governance-handoff", document)
                message = str(caught.exception)
                self.assertNotIn("never-print", message)
                self.assertNotIn(private_prefix, message)

    def test_direct_api_rejects_non_json_and_hostile_keys_without_reflection(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol

        private_key = "/" + "private/never-reflect"
        cases = (
            {**VALID["governance-handoff"], 1: "invalid-key"},
            {**VALID["governance-handoff"], private_key: "invalid-key"},
            {**VALID["governance-handoff"], "meta": {1: "invalid-key"}},
        )
        for document in cases:
            with self.subTest(keys=tuple(document)):
                with self.assertRaises(ProtocolError) as caught:
                    validate_protocol("governance-handoff", document)
                message = str(caught.exception)
                self.assertNotIn("never-reflect", message)
                self.assertNotIn(private_key, message)

    def test_file_loader_rejects_unsafe_and_malformed_inputs(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol_file

        valid = self._write("valid.json", json.dumps(VALID["governance-handoff"]).encode())
        self.assertEqual(
            VALID["governance-handoff"],
            validate_protocol_file("governance-handoff", valid),
        )

        malformed = self._write("malformed.json", b'{"schema_version":')
        duplicate = self._write(
            "duplicate.json",
            b'{"schema_version":"1.0","schema_version":"1.0"}',
        )
        nonfinite = self._write(
            "nonfinite.json",
            b'{"schema_version":"1.0","token_budget":NaN}',
        )
        bad_utf8 = self._write("bad-utf8.json", b'{"schema_version":"\xff"}')
        oversized = self._write("oversized.json", b" " * 1_048_577)
        directory = self.root / "directory"
        directory.mkdir()
        symlink = self.root / "link.json"
        symlink.symlink_to(valid)
        ancestor = self.root / "linked-parent"
        ancestor.symlink_to(self.root, target_is_directory=True)

        unsafe = (
            Path("relative.json"),
            malformed,
            duplicate,
            nonfinite,
            bad_utf8,
            oversized,
            directory,
            symlink,
            ancestor / "valid.json",
        )
        for path in unsafe:
            with self.subTest(path=path.name):
                with self.assertRaises(ProtocolError) as caught:
                    validate_protocol_file("governance-handoff", path)
                self.assertNotIn(str(path), str(caught.exception))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires mkfifo")
    def test_fifo_is_rejected_without_blocking(self) -> None:
        from mothership.protocols import ProtocolError, validate_protocol_file

        fifo = self.root / "input.fifo"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ProtocolError, "regular file"):
            validate_protocol_file("governance-handoff", fifo)

    def test_unknown_kind_precedes_file_access(self) -> None:
        from mothership import protocols

        with mock.patch.object(protocols, "_load_protocol_file") as loader:
            with self.assertRaisesRegex(protocols.ProtocolError, "kind is unknown"):
                protocols.validate_protocol_file("unknown", self.root / "missing")
        loader.assert_not_called()

    def test_registry_verification_rejects_unknown_schema_keywords(self) -> None:
        from mothership import protocols

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version"],
            "properties": {
                "schema_version": {"const": "1.0", "format": "unsupported"}
            },
        }
        with mock.patch.object(protocols, "_load_schema", return_value=schema):
            with self.assertRaisesRegex(protocols.ProtocolError, "unsupported schema keyword"):
                protocols.list_protocols()


if __name__ == "__main__":
    unittest.main()
