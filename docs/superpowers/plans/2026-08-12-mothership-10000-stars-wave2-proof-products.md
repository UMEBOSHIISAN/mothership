# Mothership 10,000 Stars Wave 2 Proof Products Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agent Frontdoor, Workflow Governance Model, Mothership Router, and Secretary TUI powerful independent proof products that route qualified discovery back to Mothership.

**Architecture:** Preserve each repository's existing hero, signature proof, language, and safety model. Add one shared relationship contract, test it locally in the repository's native framework, and keep each repository in its own branch/worktree and commit.

**Tech Stack:** Markdown, existing SVG/GIF assets, pytest, Python unittest, Go test, Git worktrees.

## Global Constraints

- Relationship copy: `Part of the Mothership constellation.`
- Independence copy must state that Mothership does not install, invoke, or configure the companion.
- The Mothership link is `https://github.com/UMEBOSHIISAN/mothership` and is the only star-oriented CTA.
- Existing signature proofs, commands, exit codes, schema versions, and safety boundaries are preserved unless current tests prove a correction is required.
- Create all four worktrees under `<workspace>/oss_staging/.worktrees-10000-stars/` to avoid touching existing checkouts.
- A repository with a dirty checkout, unexplained upstream state, or failing baseline is stopped and reported; no stash/reset/clean/rebase workaround.

---

### Task 1: Measure bases and create four isolated worktrees

**Files:**
- Inspect only: each repository root, branch, upstream, status, and documented test files
- Create worktrees: `<workspace>/oss_staging/.worktrees-10000-stars/{agent-frontdoor,workflow-governance-model,mothership-router,secretary-tui}`

**Interfaces:**
- Consumes: current clean primary checkouts.
- Produces: four independent branches named `docs/mothership-10000-stars`.

- [ ] **Step 1: Record measured bases**

For each repo run:

```bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
git rev-list --left-right --count HEAD...@{upstream}
git worktree list --porcelain
```

Expected: empty porcelain status. If `@{upstream}` is absent, record `upstream: none` and do not infer remote parity.

- [ ] **Step 2: Run native baselines**

```bash
# Agent Frontdoor
python3 -m pytest -q

# Workflow Governance Model
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Mothership Router
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Secretary TUI
go test ./...
```

Expected: every selected repository passes before editing.

- [ ] **Step 3: Create the worktrees**

```bash
mkdir -p <workspace>/oss_staging/.worktrees-10000-stars
git -C <workspace>/oss_staging/agent-frontdoor worktree add <workspace>/oss_staging/.worktrees-10000-stars/agent-frontdoor -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/workflow-governance-model worktree add <workspace>/oss_staging/.worktrees-10000-stars/workflow-governance-model -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/mothership-router worktree add <workspace>/oss_staging/.worktrees-10000-stars/mothership-router -b docs/mothership-10000-stars HEAD
git -C <workspace>/Projects/Umeboshi/secretary-tui worktree add <workspace>/oss_staging/.worktrees-10000-stars/secretary-tui -b docs/mothership-10000-stars HEAD
```

Expected: each new worktree is clean on `docs/mothership-10000-stars`.

### Task 2: Agent Frontdoor relationship funnel

**Files:**
- Modify: `README.md`
- Modify: `tests/test_readme.py`

**Interfaces:**
- Consumes: existing frontdoor card, invalid-card, and scope-drift proof.
- Produces: a tested Mothership relationship strip without changing the required first three README lines.

- [ ] **Step 1: Add the failing README assertions**

```python
def test_readme_routes_to_mothership_without_claiming_integration() -> None:
    text = _text()
    assert "Part of the Mothership constellation." in text
    assert "https://github.com/UMEBOSHIISAN/mothership" in text
    assert "does not install, invoke, or configure Agent Frontdoor" in text
    assert "For authority, evidence, replay, and drift across the complete agent flight" in text
```

- [ ] **Step 2: Verify the new test fails**

Run: `python3 -m pytest tests/test_readme.py -q`

Expected: FAIL on the missing shared relationship wording.

- [ ] **Step 3: Add the relationship strip**

Insert it after the badge/pulse hero and before the first conceptual diagram. Preserve the first three contract lines and all exact CLI examples. Use this final sentence:

```markdown
For authority, evidence, replay, and drift across the complete agent flight, visit [Mothership](https://github.com/UMEBOSHIISAN/mothership). Part of the Mothership constellation. This repository is independently adoptable; Mothership does not install, invoke, or configure Agent Frontdoor.
```

- [ ] **Step 4: Run focused and full tests**

Run: `python3 -m pytest tests/test_readme.py tests/test_no_execution_paths.py -q`

Then: `python3 -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_readme.py
git commit -m "docs: connect agent frontdoor to mothership"
```

### Task 3: Workflow Governance Model relationship funnel

**Files:**
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: governance-chain and stale-reference proof already present in README and tests.
- Produces: a small test contract and one flagship route.

- [ ] **Step 1: Create the failing test file**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_readme_has_evidence_backed_mothership_relationship() -> None:
    text = (ROOT / "README.md").read_text("utf-8")
    assert "A stale reference is rejected, not silently resolved." in text
    assert "assets/governance-chain.svg" in text
    assert "Part of the Mothership constellation." in text
    assert "https://github.com/UMEBOSHIISAN/mothership" in text
    assert "Mothership does not install, invoke, or configure WGM" in text
```

- [ ] **Step 2: Run and observe failure**

Run: `python3 -m pytest tests/test_readme.py -q`

Expected: FAIL on the relationship string.

- [ ] **Step 3: Add the relationship paragraph**

Place it below the top link row. Use `WGM` consistently with the README's existing abbreviation and keep the signature statement and chain diagram above the quick start.

- [ ] **Step 4: Run full tests**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Then: `python3 -m pytest tests/test_readme.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_readme.py
git commit -m "docs: connect governance proof to mothership"
```

### Task 4: Mothership Router relationship funnel

**Files:**
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: registry digest and stale-approval proof.
- Produces: a tested relationship statement that preserves no-execution boundaries.

- [ ] **Step 1: Create the failing test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_readme_routes_digest_proof_to_mothership() -> None:
    text = (ROOT / "README.md").read_text("utf-8")
    assert "An approval only applies to what it approved." in text
    assert "assets/digest-binding.svg" in text
    assert "Part of the Mothership constellation." in text
    assert "https://github.com/UMEBOSHIISAN/mothership" in text
    assert "Mothership does not install, invoke, or configure Mothership Router" in text
    assert "authority_effect: false" in text
    assert "execution_effect: false" in text
```

- [ ] **Step 2: Run and observe failure**

Run: `python3 -m pytest tests/test_readme.py -q`

Expected: FAIL on the relationship string.

- [ ] **Step 3: Add one relationship paragraph below the hero link row**

Keep the digest-binding explanation and four outcome table unchanged. Do not add a CLI approval path or imply execution.

- [ ] **Step 4: Run full tests**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Then: `python3 -m pytest tests/test_readme.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_readme.py
git commit -m "docs: connect approval proof to mothership"
```

### Task 5: Secretary TUI relationship funnel

**Files:**
- Create: `readme_test.go`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing `assets/demo.gif`, read-only dashboard principle, and governance snapshot limits.
- Produces: a tested Japanese-first route to Mothership without changing TUI behavior.

- [ ] **Step 1: Add the failing Go test**

```go
package main

import (
    "os"
    "strings"
    "testing"
)

func TestReadmeConnectsReadOnlyObservationToMothership(t *testing.T) {
    data, err := os.ReadFile("README.md")
    if err != nil { t.Fatal(err) }
    text := string(data)
    for _, want := range []string{
        "The dashboard that cannot press anything.",
        "assets/demo.gif",
        "Part of the Mothership constellation.",
        "https://github.com/UMEBOSHIISAN/mothership",
        "Mothership does not install, invoke, or configure Secretary TUI",
    } {
        if !strings.Contains(text, want) { t.Fatalf("README missing %q", want) }
    }
}
```

- [ ] **Step 2: Run and observe failure**

Run: `go test ./...`

Expected: FAIL on the new relationship string.

- [ ] **Step 3: Add the bilingual relationship paragraph**

Place it below the badges and above the first Japanese product paragraph. Keep the Japanese explanation first, retain the real demo GIF, and state that the dashboard display is not freshness or operational truth.

- [ ] **Step 4: Run full tests**

Run: `go test ./...`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md readme_test.go
git commit -m "docs: connect read-only observation to mothership"
```

### Task 6: Wave 2 ownership and evidence closeout

**Files:**
- Create in Mothership: `docs/launch/wave2-proof-products-receipt.md`

**Interfaces:**
- Consumes: four clean result commits and native test results.
- Produces: a factual receipt for Wave 4.

- [ ] **Step 1: Record each base/result pair and command**

Use one table row per repository: repository, source checkout status, worktree path, base HEAD, result HEAD, test command, test result, remaining dirty state.

- [ ] **Step 2: Verify no worktree has pending changes**

Run `git status --short --branch` and `git diff --check` in all four worktrees. Expected: clean result branches.

- [ ] **Step 3: Commit the receipt in Mothership**

```bash
git add docs/launch/wave2-proof-products-receipt.md
git commit -m "docs: record proof product rollout evidence"
```
