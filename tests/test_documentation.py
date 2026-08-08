from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import venv


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
GENERATED = ROOT / "docs/generated"
EXPECTED_H2 = (
    "Quick start",
    "See the whole control plane in 60 seconds",
    "The problem",
    "The Mothership answer",
    "Architecture",
    "Choose your adoption path",
    "Safety guarantees",
    "What Mothership is not",
    "How it compares",
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
    "mothership demo",
)


def _minimal_environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "7",
    }


def _marked_fence(text: str, name: str, language: str) -> str:
    pattern = re.compile(
        rf"<!-- {re.escape(name)}:start -->\n```{language}\n(.*?)\n```\n"
        rf"<!-- {re.escape(name)}:end -->",
        re.DOTALL,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one {name} fence")
    return matches[0]


class GeneratedDocumentationTests(unittest.TestCase):
    def _run(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                [sys.executable, "-m", "mothership", *arguments],
                cwd=ROOT,
                env=_minimal_environment(Path(directory)),
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )

    def test_generated_outputs_are_exact_current_cli_bytes(self) -> None:
        for arguments, filename in (
            (("verify",), "verify-output.json"),
            (("demo",), "demo-output.json"),
        ):
            with self.subTest(arguments=arguments):
                expected = (GENERATED / filename).read_bytes()
                completed = self._run(*arguments)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(b"", completed.stderr)
                self.assertEqual(expected, completed.stdout)
                self.assertIsInstance(json.loads(expected), dict)
                self.assertTrue(expected.endswith(b"\n"))
                self.assertFalse(expected.endswith(b"\n\n"))


class ReadmeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text("utf-8")

    def test_product_narrative_has_exact_h2_order(self) -> None:
        headings = tuple(
            line.removeprefix("## ")
            for line in self.text.splitlines()
            if line.startswith("## ")
        )
        self.assertEqual(EXPECTED_H2, headings)

    def test_quickstart_is_one_exact_executable_block(self) -> None:
        block = _marked_fence(self.text, "quickstart", "sh")
        commands = tuple(
            line.strip()
            for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertEqual(QUICKSTART, commands)
        self.assertEqual(1, self.text.count("<!-- quickstart:start -->"))
        self.assertEqual(1, self.text.count("<!-- quickstart:end -->"))

    def test_embedded_demo_is_the_generated_transcript(self) -> None:
        transcript = _marked_fence(self.text, "demo-output", "json")
        expected = (GENERATED / "demo-output.json").read_text("utf-8").rstrip("\n")
        self.assertEqual(expected, transcript)
        self.assertEqual("protocol-composition-only", json.loads(transcript)["claim"])

    def test_hero_links_and_companion_topology_are_exact(self) -> None:
        self.assertIn(
            "The portable, safety-first control plane for AI coding environments.",
            self.text,
        )
        for target in (
            "docs/installation.md",
            "docs/architecture.md",
            "docs/composition.md",
            "docs/protocols.md",
            "docs/security.md",
            "docs/compatibility.md",
            "docs/ecosystem-roadmap.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "docs/ja/README.md",
            "LICENSE",
        ):
            self.assertIn(f"]({target})", self.text)
        companions = (
            "https://github.com/UMEBOSHIISAN/agent-frontdoor",
            "https://github.com/UMEBOSHIISAN/workflow-governance-model",
            "https://github.com/UMEBOSHIISAN/mothership-router",
            "https://github.com/UMEBOSHIISAN/secretary-tui",
        )
        for companion in companions:
            self.assertIn(companion, self.text)
        positions = [self.text.index(kind) for kind in (
            "frontdoor-task",
            "governance-handoff",
            "router-manifest",
            "observation-snapshot",
        )]
        self.assertEqual(sorted(positions), positions)

    def test_claims_and_rendering_structure_are_closed(self) -> None:
        lowered = self.text.casefold()
        for forbidden in (
            "production ready",
            "production-ready",
            "automatically installs",
            "autonomous execution",
            "guaranteed secure",
            "10,000 stars",
            "10000 stars",
        ):
            self.assertNotIn(forbidden, lowered)
        self.assertNotIn("/Users/", self.text)
        self.assertNotIn("/" + "private/", self.text)
        self.assertNotIn("file://", lowered)

        headings = [line for line in self.text.splitlines() if line.startswith("#")]
        self.assertEqual(1, sum(line.startswith("# ") for line in headings))
        previous = 0
        anchors: set[str] = set()
        for heading in headings:
            level = len(heading) - len(heading.lstrip("#"))
            self.assertLessEqual(level, previous + 1 if previous else 1)
            previous = level
            title = heading[level:].strip().casefold()
            anchor = re.sub(r"[^a-z0-9 _-]", "", title).replace(" ", "-")
            self.assertNotIn(anchor, anchors)
            anchors.add(anchor)
        image_alts = re.findall(r"!\[([^]]*)\]\([^)]+\)", self.text)
        image_alts.extend(re.findall(r"<img\s+[^>]*alt=\"([^\"]+)\"", self.text))
        self.assertTrue(image_alts)
        self.assertTrue(all(len(alt.strip()) >= 5 for alt in image_alts))

        in_fence = False
        for number, line in enumerate(self.text.splitlines(), 1):
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or line.startswith(("[!", "<img", "  <img")) or "https://" in line:
                continue
            self.assertLessEqual(len(line), 120, f"README line {number} is too long")

    def test_quickstart_succeeds_in_an_isolated_preprovisioned_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(
                ROOT,
                source,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".worktrees",
                    ".venv",
                    "__pycache__",
                    "*.pyc",
                    "build",
                    "dist",
                    "*.egg-info",
                ),
            )
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            binary = environment / "bin/python"
            install_environment = _minimal_environment(root)
            install_environment.update(
                {
                    "PIP_NO_INDEX": "1",
                    "PYTHONPATH": sysconfig.get_paths()["purelib"],
                }
            )
            installed = subprocess.run(
                [str(binary), "-m", "pip", "install", "--no-build-isolation", "."],
                cwd=source,
                env=install_environment,
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(0, installed.returncode, installed.stderr.decode("utf-8", "replace"))

            runtime_environment = _minimal_environment(root)
            for command, generated in (
                ("verify", "verify-output.json"),
                ("demo", "demo-output.json"),
            ):
                completed = subprocess.run(
                    [str(environment / "bin/mothership"), command],
                    cwd=root,
                    env=runtime_environment,
                    input=b"",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual((GENERATED / generated).read_bytes(), completed.stdout)


if __name__ == "__main__":
    unittest.main()
