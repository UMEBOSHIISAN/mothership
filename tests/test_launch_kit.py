import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "mothership",
    "agent-frontdoor",
    "workflow-governance-model",
    "mothership-router",
    "secretary-tui",
    "agent-team-runtime",
    "evidence-spine-core",
    "run-lineage-core",
    "source-health-core",
    "agent-decision-core",
    "knowledge-lifecycle-kit",
}


class LaunchKitTests(unittest.TestCase):
    def test_metadata_manifest_is_closed_and_complete(self):
        data = json.loads(
            (ROOT / "docs/launch/repository-metadata.json").read_text("utf-8")
        )
        self.assertEqual(
            {"schema_version", "status", "generated_from", "repositories"},
            set(data),
        )
        self.assertEqual("mothership-metadata-draft.v1", data["schema_version"])
        self.assertEqual("draft-not-applied", data["status"])
        self.assertEqual(EXPECTED, {entry["name"] for entry in data["repositories"]})
        for entry in data["repositories"]:
            self.assertEqual(
                {
                    "name",
                    "description",
                    "topics",
                    "social_preview",
                    "relationship",
                    "homepage",
                    "primary_language",
                    "package_manager",
                    "verified_at",
                    "source_commit",
                },
                set(entry),
            )
            self.assertLessEqual(len(entry["description"]), 350)
            self.assertEqual(len(entry["topics"]), len(set(entry["topics"])))
            self.assertTrue(
                all(topic == topic.lower() and " " not in topic for topic in entry["topics"])
            )
            self.assertNotIn("/Users/", json.dumps(entry))
            self.assertRegex(entry["source_commit"], r"\A[0-9a-f]{40}\Z")
            self.assertIn(entry["package_manager"], {"pip", "npm", "go"})
            expected_relationship = (
                "flagship"
                if entry["name"] == "mothership"
                else "independent-companion-to-mothership"
            )
            self.assertEqual(expected_relationship, entry["relationship"])
