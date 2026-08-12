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
    def test_rollout_documents_do_not_publish_the_local_username(self):
        paths = (
            ROOT / "docs/superpowers/plans/2026-08-12-mothership-10000-stars-wave2-proof-products.md",
            ROOT / "docs/superpowers/plans/2026-08-12-mothership-10000-stars-wave3-focused-primitives.md",
        )
        for path in paths:
            self.assertNotIn("/Users/umeboshi/", path.read_text("utf-8"))

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

    def test_launch_copy_is_bilingual_proof_first_and_non_authorizing(self):
        english = (ROOT / "docs/launch/announcement-en.md").read_text("utf-8")
        japanese = (ROOT / "docs/launch/announcement-ja.md").read_text("utf-8")
        outline = (ROOT / "docs/launch/article-outline.md").read_text("utf-8")
        release = (ROOT / "docs/launch/release-notes.md").read_text("utf-8")
        for text in (english, japanese):
            self.assertIn("mothership demo safe", text)
            self.assertIn("mothership demo drift", text)
            self.assertIn("COMPLETE", text)
            self.assertIn("DRIFTED", text)
            self.assertIn("does not grant authority", text)
            self.assertNotIn("10,000 stars", text)
            self.assertNotIn("production-ready", text.casefold())
            self.assertEqual(1, text.count("https://github.com/UMEBOSHIISAN/mothership"))
        for heading in (
            "Why AI agents need a flight recorder",
            "A success message is not evidence",
            "Authority as data",
            "Safe flight",
            "Drifted flight",
            "What Mothership does not do",
        ):
            self.assertIn(heading, outline)
        for value in (
            "Mothership Flight Recorder",
            "mothership demo safe",
            "mothership demo drift",
            "Local draft — not published",
        ):
            self.assertIn(value, release)

    def test_square_social_card_is_exact_png(self):
        data = (ROOT / "assets/mothership-flight-recorder-square.png").read_bytes()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
        self.assertEqual(
            (1080, 1080),
            tuple(int.from_bytes(data[n : n + 4], "big") for n in (16, 20)),
        )

    def test_publication_checklist_separates_local_and_remote_evidence(self):
        checklist = (ROOT / "docs/launch/publication-checklist.md").read_text("utf-8")
        prompt = (ROOT / "docs/launch/community-prompt.md").read_text("utf-8")
        for value in (
            "commit exists locally",
            "commit reached origin",
            "rendered README",
            "repository description",
            "topics",
            "social preview",
            "release reachability",
            "star count",
            "GitHub traffic remains UNKNOWN",
        ):
            self.assertIn(value, checklist)
        for value in (
            "remove secrets",
            "remove private paths",
            "synthetic reproduction",
            "do not paste credentials",
        ):
            self.assertIn(value, prompt)
