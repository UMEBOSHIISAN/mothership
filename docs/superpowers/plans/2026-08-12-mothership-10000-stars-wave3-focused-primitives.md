# Mothership 10,000 Stars Wave 3 Focused Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give six focused primitive repositories compact, evidence-backed entry points and distinct signature visuals while routing discovery to Mothership.

**Architecture:** Each repository gets one README contract test, one editable local SVG, and one restrained README rebuild around its actual public API or fixture. No shared runtime package is introduced; consistency comes from copy hierarchy, visual grammar, and the Mothership relationship statement.

**Tech Stack:** Markdown, SVG, Python unittest, Node.js test runner, repository-native boundary scripts, Git worktrees.

## Global Constraints

- Re-verify current README, HEAD, signature example, and native test command before editing each repository.
- Worktrees use the six exact paths listed in Task 1 on branch `docs/mothership-10000-stars`.
- Every SVG contains `<title>` and `<desc>`, uses no external resource, and explains an observed repository behavior.
- Every README contains one runnable proof, one strongest non-goal, `Part of the Mothership constellation.`, the Mothership URL, and an independent-adoption statement.
- No Tier 2 README is silently accepted above 220 lines; line count and reason are recorded.

---

### Task 1: Measure six clean bases and create worktrees

**Files:**
- Inspect: `agent-team-runtime`, `evidence-spine-core`, `run-lineage-core`, `source-health-core`, `agent-decision-core`, `knowledge-lifecycle-kit`
- Create: six sibling worktrees under `<workspace>/oss_staging/.worktrees-10000-stars/`

**Interfaces:**
- Consumes: current source repositories.
- Produces: clean isolated branches and baseline receipts.

- [ ] **Step 1: Record repository truth**

Run in each source repo:

```bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
git rev-list --left-right --count HEAD...@{upstream}
git worktree list --porcelain
```

Expected: empty porcelain. Record an absent upstream as `none`, never as synchronized.

- [ ] **Step 2: Run the six baselines**

```bash
# agent-team-runtime
PYTHONPATH=src python3 -m unittest discover -s tests -v
# evidence-spine-core
python3 -m unittest discover -s tests -v && python3 tools/check_public_boundary.py .
# run-lineage-core
python3 -m unittest discover -s tests -v && python3 tools/check_public_boundary.py .
# source-health-core
PYTHONPATH=src python3 -m unittest discover -s tests -v && python3 tools/verify_public_boundary.py .
# agent-decision-core
npm test && node tools/check-public-boundary.js .
# knowledge-lifecycle-kit
python3 -m unittest discover -s tests -v
```

Expected: every selected base passes. Stop only the failing/dirty repository.

- [ ] **Step 3: Create clean worktrees**

```bash
git -C <workspace>/agent-team-runtime worktree add <workspace>/oss_staging/.worktrees-10000-stars/agent-team-runtime -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/evidence-spine-core worktree add <workspace>/oss_staging/.worktrees-10000-stars/evidence-spine-core -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/run-lineage-core worktree add <workspace>/oss_staging/.worktrees-10000-stars/run-lineage-core -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/source-health-core worktree add <workspace>/oss_staging/.worktrees-10000-stars/source-health-core -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/agent-decision-core worktree add <workspace>/oss_staging/.worktrees-10000-stars/agent-decision-core -b docs/mothership-10000-stars HEAD
git -C <workspace>/oss_staging/knowledge-lifecycle-kit worktree add <workspace>/oss_staging/.worktrees-10000-stars/knowledge-lifecycle-kit -b docs/mothership-10000-stars HEAD
```

Expected: clean worktree on the new branch.

### Task 2: Agent Team Runtime — replay reducer proof

**Files:**
- Create: `assets/replay-reducer.svg`
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `fixtures/normal_cycle.jsonl`, `fixtures/duplicate_wake.jsonl`, and CLI replay output.
- Produces: a visual event lane and a compact README proving wake is not completion.

- [ ] **Step 1: Add the failing unittest**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReadmeTests(unittest.TestCase):
    def test_replay_proof_and_mothership_relationship(self):
        text = (ROOT / "README.md").read_text("utf-8")
        for value in (
            "assets/replay-reducer.svg", "worker_forgets_report.jsonl",
            "A wake is not a successful completion",
            "Part of the Mothership constellation.",
            "https://github.com/UMEBOSHIISAN/mothership",
            "does not install, invoke, or configure Agent Team Runtime",
        ):
            self.assertIn(value, text)
        svg = (ROOT / "assets/replay-reducer.svg").read_text("utf-8")
        for value in ("<title>", "<desc>", "wake", "verification", "complete"):
            self.assertIn(value, svg)
```

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_readme -v`

Expected: ERROR because the SVG is absent.

- [ ] **Step 3: Create the SVG and rewrite the README**

Show ordered packet events, duplicate wake suppression, explicit verification, and completion. Put the existing replay command and actual JSON summary fields before implementation detail. State local-only/no-dispatch/no-retry boundaries.

- [ ] **Step 4: Run native tests and check length**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v && wc -l README.md && git diff --check`

Expected: PASS and normally at most 180 README lines.

- [ ] **Step 5: Commit**

```bash
git add README.md assets/replay-reducer.svg tests/test_readme.py
git commit -m "docs: explain deterministic team replay"
```

### Task 3: Evidence Spine Core — append-only chain proof

**Files:**
- Create: `assets/evidence-chain.svg`
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: current synthetic tutorial commands and ledger verification.
- Produces: a task → run → result → scorecard → close → verify visual.

- [ ] **Step 1: Add the failing unittest**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReadmeTests(unittest.TestCase):
    def test_append_only_proof_and_relationship(self):
        text = (ROOT / "README.md").read_text("utf-8")
        for value in (
            "assets/evidence-chain.svg", "task-open", "scorecard", "verify",
            "append-only", "Part of the Mothership constellation.",
            "https://github.com/UMEBOSHIISAN/mothership",
            "does not install, invoke, or configure Evidence Spine Core",
        ):
            self.assertIn(value, text)
        svg = (ROOT / "assets/evidence-chain.svg").read_text("utf-8")
        for value in ("<title>", "<desc>", "Task", "Result", "Verify"):
            self.assertIn(value, svg)
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m unittest tests.test_readme -v`

Expected: ERROR for missing SVG.

- [ ] **Step 3: Create visual and proof-first README**

Keep the synthetic tutorial copyable. State that verification checks a supplied chain and does not repair, dispatch, select a worker, or read an external service.

- [ ] **Step 4: Run native verification**

Run: `python3 -m unittest discover -s tests -v && python3 tools/check_public_boundary.py . && wc -l README.md && git diff --check`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md assets/evidence-chain.svg tests/test_readme.py
git commit -m "docs: show the append-only evidence chain"
```

### Task 4: Run Lineage Core — exact versus proposed joins

**Files:**
- Create: `assets/lineage-join-map.svg`
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `join_records(records)` and the five documented classification values.
- Produces: a visual distinction between exact identifiers and non-promoting hints.

- [ ] **Step 1: Add the failing unittest**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReadmeTests(unittest.TestCase):
    def test_join_status_proof_and_relationship(self):
        text = (ROOT / "README.md").read_text("utf-8")
        for value in (
            "assets/lineage-join-map.svg", "join_records", "EXACT", "PROPOSED",
            "AMBIGUOUS", "UNMATCHED", "INCONCLUSIVE",
            "Part of the Mothership constellation.",
            "https://github.com/UMEBOSHIISAN/mothership",
            "does not install, invoke, or configure Run Lineage Core",
        ):
            self.assertIn(value, text)
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m unittest tests.test_readme -v`

Expected: FAIL on the missing asset reference.

- [ ] **Step 3: Add the SVG and compact README**

The diagram must show explicit task/run/manifest/hash evidence reaching `EXACT`, while timestamps and worker hints remain `PROPOSED`. Keep the in-memory-only/no-discovery/non-authorizing limits.

- [ ] **Step 4: Run native verification**

Run: `python3 -m unittest discover -s tests -v && python3 tools/check_public_boundary.py . && wc -l README.md && git diff --check`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md assets/lineage-join-map.svg tests/test_readme.py
git commit -m "docs: distinguish exact and proposed lineage"
```

### Task 5: Source Health Core — source envelope claim limits

**Files:**
- Create: `assets/source-envelope.svg`
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `component.health.v1`, `source.envelope.v1`, and `examples/quickstart.py`.
- Produces: an explicit validate/not-prove diagram and a clearer five-minute entry point.

- [ ] **Step 1: Add the failing unittest**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReadmeTests(unittest.TestCase):
    def test_source_claim_limit_and_relationship(self):
        text = (ROOT / "README.md").read_text("utf-8")
        for value in (
            "assets/source-envelope.svg", "component.health.v1", "source.envelope.v1",
            "does not prove that a value is true or fresh",
            "Part of the Mothership constellation.",
            "https://github.com/UMEBOSHIISAN/mothership",
            "does not install, invoke, or configure Source Health Core",
        ):
            self.assertIn(value, text)
```

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_readme -v`

Expected: FAIL on the asset/relationship additions.

- [ ] **Step 3: Add SVG and reorganize without inflating claims**

Place the five-minute quickstart and before/after example above audience detail. The SVG must label accepted shape separately from truth, freshness, approval, and execution, all of which remain unproved.

- [ ] **Step 4: Run native verification**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v && python3 tools/verify_public_boundary.py . && wc -l README.md && git diff --check`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md assets/source-envelope.svg tests/test_readme.py
git commit -m "docs: make source health claim limits visible"
```

### Task 6: Agent Decision Core — advisory gate proof

**Files:**
- Create: `assets/advisory-gate.svg`
- Create: `test/readme.test.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: `compileTaskContext`, `evaluateLocalFirstGate`, and `execution_allowed: false`.
- Produces: a provider-neutral advisory-gate visual and runnable Node example.

- [ ] **Step 1: Add the failing Node test**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('README proves advisory-only behavior and routes to Mothership', () => {
  const text = fs.readFileSync('README.md', 'utf8');
  for (const value of [
    'assets/advisory-gate.svg', 'compileTaskContext', 'evaluateLocalFirstGate',
    'execution_allowed: false', 'Part of the Mothership constellation.',
    'https://github.com/UMEBOSHIISAN/mothership',
    'does not install, invoke, or configure Agent Decision Core',
  ]) assert.ok(text.includes(value), value);
});
```

- [ ] **Step 2: Verify failure**

Run: `node --test test/readme.test.js`

Expected: FAIL on the missing asset/relationship wording.

- [ ] **Step 3: Add SVG and proof-first README**

The diagram must end every decision path at an advisory result with `execution_allowed: false`; it must not depict a worker launch. Keep the current example import names exact.

- [ ] **Step 4: Run native verification**

Run: `npm test && node tools/check-public-boundary.js . && wc -l README.md && git diff --check`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md assets/advisory-gate.svg test/readme.test.js
git commit -m "docs: visualize the advisory decision gate"
```

### Task 7: Knowledge Lifecycle Kit — human-gated lifecycle proof

**Files:**
- Create: `assets/knowledge-lifecycle.svg`
- Create: `tests/test_readme.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `knowledge-lifecycle-gate`, `llm-routing`, and current local verification guide.
- Produces: an inspect → propose → human decision visual with no machine-side transition.

- [ ] **Step 1: Add the failing unittest**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReadmeTests(unittest.TestCase):
    def test_human_gate_and_mothership_relationship(self):
        text = (ROOT / "README.md").read_text("utf-8")
        for value in (
            "assets/knowledge-lifecycle.svg", "knowledge-lifecycle-gate/", "llm-routing/",
            "Human authority remains required",
            "Part of the Mothership constellation.",
            "https://github.com/UMEBOSHIISAN/mothership",
            "does not install, invoke, or configure Knowledge Lifecycle Kit",
        ):
            self.assertIn(value, text)
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m unittest tests.test_readme -v`

Expected: FAIL on new asset/relationship wording.

- [ ] **Step 3: Add SVG and clarify the two-component entry point**

The diagram must show machine `inspect` and `propose`, then stop at a human decision boundary. Keep `selected_alias` and `actual_alias` empty in the explanation and do not imply suite registration.

- [ ] **Step 4: Run native verification**

Run: `python3 -m unittest discover -s tests -v && wc -l README.md && git diff --check`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md assets/knowledge-lifecycle.svg tests/test_readme.py
git commit -m "docs: show the human knowledge lifecycle gate"
```

### Task 8: Wave 3 ownership and evidence closeout

**Files:**
- Create in Mothership: `docs/launch/wave3-focused-primitives-receipt.md`

**Interfaces:**
- Consumes: six result commits, native test outputs, and README line counts.
- Produces: one Wave 4 audit input.

- [ ] **Step 1: Record evidence rows**

For each repository record source status, worktree, base, result commit, native test and boundary commands, result, README line count, and remaining dirty state.

- [ ] **Step 2: Name every README above 220 lines**

Include exact count and one-sentence reason; if there is no reason, return that repository to editing.

- [ ] **Step 3: Commit the receipt**

```bash
git add docs/launch/wave3-focused-primitives-receipt.md
git commit -m "docs: record focused primitive rollout evidence"
```
