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
    "Validate the 0.2 compatibility chain in 60 seconds",
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

    def test_legacy_demo_and_boundary_map_do_not_overstate_current_coverage(self) -> None:
        self.assertNotIn("whole control plane", self.text.casefold())
        self.assertNotIn("one fictional document at every boundary", self.text.casefold())
        self.assertNotIn("assets/boundary-map.svg", self.text)

    def test_hero_links_and_companion_topology_are_exact(self) -> None:
        self.assertIn(
            "Bounded Action Authority for AI",
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

    def test_current_authority_boundary_precedes_legacy_compatibility(self) -> None:
        for term in (
            "Mothership owns the bounded consequential-authority boundary",
            "UME Persona (private)",
            "UME-HARNESS",
            "mothership.action_authority",
            "FrozenAction",
            "default CLI remains read-only",
            "separately configured bounded executor",
        ):
            self.assertIn(term, self.text)
        self.assertLess(
            self.text.index("UME Persona (private)"),
            self.text.index("Legacy 0.2 protocol compatibility"),
        )
        for stale_claim in (
            "turn a recommendation into permission",
            "| Grants authority | no |",
            "Execution authority is a separate, unconnected concern",
        ):
            self.assertNotIn(stale_claim, self.text)

    def test_claims_and_rendering_structure_are_closed(self) -> None:
        lowered = self.text.casefold()
        self.assertIn(
            "https://github.com/UMEBOSHIISAN/mothership/actions/workflows/test.yml/badge.svg",
            self.text,
        )
        self.assertNotIn("tests-225%20passing", self.text)
        self.assertIn("reachable from their public main branches", lowered)
        self.assertNotIn("publication-pending", lowered)
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


class SupportingDocumentationTests(unittest.TestCase):
    FILES = {
        "architecture": ROOT / "docs/architecture.md",
        "installation": ROOT / "docs/installation.md",
        "composition": ROOT / "docs/composition.md",
        "protocols": ROOT / "docs/protocols.md",
        "security": ROOT / "docs/security.md",
        "physical_e2e": ROOT / "docs/physical-e2e.md",
        "compatibility": ROOT / "docs/compatibility.md",
        "roadmap": ROOT / "docs/ecosystem-roadmap.md",
        "contributing": ROOT / "CONTRIBUTING.md",
        "reporting": ROOT / "SECURITY.md",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = {
            name: path.read_text("utf-8")
            for name, path in cls.FILES.items()
        }

    def test_canonical_terms_and_non_authorizing_chain_agree(self) -> None:
        architecture = self.documents["architecture"]
        for term in (
            "UME Persona (private)",
            "UME-HARNESS",
            "MOTHERSHIP",
            "FrozenAction",
            "one-shot consume",
            "separately configured bounded executor",
        ):
            self.assertIn(term.casefold(), architecture.casefold())

        for name in ("composition", "protocols", "compatibility"):
            text = self.documents[name]
            with self.subTest(document=name):
                self.assertIn("0.2 compatibility surface", text.casefold())
                self.assertIn("authority_effect", text)
                self.assertIn("execution_effect", text)
                positions = [text.index(kind) for kind in (
                    "frontdoor-task",
                    "governance-handoff",
                    "router-manifest",
                    "observation-snapshot",
                )]
                self.assertEqual(sorted(positions), positions)
        for name in ("composition", "protocols"):
            self.assertIn("protocol-composition-only", self.documents[name])

        all_text = "\n".join(self.documents.values()).casefold()
        for contradiction in (
            "validation grants approval",
            "automatically installs companions",
            "automatically routes work",
            "invokes a model automatically",
        ):
            self.assertNotIn(contradiction, all_text)

    def test_architecture_documents_modules_resources_and_write_boundaries(self) -> None:
        text = self.documents["architecture"]
        for term in (
            "mothership.scope",
            "mothership.approval",
            "mothership.action_authority",
            "mothership.adapters",
            "mothership.contracts",
            "mothership.protocols",
            "immutable packaged resources",
            "read-only CLI",
            "explicit caller-supplied target",
            "Legacy 0.2 Protocol Compatibility",
        ):
            self.assertIn(term, text)

    def test_installation_covers_every_lifecycle_and_side_effect(self) -> None:
        text = self.documents["installation"]
        for heading in (
            "## Clone-first install",
            "## Wheel install",
            "## Editable development install",
            "## Verify",
            "## Update",
            "## Uninstall",
        ):
            self.assertIn(heading, text)
        for forbidden in ("sudo ", "install a hook", "shell startup file"):
            self.assertNotIn(forbidden, text.casefold())
        self.assertIn("Installation is the only package-changing step", text)

    def test_protocol_reference_has_owner_source_version_and_failure_contract(self) -> None:
        text = self.documents["protocols"]
        for source in (
            "src/frontdoor/schema/intake.v0.json",
            "schemas/workflow-handoff.1.1.schema.json",
            "src/mothership_router/schema/router-manifest.1.0.schema.json",
            "schemas/observation-snapshot.1.0.schema.json",
        ):
            self.assertIn(source, text)
        self.assertIn("mothership protocol validate KIND ABSOLUTE_FILE", text)
        self.assertIn("unknown kind is rejected before file access", text)
        self.assertIn("schema update procedure", text.casefold())

    def test_security_threat_model_and_residual_risks_are_explicit(self) -> None:
        text = self.documents["security"]
        for threat in (
            "duplicate keys",
            "malformed UTF-8",
            "symbolic links",
            "special files",
            "oversized input",
            "terminal control",
            "stale protocol snapshot",
            "loopback",
            "Residual risks",
            "Decision Plane",
            "Action Authority Plane",
            "Execution Plane",
            "one-shot",
            "replay",
            "separately configured bounded executor",
            "does not authenticate human identity",
            "trusted, non-rollbackable live ledger",
        ):
            self.assertIn(threat, text)

    def test_action_authority_claim_limits_are_explicit(self) -> None:
        architecture = self.documents["architecture"]
        for term in (
            "issuing interpreter lineage",
            "cannot be reconstructed",
            "child forked after issuance",
            "(consume event, exact validated action)",
        ):
            self.assertIn(term, architecture)

        security = self.documents["security"]
        for term in (
            "does not fsync the parent directory",
            "new directory entry is not claimed crash-durable",
            "rolled back or restored",
            "fresh action_id for every freeze",
            "exact live issuance",
        ):
            self.assertIn(term, security)

        physical = self.documents["physical_e2e"]
        self.assertIn("operator-observed", physical)
        self.assertIn("not independently reproducible", physical)

    def test_compatibility_contribution_reporting_and_roadmap_are_bounded(self) -> None:
        compatibility = self.documents["compatibility"]
        self.assertIn("Python 3.12+", compatibility)
        self.assertIn("0.2.0", compatibility)
        self.assertIn("Measured, not universal", compatibility)
        self.assertIn("reachable from its repository's public `main` branch", compatibility)
        self.assertNotIn("publication pending", compatibility.casefold())

        contributing = self.documents["contributing"]
        for term in ("TDD", "python3 -m unittest", "schema owner", "SHA-256"):
            self.assertIn(term, contributing)

        reporting = self.documents["reporting"]
        self.assertIn("GitHub Security Advisory", reporting)
        self.assertIn(
            "https://github.com/UMEBOSHIISAN/mothership/security/advisories/new",
            reporting,
        )
        self.assertIn("Do not open a public issue", reporting)

        roadmap = self.documents["roadmap"]
        for heading in ("## Implemented", "## Candidates", "## Not current or planned"):
            self.assertIn(heading, roadmap)
        for excluded in (
            "automatic companion installation",
            "model or agent execution",
            "automatic retry or fallback",
            "credential management",
            "background service",
            "ambient or global authority",
        ):
            self.assertIn(excluded, roadmap)
        for implemented in (
            "FrozenAction",
            "caller-attested human decision",
            "short TTL",
            "trusted, non-rollbackable live ledger",
        ):
            self.assertIn(implemented, roadmap)


class JapaneseGuideTests(unittest.TestCase):
    JAPANESE_H2 = (
        "クイックスタート",
        "0.2互換チェーンを60秒で検証",
        "課題",
        "Mothershipの答え",
        "アーキテクチャ",
        "導入パス",
        "安全保証",
        "Mothershipではないもの",
        "比較",
        "公開API",
        "エコシステムプロトコル",
        "互換性",
        "ドキュメント",
        "コントリビューション",
        "セキュリティ",
        "ロードマップ",
        "ライセンス",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.english = README.read_text("utf-8")
        cls.japanese = (ROOT / "docs/ja/README.md").read_text("utf-8")

    def test_japanese_product_story_has_complete_section_parity(self) -> None:
        headings = tuple(
            line.removeprefix("## ")
            for line in self.japanese.splitlines()
            if line.startswith("## ")
        )
        self.assertEqual(self.JAPANESE_H2, headings)

    def test_japanese_demo_is_scoped_to_the_compatibility_chain(self) -> None:
        self.assertNotIn("60秒で全体を確認", self.japanese)
        self.assertNotIn("4つの境界に置かれた架空の文書", self.japanese)
        self.assertIn("0.2互換チェーン", self.japanese)

    def test_quickstart_and_demo_bytes_match_english_contract(self) -> None:
        self.assertEqual(
            QUICKSTART,
            tuple(_marked_fence(self.japanese, "quickstart-ja", "sh").splitlines()),
        )
        japanese_demo = _marked_fence(self.japanese, "demo-output-ja", "json")
        english_demo = _marked_fence(self.english, "demo-output", "json")
        self.assertEqual(english_demo, japanese_demo)
        self.assertEqual(
            (GENERATED / "demo-output.json").read_text("utf-8").rstrip("\n"),
            japanese_demo,
        )

    def test_cross_language_machine_facts_are_identical(self) -> None:
        for fact in (
            "Python 3.12+",
            "0.2.0",
            "mothership.action_authority",
            "github.merge_pr",
            "frontdoor-task",
            "governance-handoff",
            "router-manifest",
            "observation-snapshot",
            "authority_effect: false",
            "execution_effect: false",
            "claude-code-agent",
            "codex-cli",
            "ollama-local",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, self.english)
                self.assertIn(fact, self.japanese)
        for companion in (
            "https://github.com/UMEBOSHIISAN/agent-frontdoor",
            "https://github.com/UMEBOSHIISAN/workflow-governance-model",
            "https://github.com/UMEBOSHIISAN/mothership-router",
            "https://github.com/UMEBOSHIISAN/secretary-tui",
        ):
            self.assertIn(companion, self.japanese)
        positions = [self.japanese.index(kind) for kind in (
            "frontdoor-task",
            "governance-handoff",
            "router-manifest",
            "observation-snapshot",
        )]
        self.assertEqual(sorted(positions), positions)

    def test_japanese_guide_preserves_claim_limits(self) -> None:
        for phrase in (
            "モデルを呼び出しません",
            "Mothershipは、範囲を限定したconsequential authorityの境界を所有します",
            "default CLIはread-onlyのままです",
            "別途設定されたbounded executor",
            "自動インストールしません",
            "合成コーパス",
            "本番精度ではありません",
        ):
            self.assertIn(phrase, self.japanese)
        self.assertNotIn("/Users/", self.japanese)
        self.assertNotIn("/" + "private/", self.japanese)
        self.assertNotIn("file://", self.japanese.casefold())
        self.assertIn("public main branchから到達可能", self.japanese)
        self.assertNotIn("publication pending", self.japanese.casefold())


if __name__ == "__main__":
    unittest.main()
