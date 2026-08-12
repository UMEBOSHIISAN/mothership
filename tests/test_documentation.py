from __future__ import annotations

import json
from importlib import metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv


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


def _setuptools_77_available() -> bool:
    try:
        return int(metadata.version("setuptools").split(".", 1)[0]) >= 77
    except (metadata.PackageNotFoundError, TypeError, ValueError):
        return False


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

    def test_legacy_verify_and_demo_evidence_remain_exact(self) -> None:
        for arguments, filename in (
            (("verify",), "verify-output.json"),
            (("demo",), "demo-output.json"),
        ):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as directory:
                completed = subprocess.run(
                    [sys.executable, "-m", "mothership", *arguments],
                    cwd=ROOT,
                    env=_minimal_environment(Path(directory)),
                    input=b"",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(b"", completed.stderr)
                self.assertEqual((GENERATED / filename).read_bytes(), completed.stdout)


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

    @unittest.skipUnless(
        _setuptools_77_available(),
        "setuptools>=77 is required for offline source-install verification",
    )
    def test_quickstart_succeeds_in_an_offline_preprovisioned_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(os.path.realpath(directory))
            source = root / "source"
            shutil.copytree(
                ROOT,
                source,
                ignore=shutil.ignore_patterns(
                    ".git", ".worktrees", ".venv", "__pycache__", "*.pyc", "build", "dist", "*.egg-info",
                ),
            )
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            binary = environment / "bin/python"
            preprovisioned_site_packages = metadata.distribution("setuptools").locate_file("")
            install_environment = _minimal_environment(root)
            install_environment.update(
                {
                    "PIP_NO_INDEX": "1",
                    # pip maps this inverse option onto build_isolation; false disables isolation.
                    "PIP_NO_BUILD_ISOLATION": "false",
                    "PYTHONPATH": str(preprovisioned_site_packages),
                }
            )
            installed = subprocess.run(
                [str(binary), "-m", "pip", "install", "."],
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
                ("demo safe", "flight-safe-output.json"),
            ):
                with self.subTest(command=command):
                    completed = subprocess.run(
                        [str(environment / "bin/mothership"), *command.split()],
                        cwd=root,
                        env=runtime_environment,
                        input=b"",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=10,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
                    self.assertEqual((GENERATED / generated).read_bytes(), completed.stdout)


class SupportingDocumentationTests(unittest.TestCase):
    FILES = {
        "architecture": ROOT / "docs/architecture.md",
        "installation": ROOT / "docs/installation.md",
        "composition": ROOT / "docs/composition.md",
        "protocols": ROOT / "docs/protocols.md",
        "security": ROOT / "docs/security.md",
        "compatibility": ROOT / "docs/compatibility.md",
        "roadmap": ROOT / "docs/ecosystem-roadmap.md",
        "contributing": ROOT / "CONTRIBUTING.md",
        "reporting": ROOT / "SECURITY.md",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = {name: path.read_text("utf-8") for name, path in cls.FILES.items()}

    def test_v02_projection_and_non_authorizing_terms_remain_documented(self) -> None:
        for name in ("architecture", "composition", "protocols", "compatibility"):
            text = self.documents[name]
            with self.subTest(document=name):
                self.assertIn("installable hub", text)
                self.assertIn("independently adoptable", text)
                self.assertIn("authority_effect", text)
                self.assertIn("execution_effect", text)
                positions = [text.index(kind) for kind in (
                    "frontdoor-task", "governance-handoff", "router-manifest", "observation-snapshot",
                )]
                self.assertEqual(sorted(positions), positions)
        for name in ("architecture", "composition", "protocols"):
            self.assertIn("protocol-composition-only", self.documents[name])

    def test_architecture_preserves_resources_and_actual_write_boundary(self) -> None:
        text = self.documents["architecture"]
        for term in (
            "mothership.scope", "mothership.approval", "mothership.adapters", "mothership.contracts",
            "mothership.protocols", "immutable packaged resources", "read-only CLI", "explicit caller-supplied target",
            "legacy compatibility", "explicit output directory",
        ):
            self.assertIn(term, text)
        self.assertNotIn("Flight CLI creates none", text)
        self.assertNotIn("writes only to an explicit target", text)

    def test_installation_preserves_lifecycle_update_and_uninstall_boundaries(self) -> None:
        text = self.documents["installation"]
        for heading in (
            "## Clone-first install", "## Wheel install", "## Editable development install", "## Verify",
            "## Update", "## Uninstall",
        ):
            self.assertIn(heading, text)
        for forbidden in ("sudo ", "install a hook", "shell startup file"):
            self.assertNotIn(forbidden, text.casefold())
        self.assertIn("Installation is the only package-changing step", text)

    def test_protocol_owners_sources_and_update_procedure_remain_closed(self) -> None:
        text = self.documents["protocols"]
        for source in (
            "src/frontdoor/schema/intake.v0.json", "schemas/workflow-handoff.1.1.schema.json",
            "src/mothership_router/schema/router-manifest.1.0.schema.json", "schemas/observation-snapshot.1.0.schema.json",
        ):
            self.assertIn(source, text)
        self.assertIn("mothership protocol validate KIND ABSOLUTE_FILE", text)
        self.assertIn("unknown kind is rejected before file access", text)
        self.assertIn("schema update procedure", text.casefold())

    def test_security_threats_loopback_and_residual_risks_are_explicit(self) -> None:
        text = self.documents["security"]
        for term in (
            "duplicate keys", "malformed UTF-8", "symbolic links", "special files", "oversized input",
            "terminal control", "stale protocol snapshot", "loopback", "Residual risks",
        ):
            self.assertIn(term, text)

    def test_compatibility_roadmap_contribution_and_reporting_bounds_remain_present(self) -> None:
        compatibility = self.documents["compatibility"]
        for term in ("Python 3.12+", "0.2.0", "Measured, not universal", "reachable from its repository's public `main` branch"):
            self.assertIn(term, compatibility)
        self.assertNotIn("publication pending", compatibility.casefold())
        for term in ("TDD", "python3 -m unittest", "schema owner", "SHA-256"):
            self.assertIn(term, self.documents["contributing"])
        self.assertIn("GitHub Security Advisory", self.documents["reporting"])
        self.assertIn("Do not open a public issue", self.documents["reporting"])
        roadmap = self.documents["roadmap"]
        for heading in ("## Shipped in 0.2.0", "## Next candidates", "## Not planned"):
            self.assertIn(heading, roadmap)
        for term in ("automatic companion installation", "model or agent execution", "retry or fallback engine", "credential management", "background service"):
            self.assertIn(term, roadmap)


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

    def test_japanese_claim_limits_private_paths_and_machine_facts_match_english(self) -> None:
        english = README.read_text("utf-8")
        japanese = JAPANESE_README.read_text("utf-8")
        for fact in (
            "Python 3.12+", "0.2.0", "frontdoor-task", "governance-handoff", "router-manifest",
            "observation-snapshot", "authority_effect: false", "execution_effect: false", "claude-code-agent",
            "codex-cli", "ollama-local",
        ):
            self.assertIn(fact, english)
            self.assertIn(fact, japanese)
        for phrase in ("モデルを呼び出しません", "権限を与えません", "自動インストールしません", "合成コーパス", "本番精度ではありません"):
            self.assertIn(phrase, japanese)
        self.assertNotIn("/Users/", japanese)
        self.assertNotIn("/" + "private/", japanese)
        self.assertNotIn("file://", japanese.casefold())
        self.assertIn("public main branchから到達可能", japanese)


if __name__ == "__main__":
    unittest.main()
