from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import struct
import subprocess
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
MARKDOWN_IMAGE = re.compile(r"!\[([^]]*)\]\(([^)]+)\)")
HTML_IMAGE = re.compile(
    r"<img\b(?=[^>]*\bsrc=\"([^\"]+)\")(?=[^>]*\balt=\"([^\"]*)\")[^>]*>",
    re.IGNORECASE,
)
ALLOWED_EXTERNAL_HOSTS = {"github.com", "img.shields.io"}
ALLOWED_GITHUB_OWNER = "UMEBOSHIISAN"


def _tracked_markdown() -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
    )
    return tuple(ROOT / line for line in completed.stdout.splitlines() if line)


def _outside_fences(text: str) -> str:
    visible: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            visible.append(line)
    return "\n".join(visible)


def _destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1:value.index(">")]
    return value.split(maxsplit=1)[0]


def _anchors(path: Path) -> set[str]:
    counts: Counter[str] = Counter()
    anchors: set[str] = set()
    in_fence = False
    for line in path.read_text("utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip().casefold()
        slug = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE)
        slug = re.sub(r"[\s-]+", "-", slug).strip("-")
        occurrence = counts[slug]
        counts[slug] += 1
        anchors.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
    return anchors


class MarkdownLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = _tracked_markdown()

    def test_all_tracked_markdown_links_resolve_without_path_escape(self) -> None:
        self.assertTrue(self.documents)
        failures: list[str] = []
        for document in self.documents:
            text = _outside_fences(document.read_text("utf-8"))
            for raw in MARKDOWN_LINK.findall(text):
                target = _destination(raw)
                parsed = urlsplit(target)
                if parsed.scheme:
                    continue
                if target.startswith("//"):
                    failures.append(f"{document.relative_to(ROOT)}: protocol-relative {target}")
                    continue
                relative, _, fragment = target.partition("#")
                resolved = (document.parent / unquote(relative or document.name)).resolve()
                try:
                    resolved.relative_to(ROOT.resolve())
                except ValueError:
                    failures.append(f"{document.relative_to(ROOT)}: path escape {target}")
                    continue
                if not resolved.is_file():
                    failures.append(f"{document.relative_to(ROOT)}: missing {target}")
                    continue
                if fragment and resolved.suffix.casefold() == ".md":
                    anchor = unquote(fragment).casefold()
                    if anchor not in _anchors(resolved):
                        failures.append(
                            f"{document.relative_to(ROOT)}: missing anchor {target}"
                        )
        self.assertEqual([], failures, "\n".join(failures))

    def test_external_urls_are_https_and_within_the_public_allowlist(self) -> None:
        failures: list[str] = []
        for document in self.documents:
            text = _outside_fences(document.read_text("utf-8"))
            targets = [_destination(raw) for raw in MARKDOWN_LINK.findall(text)]
            targets.extend(src for src, _ in HTML_IMAGE.findall(text))
            for target in targets:
                parsed = urlsplit(target)
                if not parsed.scheme and not parsed.netloc:
                    continue
                if parsed.scheme != "https" or parsed.hostname not in ALLOWED_EXTERNAL_HOSTS:
                    failures.append(f"{document.relative_to(ROOT)}: disallowed URL {target}")
                    continue
                if parsed.hostname == "github.com":
                    pieces = [piece for piece in parsed.path.split("/") if piece]
                    if len(pieces) < 2 or pieces[0] != ALLOWED_GITHUB_OWNER:
                        failures.append(f"{document.relative_to(ROOT)}: unowned URL {target}")
                if parsed.username or parsed.password or parsed.query:
                    failures.append(f"{document.relative_to(ROOT)}: credential/query URL {target}")
        self.assertEqual([], failures, "\n".join(failures))

    def test_images_have_resolvable_sources_and_meaningful_alt_text(self) -> None:
        failures: list[str] = []
        image_count = 0
        for document in self.documents:
            text = _outside_fences(document.read_text("utf-8"))
            images = MARKDOWN_IMAGE.findall(text)
            images.extend((alt, src) for src, alt in HTML_IMAGE.findall(text))
            for alt, raw in images:
                image_count += 1
                target = _destination(raw)
                if len(alt.strip()) < 5:
                    failures.append(f"{document.relative_to(ROOT)}: weak alt text for {target}")
                parsed = urlsplit(target)
                if parsed.scheme:
                    continue
                resolved = (document.parent / unquote(target.partition("#")[0])).resolve()
                try:
                    resolved.relative_to(ROOT.resolve())
                except ValueError:
                    failures.append(f"{document.relative_to(ROOT)}: image path escape {target}")
                    continue
                if not resolved.is_file():
                    failures.append(f"{document.relative_to(ROOT)}: missing image {target}")
        self.assertGreaterEqual(image_count, 2)
        self.assertEqual([], failures, "\n".join(failures))

    def test_flight_evidence_is_tracked_and_safe_to_link(self) -> None:
        # A documentation change must not replace generated CLI evidence with a private path.
        for path in (
            ROOT / "docs/generated/flight-safe-output.json",
            ROOT / "docs/generated/flight-drift-output.json",
            ROOT / "docs/generated/flight-safe-report.md",
        ):
            with self.subTest(path=path.name):
                text = path.read_text("utf-8")
                self.assertTrue(text.endswith("\n"))
                self.assertFalse(text.endswith("\n\n"))
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/" + "private/", text)

    def test_flight_visuals_are_editable_accessible_svg(self) -> None:
        for filename, labels in {
            "flight-lifecycle.svg": (
                "Intent",
                "Approval binding",
                "Verification",
                "Persistence proof",
            ),
            "flight-incident.svg": (
                "declared success",
                "observed evidence",
                "DRIFTED",
            ),
            "constellation.svg": (
                "Mothership",
                "Agent Frontdoor",
                "Workflow Governance Model",
                "Mothership Router",
                "Secretary TUI",
                "Agent Team Runtime",
                "Evidence Spine Core",
                "Run Lineage Core",
                "Source Health Core",
                "Agent Decision Core",
                "Knowledge Lifecycle Kit",
            ),
        }.items():
            text = (ROOT / "assets" / filename).read_text("utf-8")
            self.assertIn("<svg", text)
            self.assertIn("<title>", text)
            self.assertIn("<desc>", text)
            for label in labels:
                self.assertIn(label, text)

    def test_social_preview_is_1280_by_640_png(self) -> None:
        preview = ROOT / "assets" / "mothership-flight-recorder-social.png"
        payload = preview.read_bytes()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", payload[:8])
        self.assertEqual(b"IHDR", payload[12:16])
        self.assertEqual((1280, 640), struct.unpack(">II", payload[16:24]))


if __name__ == "__main__":
    unittest.main()
