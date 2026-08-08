# Mothership Product and Documentation Wave 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the verified Wave 1 hub into a compelling, accurate public product page with a tested 60-second path, complete English/Japanese guidance, and reproducible documentation evidence.

**Architecture:** Treat the root README as the product landing page and every supporting document as a deeper layer of the same contract. Generate the demo transcript from the real CLI, test every quick-start command and local link, and keep claims traceable to code or verification evidence.

**Tech Stack:** GitHub-flavored Markdown, Mermaid, Python 3.12 standard-library documentation tests, the actual `mothership` CLI, existing PNG brand assets.

## Global Constraints

- Preserve the fixed narrative order from the integrated-hub design.
- Lead with product value and a 60-second success path; move repository inventory and internals below the demonstrated outcome.
- Do not claim stars, users, production readiness, universal security, autonomous execution, automatic companion installation, zero local loopback traffic, or publication state.
- Every pasted CLI output must be generated from the current executable and byte-checked in tests.
- English and Japanese pages must agree on commands, versions, protocol order, authority boundaries, and companion responsibilities.
- Badge labels may summarize measured repository facts only. Avoid live counters or badges that imply popularity.
- Do not replace existing visual assets unless a measured rendering problem requires it; the brand-identity exclusion prohibits externalizing unrelated UMEBOSHI character/IP assets.
- No push, tag, release, package upload, or GitHub settings mutation is part of this wave.

---

### Task 0: Add reproducible quantitative evidence without inflating claims

**Files:**
- Create: `evaluation/corpus/protocol-validation.v1.json`
- Create: `evaluation/results/mothership-0.2.0.json`
- Create: `tools/run_evaluation.py`
- Create: `tests/test_evaluation.py`
- Create: `docs/research/paper-evidence.md`

- [ ] **Step 1: Write a failing evaluation contract test**

Require one deterministic JSON result that reports valid protocol acceptance, invalid protocol rejection, demo byte determinism, installed-resource integrity, and non-escalating authority/execution effects as separate measurements.

- [ ] **Step 2: Freeze a synthetic conformance corpus**

Cover all four protocol kinds with one valid case and five named invalid mutations each. Record the corpus SHA-256 in the result. The corpus is synthetic and must not contain user data, credentials, private paths, or real task outcomes.

- [ ] **Step 3: Implement a read-only evaluator**

`python tools/run_evaluation.py` reads only tracked corpus and packaged resources, prints one canonical JSON object, and performs no network, model, companion discovery, approval, or execution action. Run the demo across eight controlled process environments and require one distinct output.

- [ ] **Step 4: Record paper-ready evidence with explicit limits**

Separate Mothership conformance measurements from the Agent Frontdoor labeled-fixture measurements. Call corpus results internal or synthetic; never present them as production accuracy, external validity, user adoption, or a security certification.

- [ ] **Step 5: Test and commit**

```sh
python3 -m unittest tests.test_evaluation -v
python3 tools/run_evaluation.py
git diff --check
git add evaluation tools/run_evaluation.py tests/test_evaluation.py docs/research/paper-evidence.md
git commit -m "feat: add reproducible control-plane evaluation"
```

---

### Task 1: Lock the executable README contract before rewriting prose

**Files:**
- Create: `tests/test_documentation.py`
- Create: `docs/generated/demo-output.json`
- Create: `docs/generated/verify-output.json`

- [ ] **Step 1: Write failing generated-output tests**

Run `python3 -m mothership demo` and `python3 -m mothership verify` in a minimal environment. Require exact byte equality with the two checked-in generated files and parse each as one JSON object.

- [ ] **Step 2: Generate artifacts from the real CLI**

Capture stdout only. The files end in exactly one newline and contain no timestamps, hostnames, absolute paths, environment values, commands, credentials, or model output.

- [ ] **Step 3: Write failing README structure tests**

Require these H2 headings in this exact order:

```text
Quick start
See the whole control plane in 60 seconds
The problem
The Mothership answer
Architecture
Choose your adoption path
Safety guarantees
What Mothership is not
How it compares
Public API
Ecosystem protocols
Compatibility
Documentation
Contributing
Security
Roadmap
License
```

Also require one and only one fenced `sh` block marked by `<!-- quickstart:start -->` / `<!-- quickstart:end -->`, plus one fenced JSON transcript whose bytes match `docs/generated/demo-output.json` after the fence indentation is removed.

- [ ] **Step 4: Implement a quick-start extractor in the test only**

Extract non-comment shell lines and require exactly:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
mothership verify
mothership demo
```

The test must run equivalent commands in a temporary clone/copy and fresh environment, not `source` a user shell. No network is allowed after build prerequisites are present.

- [ ] **Step 5: Commit**

```sh
git add tests/test_documentation.py docs/generated/demo-output.json docs/generated/verify-output.json
git commit -m "test: lock executable documentation output"
```

---

### Task 2: Rebuild the English README as a product landing page

**Files:**
- Modify: `README.md`
- Modify: `tests/test_documentation.py`

- [ ] **Step 1: Write failing claim and link tests**

Require the hero promise:

```text
The portable, safety-first control plane for AI coding environments.
```

Require links to installation, architecture, composition, protocols, security, compatibility, roadmap, contributing, Japanese guide, license, and the four exact companion repositories. Reject banned claims and old topology text that routes Agent Frontdoor or WGM directly into a generic Mothership box without Router.

- [ ] **Step 2: Build the hero and 60-second path**

Use the existing whale logo above the product name and the existing banner after the quick success path. Include only factual badges: Python 3.12+, standard-library runtime, offline verification, MIT, and tests with a static label updated from measured suite output.

The first screenful must answer:

1. what Mothership is;
2. why it exists;
3. how to install and prove it works;
4. what it deliberately will not do.

- [ ] **Step 3: Embed the real deterministic demo**

Include the exact `mothership demo` JSON and explain that it validates composition only. Do not say the demo executed a worker, obtained approval, or contacted companions.

- [ ] **Step 4: Present the exact hub-and-spoke architecture**

Mermaid chain:

```text
Human request → Agent Frontdoor → WGM → Mothership Router → Secretary TUI
                                  ↘ Mothership protocol registry / verification hub ↗
```

The diagram and table must state that each companion remains independently installable and that Mothership does not auto-discover or auto-install it.

- [ ] **Step 5: Add standalone and composed adoption paths**

Document three paths only:

1. **Mothership alone — recommended first step:** install, verify, validate contracts, run diagnostics intentionally.
2. **One companion:** use a focused repository independently and validate its interchange document with Mothership.
3. **Full synthetic chain:** validate the four versioned documents without executing work.

- [ ] **Step 6: Add a concise comparison table**

Compare only Mothership, copying a home directory, an agent framework, and a model router across portability, secrets, authority, execution, and offline verification. Use neutral descriptions; do not disparage competitors or claim universal superiority.

- [ ] **Step 7: Verify rendering-oriented structure**

Require one H1, no skipped heading levels, unique heading anchors, meaningful image alt text, no raw absolute local paths, and a maximum line length exception only for badge/image/URL lines.

- [ ] **Step 8: Run and commit**

```sh
python3 -m unittest tests.test_documentation -v
git diff --check
git add README.md tests/test_documentation.py
git commit -m "docs: make README the Mothership product page"
```

---

### Task 3: Make supporting English documentation agree with the product contract

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/installation.md`
- Modify: `docs/composition.md`
- Modify: `docs/security.md`
- Modify: `docs/ecosystem-roadmap.md`
- Create: `docs/protocols.md`
- Create: `docs/compatibility.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Modify: `tests/test_documentation.py`

- [ ] **Step 1: Write a failing cross-document vocabulary test**

Define the canonical terms once in the test: `installable hub`, `independently adoptable`, `protocol-composition-only`, `authority_effect`, `execution_effect`, and the four ordered protocol kinds. Require their appropriate presence and reject contradictory phrases such as automatic routing, automatic installation, model invocation, or approval by validation.

- [ ] **Step 2: Update architecture**

Document package modules, immutable resources, CLI data flow, legacy compatibility, trust boundaries, and the difference between explicitly called mutation-capable APIs and read-only default CLI commands.

- [ ] **Step 3: Update installation lifecycle**

Provide clone-first, wheel, editable-development, update, verification, and uninstall paths. Every path names its side effects. No command should use `sudo`, mutate shell startup files, install hooks, or imply an online runtime.

- [ ] **Step 4: Update composition and add protocol reference**

`composition.md` explains responsibility and handoff order. `protocols.md` includes the registry fields, all versions, exact owner repository/source path, validation commands, safe example snippets, failure behavior, and schema-update procedure.

- [ ] **Step 5: Update security**

Threat-model explicit local JSON, packaged resources, diagnostics subprocesses, symlinks/special files, duplicate keys, oversized content, secret-like keys, terminal controls, and stale protocol snapshots. State residual risks and what installation itself can do.

- [ ] **Step 6: Add compatibility and contribution policies**

`compatibility.md` records Python, OS assumptions, old entry points, alias diagnostics, protocol matrix, and the exact Mothership release that freezes each snapshot. `CONTRIBUTING.md` gives setup, TDD, full verification, schema-owner coordination, checksum rules, and no-publication boundaries. `SECURITY.md` gives a private vulnerability-reporting path using GitHub Security Advisories and explicitly tells reporters not to open public issues containing secrets.

- [ ] **Step 7: Make the roadmap measurable**

Separate `shipped in 0.2.0`, `next candidates`, and `not planned`. Do not promise dates or popularity. Put automated companion installation, execution, retries, background services, and credential management under `not planned` unless a later design explicitly changes the boundary.

- [ ] **Step 8: Test and commit**

```sh
python3 -m unittest tests.test_documentation -v
git diff --check
git add docs CONTRIBUTING.md SECURITY.md tests/test_documentation.py
git commit -m "docs: align the integrated hub documentation"
```

---

### Task 4: Bring the Japanese guide to product-story parity

**Files:**
- Modify: `docs/ja/README.md`
- Modify: `tests/test_documentation.py`

- [ ] **Step 1: Write failing parity tests**

Require Japanese sections corresponding to quick start, 60-second demo, problem, answer, architecture, adoption paths, safety, non-goals, comparison, API, protocols, compatibility, documentation, contribution, security, roadmap, and license. Require the same five quick-start commands and four protocol kinds.

- [ ] **Step 2: Rewrite as a complete guide**

Translate meaning, not sentence order. Keep commands, JSON, module names, versions, repository names, and safety constants identical to English. Explain `authority_effect: false` and `execution_effect: false` in natural Japanese.

- [ ] **Step 3: Verify cross-language facts**

The test extracts Python/version values, command sequence, protocol order, companion URLs, and non-goals from both pages and compares structured values.

- [ ] **Step 4: Test and commit**

```sh
python3 -m unittest tests.test_documentation -v
git add docs/ja/README.md tests/test_documentation.py
git commit -m "docs: complete the Japanese product guide"
```

---

### Task 5: Validate every documentation command and link

**Files:**
- Create: `tests/test_markdown_links.py`
- Create: `tests/test_documentation_commands.py`

- [ ] **Step 1: Add local-link tests**

Parse Markdown links and images in all tracked `.md` files. Resolve relative paths and anchors; reject missing files, missing headings, escaping repository paths, `file://` URLs, private absolute paths, and empty alt text. Ignore only fenced examples explicitly labeled `non-executable`.

- [ ] **Step 2: Add public-link inventory tests**

Maintain an exact allowlist of official GitHub repository links, Python documentation, PyPI project location if and only if published, GitHub Security Advisories, and license references. This test checks URL shape offline. A separate attended audit may check HTTP status, but runtime tests never use the network.

- [ ] **Step 3: Execute documented local commands**

Extract executable code blocks from README, installation, composition, protocols, contributing, and Japanese README. Run each in an isolated temporary directory/environment with timeouts and a minimal environment. Fixture-producing commands must write only inside the temporary directory.

- [ ] **Step 4: Verify no documentation drift**

Run:

```sh
python3 -m unittest tests.test_documentation tests.test_markdown_links tests.test_documentation_commands -v
```

- [ ] **Step 5: Commit**

```sh
git add tests/test_markdown_links.py tests/test_documentation_commands.py
git commit -m "test: execute documentation and validate links"
```

---

### Task 6: Freeze release integrity after final documentation bytes

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `RELEASE_CHECKLIST.md`
- Modify: `SHA256SUMS`
- Create: `docs/verification/2026-08-09-product-docs-wave2.md`

- [ ] **Step 1: Record the 0.2.0 change without claiming publication**

Under `Unreleased`, describe installable hub, protocol registry, demo, public APIs, documentation redesign, compatibility, and safety boundaries. Do not create a release date or tag claim.

- [ ] **Step 2: Run full verification before checksums**

```sh
python3 -m unittest discover -s tests -v
python3 -m mothership verify
python3 -m mothership demo
python3 -m build --wheel --sdist
git diff --check
```

- [ ] **Step 3: Regenerate checksums deterministically**

Include every intended tracked public file except `.git/**`, build artifacts, caches, and `SHA256SUMS` itself. Sort bytewise by POSIX-relative path. Verify the manifest from a clean temporary checkout before committing it.

- [ ] **Step 4: Audit the rendered public surface**

Render Markdown locally or use GitHub's read-only rendering endpoint only if network access is explicitly available. Inspect hero crop, badge wrapping, Mermaid fallback, tables on narrow screens, code-block scrolling, image alt text, and all links. Record whether this was local-only or GitHub-rendered; do not imply remote publication.

- [ ] **Step 5: Run privacy and authority scans**

Review tracked bytes for private absolute paths, emails, hostnames, credentials, prompt/model-output keys, execution primitives, retry/fallback claims, and unverified metrics. Record every finding and disposition.

- [ ] **Step 6: Independent review and evidence**

Run Codex review over the Wave 2 range. Record commit range, test count, generated-output digests, checksum verification, link counts, rendering method, and unresolved remote publication work in the evidence document.

- [ ] **Step 7: Commit final frozen bytes**

```sh
git add CHANGELOG.md RELEASE_CHECKLIST.md SHA256SUMS docs/verification/2026-08-09-product-docs-wave2.md
git commit -m "docs: freeze Mothership 0.2.0 handoff evidence"
```
