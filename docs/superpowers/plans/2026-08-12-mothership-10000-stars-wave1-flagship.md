# Mothership 10,000 Stars Wave 1 Flagship Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Mothership's first screenful into a proof-first Flight Recorder conversion surface with real CLI evidence, accessible visuals, and one Mothership CTA.

**Architecture:** Preserve the current Flight Recorder implementation and generated evidence. Create and verify each asset independently, then close the README and Japanese entry point around those existing, tested assets.

**Tech Stack:** Markdown, Python unittest, SVG, PNG, POSIX shell, ffmpeg (asset generation only), Mothership CLI.

## Global Constraints

- Base branch is `feature/mothership-10000-stars`, derived from immutable Flight Recorder commit `62240fd`.
- Preserve exact generated JSON and Markdown evidence and all existing safety/non-authority disclaimers.
- The first star-oriented CTA links only to `https://github.com/UMEBOSHIISAN/mothership`.
- New behavioral assets must remain understandable through alt text and nearby Markdown.
- The GIF transcript must be captured from the current CLI and checked into `docs/generated/flight-demo-transcript.txt`.
- `ffmpeg` is a maintainer generation tool, not a project runtime or test dependency.

---

### Task 1: Add editable Flight lifecycle and incident visuals

**Files:**
- Create: `assets/flight-lifecycle.svg`
- Create: `assets/flight-incident.svg`
- Modify: `tests/test_markdown_links.py`

**Interfaces:**
- Consumes: lifecycle stages and verdict semantics already asserted in `tests/test_documentation.py`.
- Produces: two local, accessible SVG sources referenced by the README.

- [ ] **Step 1: Add failing asset-contract assertions**

```python
def test_flight_visuals_are_editable_accessible_svg(self) -> None:
    for filename, labels in {
        'flight-lifecycle.svg': ('Intent', 'Approval binding', 'Verification', 'Persistence proof'),
        'flight-incident.svg': ('declared success', 'observed evidence', 'DRIFTED'),
    }.items():
        text = (ROOT / 'assets' / filename).read_text('utf-8')
        self.assertIn('<svg', text)
        self.assertIn('<title>', text)
        self.assertIn('<desc>', text)
        for label in labels:
            self.assertIn(label, text)
```

- [ ] **Step 2: Run the failing test**

Run: `python3 -m unittest tests.test_markdown_links.MarkdownLinkTests.test_flight_visuals_are_editable_accessible_svg -v`

Expected: ERROR with missing asset file.

- [ ] **Step 3: Create the SVGs**

Use a `0 0 1280 560` wide viewBox, opaque deep-navy panel, cyan normal evidence, amber incomplete evidence, and red only for the `DRIFTED` finding. Include `<title>` and `<desc>`, use no embedded raster or external font, and spell the tested labels exactly.

- [ ] **Step 4: Run asset and link tests**

Run: `python3 -m unittest tests.test_markdown_links -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/flight-lifecycle.svg assets/flight-incident.svg tests/test_markdown_links.py
git commit -m "docs: visualize flight lifecycle and drift"
```

### Task 2: Add the atmospheric hero/social image

**Files:**
- Create: `assets/mothership-flight-recorder-social.png`
- Modify: `tests/test_markdown_links.py`

**Interfaces:**
- Consumes: existing whale identity and the deep-space instrument-panel visual design.
- Produces: a 1280×640 local PNG for README atmosphere and future GitHub social-preview upload.

- [ ] **Step 1: Add a failing PNG dimension test using only stdlib**

```python
def test_social_preview_is_1280_by_640_png(self) -> None:
    data = (ROOT / 'assets/mothership-flight-recorder-social.png').read_bytes()
    self.assertEqual(b'\x89PNG\r\n\x1a\n', data[:8])
    self.assertEqual((1280, 640), tuple(int.from_bytes(data[n:n+4], 'big') for n in (16, 20)))
```

- [ ] **Step 2: Run the test and observe the missing asset**

Run: `python3 -m unittest tests.test_markdown_links.MarkdownLinkTests.test_social_preview_is_1280_by_640_png -v`

Expected: ERROR with missing file.

- [ ] **Step 3: Generate one original image**

Use the image generation tool with this art direction: friendly whale-shaped mothership in deep navy space; cyan telemetry arcs and amber recorder beacon; clean negative space; no text, logos, vendor marks, characters, dashboards, or claims; cinematic but restrained; exact 2:1 composition suitable for cropping to 1280×640.

Resize/crop only as needed to exact dimensions without altering the existing `mothership-logo.png` or `mothership-banner.png`.

- [ ] **Step 4: Inspect and test the final PNG**

Run the PNG dimension test and visually inspect the image at original detail. Expected: 1280×640, readable focal point at small width, no text artifacts or vendor-like marks.

- [ ] **Step 5: Commit**

```bash
git add assets/mothership-flight-recorder-social.png tests/test_markdown_links.py
git commit -m "docs: add flight recorder social artwork"
```

### Task 3: Generate a real safe-versus-drift terminal GIF

**Files:**
- Create: `tools/generate_flight_demo.sh`
- Create: `docs/generated/flight-demo-transcript.txt`
- Create: `assets/flight-demo.gif`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: `python -m mothership demo safe` exit 0 and `python -m mothership demo drift` exit 21.
- Produces: a static transcript with exact CLI bytes and a generated GIF whose frames display that transcript.

- [ ] **Step 1: Add the failing transcript test**

```python
def test_terminal_demo_transcript_is_current_cli_evidence(self) -> None:
    transcript = (GENERATED / 'flight-demo-transcript.txt').read_text('utf-8')
    safe = (GENERATED / 'flight-safe-output.json').read_text('utf-8').rstrip()
    drift = (GENERATED / 'flight-drift-output.json').read_text('utf-8').rstrip()
    self.assertEqual(
        '$ mothership demo safe\n' + safe + '\n[exit 0]\n\n'
        '$ mothership demo drift\n' + drift + '\n[exit 21]\n',
        transcript,
    )
    data = (ROOT / 'assets' / 'flight-demo.gif').read_bytes()
    self.assertIn(data[:6], (b'GIF87a', b'GIF89a'))
```

- [ ] **Step 2: Run the test and observe missing outputs**

Run: `python3 -m unittest tests.test_documentation.GeneratedDocumentationTests.test_terminal_demo_transcript_is_current_cli_evidence -v`

Expected: ERROR for the missing transcript.

- [ ] **Step 3: Implement the generator**

The shell script must: use `mktemp -d`; capture safe stdout and require exit 0; capture drift stdout and require exit 21; compare both outputs byte-for-byte with existing generated JSON; write the canonical transcript; create two 1280×720 terminal frames with `ffmpeg` `drawtext` from the captured text using a reviewed local monospace font; assemble a looping GIF; and remove only its owned temporary directory through a trap. It must contain no network command and no path in the checked-in transcript.

- [ ] **Step 4: Run the generator and tests**

Run: `bash tools/generate_flight_demo.sh`

Then: `python3 -m unittest tests.test_documentation.GeneratedDocumentationTests -v`

Expected: PASS; safe/drift CLI bytes remain exact.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_flight_demo.sh docs/generated/flight-demo-transcript.txt assets/flight-demo.gif tests/test_documentation.py
git commit -m "docs: record the safe and drift terminal proof"
```

### Task 4: Close the flagship README and run regression

**Files:**
- Modify: `README.md`
- Modify: `docs/ja/README.md`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: all Wave 1 assets and exact generated transcript.
- Produces: a fully linked flagship README and Japanese parity statement.

- [ ] **Step 1: Write the failing flagship and Japanese contract assertions**

Add to `ReadmeContractTests`:

```python
def test_flagship_funnel_has_real_demo_visual_and_one_star_cta(self) -> None:
    for asset in (
        'assets/flight-demo.gif', 'assets/flight-lifecycle.svg',
        'assets/flight-incident.svg', 'assets/mothership-flight-recorder-social.png',
    ):
        self.assertIn(asset, self.text)
    self.assertEqual(1, self.text.count('https://github.com/UMEBOSHIISAN/mothership'))
    self.assertIn('Part of the Mothership constellation', self.text)
    self.assertIn('independently adoptable', self.text)

def test_japanese_entry_matches_the_flagship_boundary(self) -> None:
    text = JAPANESE_README.read_text('utf-8')
    for value in ('AIエージェントのブラックボックス', 'mothership demo safe', 'mothership demo drift'):
        self.assertIn(value, text)
    self.assertIn('権限を付与しません', text)
```

Run: `python3 -m unittest tests.test_documentation.ReadmeContractTests -v`

Expected: FAIL because the README copy has not referenced the now-existing assets or CTA.

- [ ] **Step 2: Rewrite the README entry and ecosystem CTA sections**

Put the GIF immediately below the hero, retain the safe/drift evidence before architecture detail, use the incident and lifecycle SVGs beside their matching explanations, and finish with one `## Star the black box` section linking to Mothership. Add the independence sentence `Part of the Mothership constellation means independently adoptable components with explicit boundaries. Mothership does not install, invoke, or configure a companion.` Update Japanese with equivalent meaning and no second star link. Keep exact generated evidence fences unchanged.

- [ ] **Step 3: Run focused documentation tests**

Run: `python3 -m unittest tests.test_documentation tests.test_documentation_commands tests.test_markdown_links -v`

Expected: PASS.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass; the six existing optional distribution/offline skips remain explainable.

- [ ] **Step 5: Scan and diff-check**

```bash
git diff --check
rg -n '/Users/|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|api[_-]?key\s*[:=]|secret\s*[:=]|token\s*[:=]' README.md docs/ja/README.md docs/generated assets tools
```

Expected: no private path, key, secret assignment, or token assignment in new public artifacts.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/ja/README.md tests/test_documentation.py
git commit -m "docs: make mothership the flight recorder flagship"
```
