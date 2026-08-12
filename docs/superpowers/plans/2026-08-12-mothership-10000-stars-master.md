# Mothership 10,000 Stars Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Concentrate the public Mothership ecosystem into one truthful, proof-first acquisition funnel whose only star-oriented destination is `UMEBOSHIISAN/mothership`.

**Architecture:** Four independently testable waves preserve repository ownership: Mothership flagship conversion, four proof products, six focused primitives, then launch-kit and cross-repository audit. Every repository uses an isolated branch or worktree from a measured clean base and retains its native tests and release boundary.

**Tech Stack:** Markdown, editable SVG, PNG, GIF, Python 3.12+ unittest, pytest, Go, Node.js test runner, Git, GitHub metadata drafts.

## Global Constraints

- North Star is 10,000 GitHub stars on `UMEBOSHIISAN/mothership`; popularity is not guaranteed or reported as locally completed.
- `mothership` is the only star-oriented CTA; companions remain independently adoptable.
- No runtime behavior, dependency, repository name, ownership boundary, provider endorsement, or automatic cross-repository integration is added.
- No push, merge, tag, release, package upload, GitHub setting change, announcement post, CI/CD edit, deploy, scheduler, secret, auth, env, or infrastructure mutation.
- Behavioral claims come from current code, fixtures, examples, or passing repository-native tests.
- Raster art creates atmosphere only; behavioral visuals come from current CLI output, schemas, fixtures, or editable SVG.
- Existing dirty or unpushed work is never stashed, reset, cleaned, rebased, staged, or bundled.
- Python verification uses `/opt/homebrew/bin/python3` (currently Python 3.14.6 and compatible with the project floor of Python 3.12+).
- Each task ends with focused tests, native regression tests proportional to the change, diff checks, and a separate commit.

---

## Execution Order

### Task 1: Execute Wave 1 — Flagship conversion

**Files:**
- Execute: `docs/superpowers/plans/2026-08-12-mothership-10000-stars-wave1-flagship.md`

**Interfaces:**
- Consumes: verified Flight Recorder base `62240fd` and corrected ecosystem design `f937ccf`.
- Produces: Mothership README, visuals, real demo recording, and local contract tests used by Waves 2–4.

- [ ] **Step 1: Complete every Wave 1 checkbox in order**

Run the focused test after each task and the full 299-test suite at Wave 1 closeout.

- [ ] **Step 2: Record the Wave 1 commit range**

```bash
git log --oneline 62240fd..HEAD
```

Expected: only design commits and reviewed Wave 1 documentation/asset commits.

### Task 2: Execute Wave 2 — Four proof products

**Files:**
- Execute: `docs/superpowers/plans/2026-08-12-mothership-10000-stars-wave2-proof-products.md`

**Interfaces:**
- Consumes: the exact relationship wording and CTA hierarchy established in Wave 1.
- Produces: current, tested Tier 1 README funnels in four independent repositories.

- [ ] **Step 1: Complete each repository task independently**

Stop a repository if its measured base or native baseline fails. Continue only with repositories whose bases pass.

- [ ] **Step 2: Record one commit and test receipt per repository**

Expected receipt fields: repository, branch, base HEAD, result HEAD, native test command, result, dirty-tree status.

### Task 3: Execute Wave 3 — Six focused primitives

**Files:**
- Execute: `docs/superpowers/plans/2026-08-12-mothership-10000-stars-wave3-focused-primitives.md`

**Interfaces:**
- Consumes: Wave 1 relationship wording and visual grammar.
- Produces: six compact, evidence-backed README entry points and signature SVGs.

- [ ] **Step 1: Complete each repository task independently**

Use each repository's language and existing test runner. Do not introduce a common runtime dependency.

- [ ] **Step 2: Audit editorial length**

```bash
wc -l README.md
```

Expected: normally at most 180 lines. Any file above 220 lines is named with a reason in the Wave 4 closeout.

### Task 4: Execute Wave 4 — Launch kit and audit

**Files:**
- Execute: `docs/superpowers/plans/2026-08-12-mothership-10000-stars-wave4-launch-audit.md`

**Interfaces:**
- Consumes: locally committed results and measured test receipts from Waves 1–3.
- Produces: metadata drafts, English/Japanese launch copy, article outline, publication checklist, and factual cross-repository closeout.

- [ ] **Step 1: Complete local launch artifacts and checks**

Do not mutate GitHub or post externally.

- [ ] **Step 2: Stop at the publication checkpoint**

Expected: exact local commits and proposed remote actions are presented separately. Publication remains unexecuted until target-specific approval.

## Master Verification

### Task 5: Prove local completion without claiming publication

**Files:**
- Verify: all files named by the four wave plans
- Create: `docs/launch/2026-08-12-local-closeout.md`

**Interfaces:**
- Consumes: all wave receipts and repository HEADs.
- Produces: one factual, auditable local closeout.

- [ ] **Step 1: Write the closeout with exact evidence**

Use these headings and fields:

```markdown
## Implemented
- repository: branch, base, result commit, changed files

## Verification
- repository: command, exit, test count or explicit output marker

## Current state
- clean/dirty status and ownership of remaining changes

## Publication gates
- exact unexecuted remote actions

## Unknown
- GitHub traffic, rendered remote state, star conversion, package/release reachability
```

- [ ] **Step 2: Run the final Mothership suite**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -v`

Expected: 299 tests pass with the same six environment/tooling skips unless new documentation tests increase the total.

- [ ] **Step 3: Verify every repository is isolated and owned**

Run in each worktree:

```bash
git status --short --branch
git diff --check
git log -1 --oneline
```

Expected: no unstaged or staged task changes; one recorded result commit per repository.

- [ ] **Step 4: Commit the local closeout**

```bash
git add docs/launch/2026-08-12-local-closeout.md
git commit -m "docs: record 10000-star local rollout evidence"
```
