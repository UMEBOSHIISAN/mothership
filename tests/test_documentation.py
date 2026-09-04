from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
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
README_EN = ROOT / "README.en.md"
PUBLIC_RESULT_IMAGE = ROOT / "assets/readme/ja/pr18-public-result.svg"
EXPLAINER_GIF = ROOT / "assets/readme/ja/mothership-flow.gif"
EXPLAINER_POSTER = ROOT / "assets/readme/ja/mothership-flow-poster.png"
ASSET_BUILD = ROOT / "assets/readme/source/asset-build.toml"
ASSET_FONT = ROOT / "assets/readme/source/fonts/NotoSansJP-Regular.ttf"
EXPECTED_POSITIONING_ASSETS = (
    "assets/readme/ja/mothership-flow.gif",
    "assets/readme/ja/mothership-flow-poster.png",
    "assets/readme/en/mothership-flow.gif",
    "assets/readme/en/mothership-flow-poster.png",
    "assets/readme/ja/ume-stack-responsibility.svg",
    "assets/readme/en/ume-stack-responsibility.svg",
    "assets/readme/en/pr18-public-result.svg",
)
E2E_EVIDENCE = ROOT / "docs/evidence/github-merge-pr-e2e-20260903/README.md"
E2E_EVIDENCE_LINK = "docs/evidence/github-merge-pr-e2e-20260903/README.md"
E2E_EVIDENCE_DIR = E2E_EVIDENCE.parent
GENERATED = ROOT / "docs/generated"
QUICKSTART = (
    "python3 -m venv .venv",
    ". .venv/bin/activate",
    "python -m pip install .",
    "python examples/authority_core_walkthrough.py",
    "mothership verify",
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


def _gif_metadata(path: Path) -> tuple[tuple[int, int], int, int, frozenset[int]]:
    """Return dimensions, frame count, duration ms, and frame delays for a GIF."""
    data = path.read_bytes()
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise AssertionError(f"not a GIF: {path}")
    dimensions = struct.unpack("<HH", data[6:10])
    packed = data[10]
    offset = 13
    if packed & 0x80:
        offset += 3 * (2 ** ((packed & 0x07) + 1))

    delays: list[int] = []
    pending_delay = 0

    def skip_sub_blocks(start: int) -> int:
        while True:
            size = data[start]
            start += 1
            if size == 0:
                return start
            start += size

    while offset < len(data):
        marker = data[offset]
        offset += 1
        if marker == 0x3B:
            break
        if marker == 0x21:
            label = data[offset]
            offset += 1
            if label == 0xF9:
                block_size = data[offset]
                if block_size != 4:
                    raise AssertionError(f"invalid GIF control block: {path}")
                pending_delay = struct.unpack("<H", data[offset + 2:offset + 4])[0] * 10
                offset += 1 + block_size
                if data[offset] != 0:
                    raise AssertionError(f"unterminated GIF control block: {path}")
                offset += 1
            else:
                offset = skip_sub_blocks(offset)
            continue
        if marker != 0x2C:
            raise AssertionError(f"unexpected GIF marker 0x{marker:02x}: {path}")
        local_packed = data[offset + 8]
        offset += 9
        if local_packed & 0x80:
            offset += 3 * (2 ** ((local_packed & 0x07) + 1))
        offset += 1
        offset = skip_sub_blocks(offset)
        delays.append(pending_delay)
        pending_delay = 0

    return dimensions, len(delays), sum(delays), frozenset(delays)


def _asset_contract(path: Path) -> dict[str, object]:
    """Parse the flat JSON-compatible values used by the asset TOML contract."""
    text = path.read_text("utf-8")
    entries = re.finditer(
        r"(?ms)^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)(?=^[A-Za-z_][A-Za-z0-9_]*\s*=|\Z)",
        text,
    )
    return {match.group(1): json.loads(match.group(2).strip()) for match in entries}


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
        self.assertEqual(
            (
                "PURPOSE",
                "責務分担",
                "CURRENT: v0.4.1",
                "現在のMothership Core",
                "現在の参照profile",
                "公開結果の一例",
                "クイックスタート",
                "現在の制約",
                "詳細ドキュメント",
                "License",
            ),
            headings,
        )
        english = README_EN.read_text("utf-8")
        english_headings = tuple(
            line.removeprefix("## ")
            for line in english.splitlines()
            if line.startswith("## ")
        )
        self.assertEqual(
            (
                "PURPOSE",
                "Responsibility split",
                "CURRENT: v0.4.1",
                "How the current Mothership Core works",
                "Current reference profile",
                "One public result",
                "Quick start",
                "Current limitations",
                "Documentation",
                "License",
            ),
            english_headings,
        )

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

    def test_reference_positioning_and_scope_are_explicit(self) -> None:
        for phrase in (
            "人間が全部を抱えず、AIにも全部を明け渡さない。",
            "「どこまで任せるか」を曖昧にしない。",
            "現実を変える権限を限定的に受け渡す",
            "リファレンス実装",
            "github.merge_pr",
            "base commit SHAは結び付けられません",
            "`expires_at`はaction digestに含まれません",
            "毎回新しい `action_id` を発行",
            "表示した発行情報と期限へ応答を対応付け",
            "人間の本人確認は行いません",
            "信頼されたローカル台帳履歴",
            "本番運用または規制対象の高リスク用途への適合",
        ):
            self.assertIn(phrase, self.text)

    def test_shared_responsibility_copy_matches_current_surfaces(self) -> None:
        composition = (ROOT / "docs/composition.md").read_text("utf-8")
        japanese_map = (ROOT / "assets/readme/ja/ume-stack-responsibility.svg").read_text("utf-8")
        english_map = (ROOT / "assets/readme/en/ume-stack-responsibility.svg").read_text("utf-8")
        self.assertIn("UME-HARNESS turns human intent into a bounded local-work preview.", composition)
        self.assertIn("Mothership binds a human decision to bounded authority for one external action.", composition)
        self.assertIn("ローカル作業のプレビュー", japanese_map)
        self.assertIn("Visible scope / confirmation", english_map)
        self.assertIn("方向性・未実装", japanese_map)
        self.assertIn("DIRECTION / NOT_SHIPPED", english_map)
        self.assertNotIn("やる / 確認 / しない", japanese_map)
        self.assertNotIn("Will do / confirm / will not do", english_map)
        purpose = self.text.split("## PURPOSE", 1)[1].split("## 責務分担", 1)[0]
        self.assertNotIn("github.merge_pr", purpose)
        self.assertNotIn("医療製品", self.text)

    def test_authority_flow_and_decision_cardinality_match_v0_4_1(self) -> None:
        english = README_EN.read_text("utf-8")

        for phrase in (
            "現在の公開版同士に自動接続はありません。破線部分は未実装です。",
            "proposalとevidenceは判断材料ですが、FrozenActionへ機械的に結び付けられません",
            "同じactionへ複数のdecision eventを記録できる",
            "同じaction IDは同じ台帳履歴内で一度だけconsumeできる",
        ):
            self.assertIn(phrase, self.text)

        for phrase in (
            "The current public releases have no automatic runtime bridge. The dashed connection is not implemented.",
            "Proposal and evidence are decision context, but they are not mechanically bound to a FrozenAction",
            "Multiple decision events may be recorded for the same action",
            "one consume per action ID in one trusted ledger history",
        ):
            self.assertIn(phrase, english)
        self.assertNotIn("権限の受け渡しを具体的に閉じた", self.text)
        self.assertNotIn("closed end to end", english)
        self.assertIn("5つの実行パラメータ", self.text)
        self.assertIn("five execution parameters", english)
        self.assertIn("issue a fresh `action_id` for every freeze", english)
        self.assertIn("correlate the response to the exact live issuance and displayed expiry", english)

    def test_public_result_and_links_are_bounded(self) -> None:
        self.assertIn(f"]({E2E_EVIDENCE_LINK})", self.text)
        for target in (
            "docs/architecture.md",
            "docs/installation.md",
            "docs/protocols.md",
            "docs/security.md",
            "docs/composition.md",
            "docs/evidence/github-merge-pr-e2e-20260903/README.md",
            "README.en.md",
            "LICENSE",
        ):
            self.assertIn(f"]({target})", self.text)
        self.assertEqual(1, self.text.count(f"]({E2E_EVIDENCE_LINK})"))
        self.assertIn("一例です", self.text)
        self.assertIn("汎用的な安全性", self.text)
        self.assertIn("本番運用への適合は主張しません", self.text)

    def test_public_result_image_is_deterministic_and_sanitized(self) -> None:
        self.assertTrue(PUBLIC_RESULT_IMAGE.is_file())
        image = PUBLIC_RESULT_IMAGE.read_text("utf-8")
        for value in (
            "PR #18",
            "e2e/mothership-merge-canary-base-20260902b",
            "0874166551f11d580168e8b4d0f354e742d39fe6",
            "1cfbbf646b8ac227c8c411f08a961c4396cc69ca",
            "1ファイル・+5 / -0",
            "公開本線は操作対象外",
        ):
            self.assertIn(value, image)
        for forbidden in ("/Users/", "/" + "private/", "token", "secret"):
            self.assertNotIn(forbidden.casefold(), image.casefold())
        self.assertIn('role="img"', image)
        self.assertIn('viewBox="0 0 720 760"', image)
        self.assertIn("alt", self.text)
        self.assertIn("assets/readme/ja/pr18-public-result.svg", self.text)
        self.assertIn('width="720"', self.text)
        english = README_EN.read_text("utf-8")
        english_image = (ROOT / "assets/readme/en/pr18-public-result.svg").read_text("utf-8")
        for value in (
            "PR #18",
            "e2e/mothership-merge-canary-base-20260902b",
            "0874166551f11d580168e8b4d0f354e742d39fe6",
            "1cfbbf646b8ac227c8c411f08a961c4396cc69ca",
            "1 file · +5 / -0",
            "Mothership public main",
        ):
            self.assertIn(value, english_image)
        self.assertIn("assets/readme/en/pr18-public-result.svg", english)

    def test_japanese_explainer_assets_are_bounded_and_factual(self) -> None:
        self.assertTrue(EXPLAINER_GIF.is_file())
        self.assertTrue(EXPLAINER_POSTER.is_file())
        self.assertLess(EXPLAINER_GIF.stat().st_size, 10 * 1024 * 1024)
        self.assertLess(EXPLAINER_POSTER.stat().st_size, 10 * 1024 * 1024)

        contract = _asset_contract(ASSET_BUILD)
        for locale in ("ja", "en"):
            gif = ROOT / f"assets/readme/{locale}/mothership-flow.gif"
            poster = ROOT / f"assets/readme/{locale}/mothership-flow-poster.png"
            dimensions, frames, duration_ms, delays = _gif_metadata(gif)
            self.assertEqual((contract["width"], contract["height"]), dimensions)
            self.assertEqual(contract["frame_count"], frames)
            self.assertEqual(contract["duration_ms"], duration_ms)
            self.assertEqual(frozenset((120, 130)), delays)
            self.assertLess(gif.stat().st_size, contract["max_gif_bytes"])

            png_header = poster.read_bytes()[:24]
            self.assertEqual(b"\x89PNG\r\n\x1a\n", png_header[:8])
            self.assertEqual(
                (contract["poster_width"], contract["poster_height"]),
                struct.unpack(">II", png_header[16:24]),
            )

        source = (ROOT / "assets/readme/source/mothership-flow-storyboard.md").read_text("utf-8")
        for phrase in (
            "github.merge_pr",
            "base commit SHA",
            "人間本人の認証",
            "汎用の実行系",
            "実行系・確認系",
        ):
            self.assertIn(phrase, source)
        for forbidden in ("/Users/", "/" + "private/", "token", "secret"):
            self.assertNotIn(forbidden.casefold(), source.casefold())
        english = README_EN.read_text("utf-8")
        self.assertEqual(1, self.text.count("assets/readme/ja/mothership-flow.gif"))
        self.assertEqual(2, self.text.count("assets/readme/ja/mothership-flow-poster.png"))
        self.assertEqual(1, english.count("assets/readme/en/mothership-flow.gif"))
        self.assertEqual(2, english.count("assets/readme/en/mothership-flow-poster.png"))
        self.assertIn("仕組みの図解です", self.text)
        generator = (ROOT / "assets/readme/source/generate_mothership_flow.py").read_text("utf-8")
        self.assertNotIn("/System/Library/Fonts/", generator)
        self.assertIn("First current reference profile: github.merge_pr", generator)
        self.assertIn("Unbound decision context", generator)
        self.assertIn("v0.4.1では未結合", generator)
        self.assertNotIn("仕事と操作案を準備", generator)
        self.assertNotIn("Prepare work and action", generator)
        self.assertIn('"parameters": ("Execution fields", "Caller-supplied")', generator)
        self.assertIn('"freeze": ("Exact operation", "Freeze five fields")', generator)
        self.assertIn('"consume": ("Local ledger", "One use per", "ledger history")', generator)
        self.assertIn('"consume_poster": ("Local ledger", "One use / ledger history")', generator)
        self.assertIn("FRAME_COUNT * 1000 != FPS * DURATION_MS", generator)

    def test_bilingual_positioning_assets_have_portable_generation_inputs(self) -> None:
        for relative in EXPECTED_POSITIONING_ASSETS:
            self.assertTrue((ROOT / relative).is_file(), relative)
        contract = _asset_contract(ASSET_BUILD)
        self.assertEqual("fonts/NotoSansJP-Regular.ttf", contract["font"])
        self.assertEqual(400, contract["normal_weight"])
        self.assertEqual(700, contract["bold_weight"])
        self.assertEqual(sorted(EXPECTED_POSITIONING_ASSETS[:-1]), sorted(contract["outputs"]))
        self.assertEqual(contract["font_sha256"], hashlib.sha256(ASSET_FONT.read_bytes()).hexdigest())
        generator = (ROOT / "assets/readme/source/generate_mothership_flow.py").read_text("utf-8")
        self.assertNotIn("/System/Library/Fonts/", generator)
        self.assertIn("tomllib", generator)
        self.assertIn("NORMAL_WEIGHT", generator)

        for locale in ("ja", "en"):
            svg = (ROOT / f"assets/readme/{locale}/ume-stack-responsibility.svg").read_text("utf-8")
            self.assertIn('viewBox="0 0 720 1120"', svg)
            self.assertEqual(2, svg.count("stroke-dasharray="))
            self.assertEqual(1, svg.count('data-role="bridge"'))
            self.assertEqual(2, svg.count('data-role="external"'))
            if locale == "en":
                self.assertIn(">Separately configured</tspan>", svg)
                self.assertIn(">executor</tspan>", svg)
                self.assertIn(">Separate verification</tspan>", svg)
                self.assertIn(">path</tspan>", svg)
                self.assertNotIn(">Separately configured executor</text>", svg)
                self.assertIn(">Solid = implemented now</tspan>", svg)
                self.assertIn(">Dashed = not connected</tspan>", svg)
                self.assertIn(">Outline = separately configured</tspan>", svg)
                self.assertNotIn("Solid = implemented now    Dashed = not connected", svg)
            else:
                self.assertEqual(2, svg.count(">現在の実装</text>"))
                self.assertIn(">方向性・未実装</text>", svg)
                self.assertNotIn(">CURRENT</text>", svg)
                self.assertNotIn("DIRECTION / NOT_SHIPPED", svg)

        for readme in (self.text, README_EN.read_text("utf-8")):
            self.assertIn('media="(max-width: 600px)"', readme)
            self.assertIn('media="(prefers-reduced-motion: reduce)"', readme)

    def test_code_tour_and_cli_scope_are_exact(self) -> None:
        for path in (
            "orchestration/lib/action_authority.py",
            "orchestration/lib/action_authority_ledger.py",
            "orchestration/lib/external_action.py",
            "tests/test_action_authority.py",
            "tests/test_action_authority_ledger.py",
            "tests/test_external_action_contracts.py",
        ):
            self.assertIn(f"]({path})", self.text)
        self.assertIn("同梱resource inventory、schema、registry、fixture", self.text)
        self.assertIn("legacy 0.2のsyntheticな", self.text)
        self.assertIn("Authority Coreの", self.text)
        self.assertIn("証明でも", self.text)
        self.assertNotIn("assets/boundary-map.svg", self.text)
        self.assertNotIn("assets/available-vs-allowed.svg", self.text)
        self.assertNotIn("assets/incident-lineage.svg", self.text)

    def test_no_sales_or_overclaiming_surface_remains(self) -> None:
        lowered = self.text.casefold()
        for forbidden in (
            "for teams",
            "design partner",
            "enterprise integration",
            "production-ready",
            "generic agent-security platform",
            "offline verification badge",
            "whole control plane",
        ):
            self.assertNotIn(forbidden, lowered)
        self.assertNotIn("/Users/", self.text)
        self.assertNotIn("/" + "private/", self.text)
        self.assertNotIn("file://", lowered)

    def test_claims_and_rendering_structure_are_closed(self) -> None:
        lowered = self.text.casefold()
        self.assertNotIn("offline verification", lowered)
        self.assertIn("github.merge_pr", lowered)
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
            anchor = re.sub(r"[^a-z0-9 _-]", "", title).replace(" ", "-") or title
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

            walkthrough = subprocess.run(
                [str(binary), str(source / "examples/authority_core_walkthrough.py")],
                cwd=root,
                env=install_environment,
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=15,
            )
            self.assertEqual(0, walkthrough.returncode, walkthrough.stderr.decode("utf-8", "replace"))
            self.assertIn(b"replay: \xe6\x8b\x92\xe5\x90\xa6", walkthrough.stdout)
            self.assertIn("合成した承認記録".encode(), walkthrough.stdout)

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
            "# Mothership",
            'src="assets/mothership-banner.png"',
            "人間が全部を抱えず、AIにも全部を明け渡さない。",
            "## PURPOSE",
            "## 責務分担",
            "## CURRENT: v0.4.1",
            "## 現在の参照profile",
            "## 公開結果の一例",
            f"]({E2E_EVIDENCE_LINK})",
            "## クイックスタート",
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
        self.assertIn("derived value, not a field", public)
        self.assertNotIn("These facts are captured", public)

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
        self.assertIn("historical snapshot", compatibility)
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
    @classmethod
    def setUpClass(cls) -> None:
        cls.english = README_EN.read_text("utf-8")
        cls.japanese = (ROOT / "docs/ja/README.md").read_text("utf-8")

    def test_japanese_guide_is_a_pointer_not_a_second_canonical_readme(self) -> None:
        self.assertIn("repository root", self.japanese)
        self.assertIn("../../README.md", self.japanese)
        self.assertIn("../../README.en.md", self.japanese)
        self.assertLessEqual(len(self.japanese.splitlines()), 16)
        self.assertNotIn("## クイックスタート", self.japanese)

    def test_english_equivalent_has_the_same_machine_scope(self) -> None:
        for fact in (
            "github.merge_pr",
            "expected head SHA",
            "expected base branch name",
            "expires_at",
            "Human identity is not authenticated",
            "trusted local ledger history",
            "PR #18",
            "production readiness",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, self.english)
        self.assertIn("github.merge_pr", README.read_text("utf-8"))
        self.assertIn("人間の本人確認は行いません", README.read_text("utf-8"))

    def test_both_full_readmes_have_bounded_language_and_no_private_paths(self) -> None:
        japanese = README.read_text("utf-8")
        for text in (japanese, self.english, self.japanese):
            self.assertNotIn("/Users/", text)
            self.assertNotIn("/" + "private/", text)
            self.assertNotIn("file://", text.casefold())
        for text in (japanese, self.english):
            lowered = text.casefold()
            self.assertNotIn("for teams", lowered)
            self.assertNotIn("design partner", lowered)
            self.assertNotIn("production-ready", lowered)


if __name__ == "__main__":
    unittest.main()
