from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
JAPANESE_README = ROOT / "docs/ja/README.md"
GENERATED = ROOT / "docs/generated"
EXPECTED_H2 = (
    "See agent scope drift in 60 seconds",
    "What Mothership proves",
    "The flight lifecycle",
    "Quick start",
    "Import and verify a run",
    "Authority as Data",
    "Safety guarantees",
    "What Mothership is not",
    "Architecture",
    "Public API",
    "Ecosystem protocols",
    "Compatibility",
    "Documentation",
    "Contributing",
    "Security",
    "Roadmap",
    "License",
)
QUICKSTART = (
    "python3 -m venv .venv",
    ". .venv/bin/activate",
    "python -m pip install .",
    "mothership verify",
    "mothership demo safe",
)
LIFECYCLE = (
    "Intent",
    "Scope",
    "Decision",
    "Approval binding",
    "Execution receipt",
    "Result evidence",
    "Verification",
    "Persistence proof",
    "Reusable asset (optional)",
)
VERDICTS = ("COMPLETE", "INCOMPLETE", "DRIFTED", "INVALID")


def _marked_fence(text: str, name: str, language: str) -> str:
    start = f"<!-- {name}:start -->\n```{language}\n"
    end = f"\n```\n<!-- {name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError(f"expected exactly one {name} fence")
    return text.split(start, 1)[1].split(end, 1)[0]


class GeneratedDocumentationTests(unittest.TestCase):
    def test_generated_outputs_are_exact_current_cli_bytes(self) -> None:
        # A changed CLI transcript must force its checked-in evidence to change too.
        commands = (
            (("demo", "safe"), "flight-safe-output.json", 0),
            (("demo", "drift"), "flight-drift-output.json", 21),
            (("report", "mothership/resources/flight/safe-run", "--format", "markdown"),
             "flight-safe-report.md", 0),
        )
        for arguments, filename, exit_code in commands:
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, "-m", "mothership", *arguments],
                    cwd=ROOT,
                    input=b"",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=10,
                )
                expected = (GENERATED / filename).read_bytes()
                self.assertEqual(exit_code, completed.returncode, completed.stderr)
                self.assertEqual(b"", completed.stderr)
                self.assertEqual(expected, completed.stdout)
                self.assertTrue(expected.endswith(b"\n"))
                self.assertFalse(expected.endswith(b"\n\n"))


class ReadmeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text("utf-8")

    def test_root_readme_has_the_proof_first_section_order_and_exact_hero(self) -> None:
        headings = tuple(line[3:] for line in self.text.splitlines() if line.startswith("## "))
        self.assertEqual(EXPECTED_H2, headings)
        self.assertIn("The black box for AI agents.\nKnow what your agents were allowed to do—and prove what actually happened.", self.text)

    def test_readme_embeds_generated_evidence_and_the_complete_lifecycle(self) -> None:
        self.assertEqual(
            (GENERATED / "flight-safe-output.json").read_text("utf-8").rstrip("\n"),
            _marked_fence(self.text, "flight-safe-output", "json"),
        )
        self.assertEqual(
            (GENERATED / "flight-drift-output.json").read_text("utf-8").rstrip("\n"),
            _marked_fence(self.text, "flight-drift-output", "json"),
        )
        positions = [self.text.index(value) for value in LIFECYCLE]
        self.assertEqual(positions, sorted(positions))
        for verdict in VERDICTS:
            self.assertIn(f"`{verdict}`", self.text)
        self.assertIn(
            "docs/superpowers/specs/2026-08-12-mothership-flight-recorder-design.md",
            self.text,
        )
        disclaimer = (
            "This report verifies supplied records; it does not grant authority or prove "
            "unobserved real-world actions."
        )
        self.assertIn(disclaimer, (GENERATED / "flight-safe-report.md").read_text("utf-8"))
        self.assertIn(disclaimer, self.text)

    def test_quickstart_is_the_clone_first_sequence(self) -> None:
        self.assertEqual(QUICKSTART, tuple(_marked_fence(self.text, "quickstart", "sh").splitlines()))

    def test_claims_and_private_paths_remain_closed(self) -> None:
        lowered = self.text.casefold()
        for forbidden in (
            "guaranteed secure",
            "production-ready",
            "autonomous execution",
            "certified",
            "10,000 stars",
            "10000 stars",
            "/users/",
            "/" + "private/",
            "file://",
        ):
            self.assertNotIn(forbidden, lowered)


class JapaneseGuideTests(unittest.TestCase):
    def test_japanese_onboarding_has_primary_copy_and_machine_facts(self) -> None:
        text = JAPANESE_README.read_text("utf-8")
        self.assertIn("AIエージェントのブラックボックス。\n何が許可され、実際に何が起きたかを、証拠から検証する。", text)
        self.assertEqual(QUICKSTART, tuple(_marked_fence(text, "quickstart-ja", "sh").splitlines()))
        self.assertEqual(
            _marked_fence(README.read_text("utf-8"), "flight-safe-output", "json"),
            _marked_fence(text, "flight-safe-output-ja", "json"),
        )
        self.assertEqual(
            _marked_fence(README.read_text("utf-8"), "flight-drift-output", "json"),
            _marked_fence(text, "flight-drift-output-ja", "json"),
        )
        for value in (*LIFECYCLE, *VERDICTS):
            self.assertIn(value, text)
        self.assertNotIn("unimplemented adapter", text.casefold())


if __name__ == "__main__":
    unittest.main()
