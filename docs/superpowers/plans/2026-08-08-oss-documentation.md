# Mothership OSS Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish an English-first, visually clear, accurate documentation set that enables a new user to understand, install, verify, configure, update, and remove Mothership safely.

**Architecture:** `README.md` is the repository entry point. Detailed guidance lives under `docs/`; Mermaid supplies an editable architecture visual, while one original raster banner supplies project identity without asserting runtime behavior.

**Tech Stack:** GitHub Flavored Markdown, Mermaid, PNG asset, Python 3.12+ unittest, shell link/path checks.

## Global Constraints

- Document only observed behavior: local helpers, staged contracts, diagnostics, and user-reviewed configuration.
- Do not imply that Mothership installs hooks, edits settings, authorizes actions, invokes models, manages credentials, or deploys software.
- Configuration examples contain no personal paths, commands, endpoints, or credentials.
- Use English for the main documentation and a concise Japanese onboarding guide.

---

### Task 1: Create visual assets and documentation

**Files:**
- Create: `assets/mothership-banner.png`
- Create: `docs/architecture.md`
- Create: `docs/installation.md`
- Create: `docs/security.md`
- Create: `docs/ja/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `assets/mothership-logo.png`, `bootstrap/doctor.sh`, `config/executors.example.json`, `orchestration/bin/llm-doctor`, and `orchestration/bin/llm-seat`.
- Produces: four Markdown guides linked from `README.md`.

- [ ] **Step 1: Generate and add the original banner**

Generate `assets/mothership-banner.png`: an original dark-navy pixel-art scene of a friendly whale-shaped mothership travelling through a sparse star field. Do not imitate an identifiable existing game or include logos, lettering, or people.

- [ ] **Step 2: Write the architecture reference**

Create `docs/architecture.md` with a Mermaid `flowchart LR` containing `User`, `frontdoor`, `contracts`, `orchestration`, `safety`, and `local_config`. Describe routing, contract validation, diagnostic helpers, policy assessment, and the local configuration boundary. State that safety policy is non-authorizing.

- [ ] **Step 3: Write installation and lifecycle guidance**

Create `docs/installation.md` with clone, Python version, diagnostic, and test commands. State the Python 3.12+ requirement. Explain that diagnostics do not install software, authenticate, invoke models, or edit settings. Cover placeholder configuration review, updates by obtaining a new release, and removal by deleting the clone.

- [ ] **Step 4: Write security and Japanese entry guides**

Create `docs/security.md` covering no shipped secrets, local-only configuration, no authorization grant, no automatic hook/settings mutation, and the rule that users supply credentials only locally. Create `docs/ja/README.md` with a concise Japanese explanation, requirements, safe quick start, and links to English documentation.

- [ ] **Step 5: Replace README with a navigable entry point**

Add banner and logo with alt text. Include: Japanese guide link; one-sentence definition; feature list; explicit non-goals; Mermaid architecture overview; quick start; safe configuration note; verification/update/removal summary; detailed guide links; and MIT license link.

- [ ] **Step 6: Commit documentation content**

Run `git add README.md assets/mothership-banner.png docs/architecture.md docs/installation.md docs/security.md docs/ja/README.md` and `git commit -m "docs: add OSS onboarding guides"`.

### Task 2: Verify and publish documentation

**Files:**
- Modify: documentation files only if validation finds a defect.

**Interfaces:**
- Consumes: Task 1 Markdown and the existing unittest suite.
- Produces: a clean, pushed `main` branch containing the documentation commit.

- [ ] **Step 1: Run the complete test suite**

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. Expected: all tests pass.

- [ ] **Step 2: Check documentation integrity**

Search `README.md`, `docs`, `config`, and `assets` for `/Users/`, `/private/`, `ghp_`, `github_pat_`, or private-key markers. Verify Markdown targets exist and all five guides have a first-level heading; verify the README has a Mermaid code fence.

- [ ] **Step 3: Correct and persist verified documentation**

Commit any validation corrections with `docs: correct onboarding references`. Run `git push origin main`, then measure persistence with `git log -1 origin/main --format='%H %s'`. Expected: remote `main` contains the documentation commit.
