# Mothership 10,000 Stars Wave 4 Launch and Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete local launch kit, repository-metadata drafts for all eleven repositories, and an evidence-backed cross-repository closeout without publishing anything.

**Architecture:** Store remote-setting intentions as validated local JSON, public copy as separate English/Japanese Markdown artifacts, and final repository evidence as measured receipts. Assets reuse the real Wave 1 proof and clearly separate atmospheric art from behavioral evidence.

**Tech Stack:** JSON, Markdown, Python unittest, PNG, GIF, Git/GitHub read-only inspection.

## Global Constraints

- No `gh repo edit`, API mutation, push, tag, release, upload, or social post in this wave.
- Metadata `status` is always `draft-not-applied` until remote state is explicitly changed and measured.
- GitHub traffic and conversion metrics remain `UNKNOWN` when unavailable.
- English and Japanese launch copy make the same authority/non-execution claims.
- No tracking pixels, analytics scripts, external image hotlinks, or secret-bearing issue templates.
- Local artifacts name exact result commits and do not use `COMMITTED`, `PUBLISHED`, or `CLOSED` for remote state.

---

### Task 1: Validate the eleven-repository metadata manifest

**Files:**
- Create: `docs/launch/repository-metadata.json`
- Create: `tests/test_launch_kit.py`

**Interfaces:**
- Consumes: current GitHub descriptions observed before Wave 1 and final local README responsibilities from Waves 1–3.
- Produces: deterministic drafts for descriptions, topics, social-preview path, and flagship relationship.

- [ ] **Step 1: Write the failing manifest test**

```python
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "mothership", "agent-frontdoor", "workflow-governance-model", "mothership-router",
    "secretary-tui", "agent-team-runtime", "evidence-spine-core", "run-lineage-core",
    "source-health-core", "agent-decision-core", "knowledge-lifecycle-kit",
}

class LaunchKitTests(unittest.TestCase):
    def test_metadata_manifest_is_closed_and_complete(self):
        data = json.loads((ROOT / "docs/launch/repository-metadata.json").read_text("utf-8"))
        self.assertEqual({"schema_version", "status", "generated_from", "repositories"}, set(data))
        self.assertEqual("mothership-metadata-draft.v1", data["schema_version"])
        self.assertEqual("draft-not-applied", data["status"])
        self.assertEqual(EXPECTED, {entry["name"] for entry in data["repositories"]})
        for entry in data["repositories"]:
            self.assertEqual({
                "name", "description", "topics", "social_preview", "relationship",
                "homepage", "primary_language", "package_manager", "verified_at", "source_commit",
            }, set(entry))
            self.assertLessEqual(len(entry["description"]), 350)
            self.assertEqual(len(entry["topics"]), len(set(entry["topics"])))
            self.assertTrue(all(topic == topic.lower() and " " not in topic for topic in entry["topics"]))
            self.assertNotIn("/Users/", json.dumps(entry))
```

- [ ] **Step 2: Run and observe failure**

Run: `python3 -m unittest tests.test_launch_kit.LaunchKitTests.test_metadata_manifest_is_closed_and_complete -v`

Expected: ERROR for missing manifest.

- [ ] **Step 3: Create the closed JSON manifest**

Use these exact description drafts:

```text
mothership: The black box for AI agents — record authority, replay evidence, and detect drift without executing the agent.
agent-frontdoor: Turn an informal AI-agent request into a bounded, human-readable task contract and stop scope drift before execution.
workflow-governance-model: A typed, fail-closed data model for evidence, claims, approval, execution receipts, and verification.
mothership-router: Produce digest-bound, human-gated dry-run routing manifests without launching a worker.
secretary-tui: A read-only terminal dashboard for local AI workflows that observes state without approving or executing anything.
agent-team-runtime: A local protocol core for deterministic packet replay, duplicate-wake suppression, and canonical completion checks.
evidence-spine-core: A local append-only evidence ledger for synthetic task, run, result, scorecard, and verification chains.
run-lineage-core: Deterministic in-memory joins for exact, proposed, ambiguous, unmatched, and inconclusive run lineage.
source-health-core: Dependency-free validation for source-backed local-LLM and AI-agent observation records.
agent-decision-core: Provider-neutral advisory gates for bounded task context and local-first decisions, with execution always disabled.
knowledge-lifecycle-kit: Offline-safe lifecycle inspection and advisory routing components that stop at human authority.
```

Use 5–10 repository-specific lowercase topics per entry. `mothership` uses the Wave 1 social PNG. Each companion uses a committed 1280×640 PNG under Mothership's `assets/social-previews/`, rendered from that repository's strongest local visual so GitHub receives an accepted upload format without adding rollout-only binaries to the companion. Every companion relationship equals `independent-companion-to-mothership` and Mothership equals `flagship`. Set `homepage` to `null` unless a durable public page was measured; record the actual primary language and package manager (`pip`, `npm`, or `go`); set `verified_at` to `2026-08-12`; and fill `source_commit` from each final local HEAD rather than a branch name.

- [ ] **Step 4: Run the manifest test**

Run: `python3 -m unittest tests.test_launch_kit -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/launch/repository-metadata.json tests/test_launch_kit.py
git commit -m "docs: draft ecosystem repository metadata"
```

### Task 2: Build English and Japanese launch copy

**Files:**
- Create: `docs/launch/announcement-en.md`
- Create: `docs/launch/announcement-ja.md`
- Create: `docs/launch/article-outline.md`
- Create: `docs/launch/release-notes.md`
- Modify: `tests/test_launch_kit.py`

**Interfaces:**
- Consumes: exact Flight Recorder CLI commands, verdicts, and no-authority disclaimer.
- Produces: short announcement, technical thread, Japanese parity, and article structure.

- [ ] **Step 1: Add failing copy assertions**

```python
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
    for heading in (
        "Why AI agents need a flight recorder", "A success message is not evidence",
        "Authority as data", "Safe flight", "Drifted flight", "What Mothership does not do",
    ):
        self.assertIn(heading, outline)
    for value in ("Mothership Flight Recorder", "mothership demo safe", "mothership demo drift", "Local draft — not published"):
        self.assertIn(value, release)
```

- [ ] **Step 2: Run and observe missing files**

Run: `python3 -m unittest tests.test_launch_kit.LaunchKitTests.test_launch_copy_is_bilingual_proof_first_and_non_authorizing -v`

Expected: ERROR for missing launch copy.

- [ ] **Step 3: Write the copy**

Each announcement contains: one category sentence; the problem; safe and drift command snippets; one limitation paragraph; one Mothership URL; no adoption metric or unmeasured claim. The English file contains `## Short announcement` and `## Technical thread`; Japanese contains `## 短文` and `## 技術スレッド`. The article outline uses the six tested headings and cites only local docs/code paths. Release notes begin with `Local draft — not published`, use the title `Mothership Flight Recorder`, summarize the safe/drift proof, list compatibility and safety limits, and make no tag/version claim until the separate release decision.

- [ ] **Step 4: Run launch copy tests**

Run: `python3 -m unittest tests.test_launch_kit -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/launch/announcement-en.md docs/launch/announcement-ja.md docs/launch/article-outline.md docs/launch/release-notes.md tests/test_launch_kit.py
git commit -m "docs: prepare bilingual flight recorder launch copy"
```

### Task 3: Add a square social card derived from verified assets

**Files:**
- Create: `assets/mothership-flight-recorder-square.png`
- Modify: `tests/test_launch_kit.py`

**Interfaces:**
- Consumes: Wave 1 original social image and the real safe/drift terminal visual.
- Produces: a 1080×1080 local announcement card; atmospheric image remains non-evidentiary.

- [ ] **Step 1: Add the failing image test**

```python
def test_square_social_card_is_exact_png(self):
    data = (ROOT / "assets/mothership-flight-recorder-square.png").read_bytes()
    self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
    self.assertEqual((1080, 1080), tuple(int.from_bytes(data[n:n+4], "big") for n in (16, 20)))
```

- [ ] **Step 2: Run and observe failure**

Run: `python3 -m unittest tests.test_launch_kit.LaunchKitTests.test_square_social_card_is_exact_png -v`

Expected: ERROR for missing image.

- [ ] **Step 3: Generate/edit the square asset**

Use the image generation/editing tool with the Wave 1 social image as reference. Extend it to a square deep-space composition with the whale recorder beacon centered above clean negative space. Add no text, logo, vendor mark, UI screenshot, or character likeness. Do not edit the source PNG in place.

- [ ] **Step 4: Inspect and test**

Visually inspect original detail and run the exact PNG test. Expected: 1080×1080, no text artifacts, same visual identity as Wave 1.

- [ ] **Step 5: Commit**

```bash
git add assets/mothership-flight-recorder-square.png tests/test_launch_kit.py
git commit -m "docs: add square flight recorder launch art"
```

### Task 4: Create the publication and community-safety checklist

**Files:**
- Create: `docs/launch/publication-checklist.md`
- Create: `docs/launch/community-prompt.md`
- Modify: `tests/test_launch_kit.py`

**Interfaces:**
- Consumes: metadata manifest and local wave receipts.
- Produces: exact remote checks and a safe request for public drift examples.

- [ ] **Step 1: Add failing checklist assertions**

```python
def test_publication_checklist_separates_local_and_remote_evidence(self):
    checklist = (ROOT / "docs/launch/publication-checklist.md").read_text("utf-8")
    prompt = (ROOT / "docs/launch/community-prompt.md").read_text("utf-8")
    for value in (
        "commit exists locally", "commit reached origin", "rendered README",
        "repository description", "topics", "social preview", "release reachability",
        "star count", "GitHub traffic remains UNKNOWN",
    ):
        self.assertIn(value, checklist)
    for value in ("remove secrets", "remove private paths", "synthetic reproduction", "do not paste credentials"):
        self.assertIn(value, prompt)
```

- [ ] **Step 2: Run and observe failure**

Run: `python3 -m unittest tests.test_launch_kit.LaunchKitTests.test_publication_checklist_separates_local_and_remote_evidence -v`

Expected: ERROR for missing files.

- [ ] **Step 3: Write the two documents**

The checklist groups exact read-only verification after each separately approved remote mutation. The community prompt asks for minimal synthetic records and explicitly rejects secrets, personal paths, raw production output, and credentials.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_launch_kit -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/launch/publication-checklist.md docs/launch/community-prompt.md tests/test_launch_kit.py
git commit -m "docs: define safe publication and feedback checks"
```

### Task 5: Cross-repository audit and local closeout

**Files:**
- Create: `docs/launch/2026-08-12-local-closeout.md`
- Modify: `tests/test_launch_kit.py`

**Interfaces:**
- Consumes: Wave 2 and Wave 3 receipts, Mothership Wave 1 commits, all eleven final local HEADs.
- Produces: final local evidence and an explicit unexecuted publication gate.

- [ ] **Step 1: Re-run all native suites**

Use the exact commands from Waves 1–3. Record command, exit code, passing count/output marker, skipped count, HEAD, and dirty status immediately after each run.

- [ ] **Step 2: Run cross-repository public-boundary scans**

In each repository run `git diff --check` and scan changed public files for `/Users/`, private-key markers, secret assignments, token assignments, and external image URLs. Expected: no finding in task-owned content.

- [ ] **Step 3: Visually inspect every changed image**

Inspect Mothership hero/social/square/GIF/SVG assets and the six primitive SVGs at desktop and narrow widths. Record any corrected clipping, illegible text, missing contrast, or false dependency arrow.

- [ ] **Step 4: Write the factual closeout**

Use the master-plan closeout headings. Name all eleven local result commits. Mark GitHub descriptions, topics, social previews, releases, posts, traffic, and star conversion as `NOT APPLIED` or `UNKNOWN`, never completed.

- [ ] **Step 5: Add and run a closeout existence test**

```python
def test_closeout_names_every_repository_and_keeps_publication_open(self):
    text = (ROOT / "docs/launch/2026-08-12-local-closeout.md").read_text("utf-8")
    for name in EXPECTED:
        self.assertIn(name, text)
    self.assertIn("NOT APPLIED", text)
    self.assertIn("UNKNOWN", text)
    self.assertNotIn("remote rollout complete", text.casefold())
```

Run: `python3 -m unittest tests.test_launch_kit -v`

Expected: PASS.

- [ ] **Step 6: Run final Mothership regression and commit**

Run: `python3 -m unittest discover -s tests -v`

Then:

```bash
git add docs/launch/2026-08-12-local-closeout.md tests/test_launch_kit.py
git commit -m "docs: close the local flagship rollout with evidence"
```

### Task 6: Stop at the remote publication gate

**Files:**
- Read: `docs/launch/repository-metadata.json`
- Read: `docs/launch/publication-checklist.md`
- Read: `docs/launch/2026-08-12-local-closeout.md`

**Interfaces:**
- Consumes: final clean local commits.
- Produces: a target-specific approval request, not a remote action.

- [ ] **Step 1: Present exact proposed remote mutations**

List separately: branch pushes, PR/merge, eleven description/topic updates, social preview upload, release/tag, and announcement posts. Include target repository/account and local source commit for each.

- [ ] **Step 2: Request publication authority**

Do not execute any item until the human supplies the applicable exact approval token for that target. Local implementation ends here.
