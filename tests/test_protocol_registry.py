from __future__ import annotations

import hashlib
from importlib import resources
import json
import re
import unittest


KINDS = (
    "frontdoor-task",
    "governance-handoff",
    "router-manifest",
    "observation-snapshot",
)
ENTRY_KEYS = {
    "authority_capable",
    "bundled_schema_path",
    "execution_capable",
    "frozen_in_mothership",
    "kind",
    "owner_repository",
    "predecessors",
    "schema_sha256",
    "schema_version",
    "successors",
    "upstream_source_path",
}
EXPECTED = {
    "frontdoor-task": (
        "intake.v0",
        "UMEBOSHIISAN/agent-frontdoor",
        (),
        ("governance-handoff",),
    ),
    "governance-handoff": (
        "1.1",
        "UMEBOSHIISAN/workflow-governance-model",
        ("frontdoor-task",),
        ("router-manifest",),
    ),
    "router-manifest": (
        "1.0",
        "UMEBOSHIISAN/mothership-router",
        ("governance-handoff",),
        ("observation-snapshot",),
    ),
    "observation-snapshot": (
        "1.0",
        "UMEBOSHIISAN/secretary-tui",
        ("router-manifest",),
        (),
    ),
}


class ProtocolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = resources.files("mothership.resources")
        self.registry_bytes = self.root.joinpath("protocols/registry.json").read_bytes()
        self.registry = json.loads(self.registry_bytes)

    def test_registry_root_and_order_are_closed(self) -> None:
        self.assertEqual(
            {"schema_version", "protocols"},
            set(self.registry),
        )
        self.assertEqual("mothership.protocol-registry.v1", self.registry["schema_version"])
        entries = self.registry["protocols"]
        self.assertIsInstance(entries, list)
        self.assertEqual(KINDS, tuple(entry["kind"] for entry in entries))
        self.assertEqual(len(KINDS), len({entry["kind"] for entry in entries}))

    def test_every_entry_has_exact_owner_version_and_edges(self) -> None:
        for entry in self.registry["protocols"]:
            kind = entry["kind"]
            version, owner, predecessors, successors = EXPECTED[kind]
            with self.subTest(kind=kind):
                self.assertEqual(ENTRY_KEYS, set(entry))
                self.assertEqual(version, entry["schema_version"])
                self.assertEqual(owner, entry["owner_repository"])
                self.assertEqual(list(predecessors), entry["predecessors"])
                self.assertEqual(list(successors), entry["successors"])
                self.assertEqual("0.2.0", entry["frozen_in_mothership"])
                self.assertIs(False, entry["authority_capable"])
                self.assertIs(False, entry["execution_capable"])
                self.assertRegex(entry["schema_sha256"], r"\A[0-9a-f]{64}\Z")
                self.assertRegex(
                    entry["bundled_schema_path"],
                    r"\Aprotocols/schemas/[a-z0-9.-]+\.json\Z",
                )
                self.assertRegex(
                    entry["upstream_source_path"],
                    r"\A(?:src/[a-z0-9_./-]+|schemas/[a-z0-9_./-]+)\.json\Z",
                )

    def test_schema_digests_match_packaged_bytes(self) -> None:
        for entry in self.registry["protocols"]:
            raw = self.root.joinpath(entry["bundled_schema_path"]).read_bytes()
            with self.subTest(kind=entry["kind"]):
                self.assertEqual(entry["schema_sha256"], hashlib.sha256(raw).hexdigest())
                schema = json.loads(raw)
                self.assertEqual(
                    "https://json-schema.org/draft/2020-12/schema",
                    schema["$schema"],
                )
                self.assertEqual("object", schema["type"])
                self.assertIs(False, schema["additionalProperties"])

    def test_edges_are_reciprocal_and_form_one_chain(self) -> None:
        entries = {entry["kind"]: entry for entry in self.registry["protocols"]}
        for kind, entry in entries.items():
            for predecessor in entry["predecessors"]:
                self.assertIn(kind, entries[predecessor]["successors"])
            for successor in entry["successors"]:
                self.assertIn(kind, entries[successor]["predecessors"])

        visited = []
        current = KINDS[0]
        while current:
            self.assertNotIn(current, visited)
            visited.append(current)
            successors = entries[current]["successors"]
            current = successors[0] if successors else ""
        self.assertEqual(list(KINDS), visited)

    def test_registry_resources_contain_no_private_or_authority_material(self) -> None:
        private_prefix = b"/private" + b"/"
        for entry in self.registry["protocols"]:
            raw = self.root.joinpath(entry["bundled_schema_path"]).read_bytes()
            with self.subTest(kind=entry["kind"]):
                self.assertNotIn(b"/Users/", raw)
                self.assertNotIn(private_prefix, raw)
                self.assertIsNone(
                    re.search(
                        rb'"(?:password|api_key|access_token|private_key)"\s*:',
                        raw,
                        re.IGNORECASE,
                    )
                )


if __name__ == "__main__":
    unittest.main()
