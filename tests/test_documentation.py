from __future__ import annotations

import hashlib
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

from orchestration.lib.contracts import validate_contract
from orchestration.lib.external_action import validate_receipt_verification_binding


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
E2E_EVIDENCE = ROOT / "docs/evidence/github-merge-pr-e2e-20260903/README.md"
E2E_EVIDENCE_LINK = "docs/evidence/github-merge-pr-e2e-20260903/README.md"
E2E_EVIDENCE_DIR = E2E_EVIDENCE.parent
GENERATED = ROOT / "docs/generated"
POSITIONING_SENTENCE = (
    "Mothership sits between an AI proposal and a real external consequence. "
    "It binds one human decision to one exact, short-lived, single-use action "
    "while keeping execution and verification separate."
)
EXPECTED_H2 = (
    "Quick start",
    "Validate the 0.2 compatibility chain in 60 seconds",
    "The problem",
    "The Mothership answer",
    "The UME Stack",
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


def _tracked_markdown_paths() -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=10,
    )
    return tuple(
        ROOT / raw.decode("utf-8")
        for raw in completed.stdout.split(b"\0")
        if raw
    )


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

    def test_current_authority_example_is_executable_and_non_executing(self) -> None:
        block = _marked_fence(self.text, "authority-core-example", "python")
        calls = (
            "freeze_action(",
            "validate_decision_transport(",
            "record_action_decision(",
            "consume_action(",
        )
        positions = [block.index(call) for call in calls]
        self.assertEqual(sorted(positions), positions)
        for forbidden in ("subprocess", "requests", "executor", "git push", "gh "):
            self.assertNotIn(forbidden, block.casefold())

        for human_decision, expected_events in ((b"approve\n", 2), (b"reject\n", 1)):
            with self.subTest(decision=human_decision.strip()), tempfile.TemporaryDirectory() as directory:
                os.chmod(directory, 0o755)
                environment = _minimal_environment(Path(directory))
                environment["PYTHONPATH"] = str(ROOT)
                completed = subprocess.run(
                    [sys.executable, "-c", block],
                    cwd=directory,
                    env=environment,
                    input=human_decision,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertIn(b"github.merge_pr", completed.stdout)
                self.assertIn(b"expires_at=", completed.stdout)
                authority_dir = Path(directory, ".mothership-authority")
                self.assertEqual(0o700, authority_dir.stat().st_mode & 0o777)
                events = Path(authority_dir, "authority-action-events.jsonl").read_bytes().splitlines()
                self.assertEqual(expected_events, len(events))
                if human_decision == b"reject\n":
                    self.assertIn(b"no authority was consumed", completed.stdout)

        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as target:
            os.chmod(target, 0o700)
            Path(directory, ".mothership-authority").symlink_to(target, target_is_directory=True)
            environment = _minimal_environment(Path(directory))
            environment["PYTHONPATH"] = str(ROOT)
            completed = subprocess.run(
                [sys.executable, "-c", block],
                cwd=directory,
                env=environment,
                input=b"reject\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertFalse(Path(target, "authority-action-events.jsonl").exists())

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
            "[UME Presence](https://github.com/UMEBOSHIISAN/ume-presence)",
            "UME-HARNESS",
            "mothership.action_authority",
            "FrozenAction",
            "default CLI remains read-only",
            "separately configured bounded executor",
        ):
            self.assertIn(term, self.text)
        self.assertLess(
            self.text.index("[UME Presence](https://github.com/UMEBOSHIISAN/ume-presence)"),
            self.text.index("Legacy 0.2 protocol compatibility"),
        )
        normalized = " ".join(self.text.split())
        self.assertIn(
            "Each product is independently usable. The shared architecture defines responsibility boundaries. "
            "It does not imply automatic runtime integration.",
            normalized,
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


class PublicE2EEvidenceDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README.read_text("utf-8")

    def _evidence(self) -> str:
        self.assertTrue(E2E_EVIDENCE.is_file(), f"missing {E2E_EVIDENCE_LINK}")
        return E2E_EVIDENCE.read_text("utf-8")

    def test_readme_first_screen_order_and_evidence_link_are_exact(self) -> None:
        normalized = " ".join(self.readme.split())
        ordered = (
            'src="assets/mothership-banner.png"',
            "# Mothership",
            "Bounded Action Authority for AI",
            "One human decision. One exact action. One use.",
            POSITIONING_SENTENCE,
            "Public result from one live integration trial — `github.merge_pr`",
            "OBSERVE → PROPOSE → APPROVE → EXECUTE → VERIFY",
            f"]({E2E_EVIDENCE_LINK})",
            "## Quick start",
            "Mothership owns the bounded consequential-authority boundary",
        )
        for value in ordered:
            self.assertIn(value, normalized)
        positions = [normalized.index(value) for value in ordered]
        self.assertEqual(sorted(positions), positions)
        self.assertEqual(1, self.readme.count(f"]({E2E_EVIDENCE_LINK})"))

    def test_evidence_separates_public_facts_from_private_trace_claims(self) -> None:
        evidence = self._evidence()
        public_heading = "## Public evidence"
        sanitized_heading = "## Sanitized lifecycle records"
        private_heading = "## Privately retained lifecycle trace"
        self.assertIn(public_heading, evidence)
        self.assertIn(sanitized_heading, evidence)
        self.assertIn(private_heading, evidence)
        public = evidence.split(public_heading, 1)[1].split(sanitized_heading, 1)[0]
        sanitized = evidence.split(sanitized_heading, 1)[1].split(private_heading, 1)[0]
        private = evidence.split(private_heading, 1)[1]

        for fact in (
            "PR #18",
            "e2e/mothership-merge-canary-base-20260902b",
            "0874166551f11d580168e8b4d0f354e742d39fe6",
            "1cfbbf646b8ac227c8c411f08a961c4396cc69ca",
            "1 file, +5/-0",
            "880e514382b1a9594a9d4a6f06f5939283e57c60",
            "a5fc0d5997199dea2db5800b561e9a972765d27d",
            "Source fork head remained",
            "3edb7363aa14a868313ece2e2eda57ef6643147cd27f54a7199e22c39dc642be",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, public)

        sanitized_lifecycle = (
            "caller-attested human approval",
            "one authority consumption",
            "External Action Receipt",
            "tokenless read-only External Action Verification",
        )
        for claim in sanitized_lifecycle:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, public)
                self.assertIn(claim, sanitized)
        self.assertNotIn("Independent review", public)
        self.assertNotIn("Independent review", sanitized)
        self.assertIn("Independent review", private)
        self.assertIn("DECISION_B_CARD_COPY_TRANSPORT_FRICTION = OPEN", private)
        self.assertIn("Receipt `SUCCESS` is executor-local evidence", sanitized)
        self.assertIn("SANITIZED_LIFECYCLE_RECORDS_PUBLIC = TRUE", private)

    def test_readme_and_evidence_keep_paths_and_claims_bounded(self) -> None:
        evidence = self._evidence()
        for name, text in (("README.md", self.readme), (E2E_EVIDENCE_LINK, evidence)):
            with self.subTest(document=name):
                for forbidden in (
                    "/Users/",
                    "/" + "private/",
                    "file://",
                    "/Volumes/",
                    "local_worker/",
                    "evidence/e2e-",
                ):
                    self.assertNotIn(forbidden, text)

        for nonclaim in (
            "LIVE_EXTERNAL_VERTICAL_GREEN = github.merge_pr PR #18 only",
            "HARNESS_TO_MOTHERSHIP_VERTICAL = NOT_CLAIMED",
            "SECURITY_CLEAN = NOT_CLAIMED",
            "GENERAL_EXECUTOR_SAFETY = NOT_CLAIMED",
            "PRODUCTION_READY = NOT_CLAIMED",
            "PUBLIC_RELEASE_SHIPS_LIVE_ORCHESTRATOR = FALSE",
            "HUMAN_IDENTITY_AUTHENTICATION = NOT_CLAIMED",
            "THIRD_PARTY_REPRODUCIBILITY = NOT_YET",
        ):
            self.assertIn(nonclaim, evidence)
        lowered = evidence.casefold()
        self.assertNotIn("security_clean = true", lowered)
        self.assertNotIn("production-ready", lowered)
        self.assertNotIn("full-stack harness integration is complete", lowered)

    def test_sanitized_evidence_bundle_is_closed_and_action_bound(self) -> None:
        expected_files = {
            "README.md",
            "SHA256SUMS",
            "consume-event.json",
            "executor-receipt.json",
            "frozen-action.json",
            "human-decision.json",
            "manifest.json",
            "public-github-readback.json",
            "verification.json",
        }
        self.assertEqual(
            expected_files,
            {path.name for path in E2E_EVIDENCE_DIR.iterdir() if path.is_file()},
        )

        records = {
            name: json.loads((E2E_EVIDENCE_DIR / name).read_text("utf-8"))
            for name in expected_files
            if name.endswith(".json")
        }
        frozen = records["frozen-action.json"]
        decision = records["human-decision.json"]
        consume = records["consume-event.json"]
        receipt = records["executor-receipt.json"]
        verification = records["verification.json"]["verification"]
        action_id = frozen["action"]["action_id"]
        action_sha256 = frozen["action_sha256"]

        for record in (decision, consume, receipt, verification):
            self.assertEqual(action_id, record["action_id"])
            self.assertEqual(action_sha256, record["action_sha256"])
        self.assertEqual(frozen["expires_at"], decision["expires_at"])
        self.assertEqual(frozen["expires_at"], consume["expires_at"])
        self.assertEqual(consume, validate_contract("authority-action-consume", consume))
        self.assertEqual("SUCCESS", receipt["status"])
        self.assertEqual("CONFIRMED", verification["status"])
        self.assertNotEqual(receipt["status"], verification["status"])
        validated_receipt, validated_verification = validate_receipt_verification_binding(
            receipt,
            verification,
            expected_action_id=action_id,
            expected_action_sha256=action_sha256,
        )
        self.assertEqual(receipt, validated_receipt)
        self.assertEqual(verification, validated_verification)

        parameters = frozen["action"]["execution_parameters"]
        readback = records["public-github-readback.json"]
        self.assertEqual(parameters["repository"], readback["repository"])
        self.assertEqual(parameters["pull_request"], readback["pull_request"])
        self.assertEqual(parameters["expected_head_sha"], readback["head"]["sha"])
        self.assertEqual(parameters["expected_base"], readback["base"]["name"])
        self.assertTrue(readback["merged"])

    def test_sanitized_evidence_hashes_and_manifest_are_exact(self) -> None:
        checksum_lines = (E2E_EVIDENCE_DIR / "SHA256SUMS").read_text("ascii").splitlines()
        expected_hashed_files = {
            "README.md",
            "consume-event.json",
            "executor-receipt.json",
            "frozen-action.json",
            "human-decision.json",
            "manifest.json",
            "public-github-readback.json",
            "verification.json",
        }
        self.assertEqual(len(expected_hashed_files), len(checksum_lines))
        checksums: dict[str, str] = {}
        for line in checksum_lines:
            digest, separator, name = line.partition("  ")
            self.assertEqual("  ", separator)
            self.assertNotIn(name, checksums)
            checksums[name] = digest
        self.assertEqual(expected_hashed_files, set(checksums))
        for name, expected_digest in checksums.items():
            actual_digest = hashlib.sha256((E2E_EVIDENCE_DIR / name).read_bytes()).hexdigest()
            self.assertEqual(expected_digest, actual_digest, name)

        manifest = json.loads((E2E_EVIDENCE_DIR / "manifest.json").read_text("utf-8"))
        published = {
            entry["path"]: entry["sha256"]
            for entry in manifest["published_artifacts"]
        }
        self.assertEqual(len(manifest["published_artifacts"]), len(published))
        self.assertEqual(expected_hashed_files - {"manifest.json"}, set(published))
        for name, expected_digest in published.items():
            self.assertEqual(checksums[name], expected_digest, name)
        self.assertEqual("CONFIRMED", manifest["status"])
        self.assertEqual(1, manifest["request_counts"]["merge_requests"])
        self.assertEqual(0, manifest["request_counts"]["retries"])
        self.assertFalse(manifest["claim_ceiling"]["base_sha_digest_binding"])
        self.assertFalse(
            manifest["claim_ceiling"]["public_release_ships_live_orchestrator"]
        )


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
            "UME Presence",
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

    def test_markdown_does_not_publish_creator_absolute_paths(self) -> None:
        for path in _tracked_markdown_paths():
            text = path.read_text("utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("/Users/umeboshi", text)

    def test_presence_public_status_is_consistent(self) -> None:
        for path in _tracked_markdown_paths():
            text = path.read_text("utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("UME Presence (private", text)

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
