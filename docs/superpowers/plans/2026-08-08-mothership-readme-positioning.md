# Mothership README Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public README accurately present Mothership as a safety-first control plane for portable AI coding environments and document its composable OSS ecosystem.

**Architecture:** `README.md` becomes the complete product entry page. Existing detailed guides remain the source of deep operational detail; the README links to them while adding verified capability, composition, and use-case views.

**Tech Stack:** GitHub Flavored Markdown, Mermaid, existing PNG assets, Python 3.12+ unittest, GitHub links.

## Global Constraints

- Document only observed Mothership behavior: closed contracts, fail-closed validation, advisory routing, durable approval-ledger primitives, local diagnostics, configuration templates, and explicit authority boundaries.
- Do not claim automatic environment migration, model execution, hook installation, credential management, remote synchronization, approval, automatic ecosystem installation, or runtime dependencies between repositories.
- Describe Codex CLI, Claude Code, and Ollama Local as represented local adapter aliases only.
- Keep the English README primary and preserve a concise Japanese guide.

---

### Task 1: Expand the README narrative and capability map

**Files:**
- Modify: `README.md`
- Modify: `docs/ja/README.md`

**Interfaces:**
- Consumes: `orchestration/adapters/README.md`, `frontdoor/route.py`, `safety/policy.py`, `evidence/contracts/approval-event.schema.json`, and existing detailed guides.
- Produces: README anchors linked by the Japanese guide: `#capabilities`, `#portable-by-design`, `#composable-ecosystem`, and `#frequently-asked-questions`.

- [ ] **Step 1: Write the new hero and problem statement**

Use the heading `# Mothership` followed by the tagline `A safety-first control plane for portable AI coding environments.` Explain that it makes a reviewable, repeatable foundation for Codex CLI, Claude Code, and Ollama Local; it does not copy secrets or automatically migrate a personal machine.

- [ ] **Step 2: Add verified capability and portability tables**

Add a `## Capabilities` table for closed contracts, advisory routing, approval-ledger primitives, local diagnostics, path/configuration boundaries, and verification. Add a `## Portable by design` table that separates shipped items from local-only items: contracts/templates/tests versus credentials/personal paths/model execution/approval.

- [ ] **Step 3: Add use cases and compatibility map**

Add the use cases `New machine`, `Teammate handoff`, `Dedicated mini machine`, and `Reproducible rebuild`. Add a compatibility table with `claude-code-agent`, `codex-cli`, and `ollama-local`, each described as a diagnostic/plan alias rather than an automatically launched integration.

- [ ] **Step 4: Update the Japanese guide**

Add a Japanese paragraph that describes Mothership as a common control foundation rather than a Codex-only package, and link it to the expanded English README sections.

- [ ] **Step 5: Commit narrative content**

Run `git add README.md docs/ja/README.md` followed by `git commit -m "docs: position Mothership as a control plane"`.

### Task 2: Add the composable ecosystem map and FAQ

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: public README evidence from `agent-frontdoor`, `secretary-tui`, `git-vibes`, and `toygarden`.
- Produces: direct repository links and a Mermaid map that labels every repository as independently adoptable.

- [ ] **Step 1: Add the composition diagram**

Add a Mermaid flowchart whose nodes are `Agent Frontdoor`, `Mothership`, `Secretary TUI`, `Git Vibes`, and `Toygarden`. Label links as `preflight task cards`, `read-only observability`, `optional human ritual`, and `adjacent creative toolkit`; include a visible note that the links are conceptual composition, not installed dependencies.

- [ ] **Step 2: Add the ecosystem table**

Link to `https://github.com/UMEBOSHIISAN/agent-frontdoor`, `https://github.com/UMEBOSHIISAN/secretary-tui`, `https://github.com/UMEBOSHIISAN/git-vibes`, and `https://github.com/UMEBOSHIISAN/toygarden`. Describe each repository only in its verified public role and state that each can be adopted independently.

- [ ] **Step 3: Add the FAQ**

Add questions that answer: whether it is Codex-only; whether it runs models; whether secrets travel; whether it is an automatic environment copier; how a new machine uses it; and how the companion repositories relate.

- [ ] **Step 4: Commit ecosystem content**

Run `git add README.md` followed by `git commit -m "docs: map the Mothership ecosystem"`.

### Task 3: Verify and publish the positioning update

**Files:**
- Modify: `README.md` or `docs/ja/README.md` only if validation detects a defect.

**Interfaces:**
- Consumes: completed Markdown and the existing unittest suite.
- Produces: a clean remote `main` branch containing the documentation update.

- [ ] **Step 1: Check source integrity**

Verify that the README contains headings for `Capabilities`, `Portable by design`, `Composable ecosystem`, and `Frequently asked questions`; verify internal Markdown targets; and scan the updated documents for secret markers and machine-specific absolute paths.

- [ ] **Step 2: Run the complete test suite**

Run `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -m unittest discover -s tests -v`. Expected: all tests pass.

- [ ] **Step 3: Commit validation corrections if needed**

If validation finds a documentation error, stage only the corrected Markdown files and commit with `docs: correct Mothership positioning references`.

- [ ] **Step 4: Push and measure persistence**

Run `git push origin main`, then run `git log -1 origin/main --format='%H %s'`. Expected: the remote contains the final documentation commit.
