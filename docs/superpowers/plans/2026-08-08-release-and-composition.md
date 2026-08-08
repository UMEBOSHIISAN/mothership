# Mothership Release and Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish Mothership v0.1.1 with concrete, truthful usage and composition guidance.

**Architecture:** Add documentation-only composition guidance without creating runtime dependencies; then finalize metadata, a clone-verifiable checksum manifest, an annotated tag, and a GitHub Release.

**Tech Stack:** GitHub Flavored Markdown, Mermaid, POSIX shell, Python 3.12+ unittest, GitHub CLI.

## Global Constraints

- Companion repositories remain independently installable; automatic setup, invocation, configuration, shared credentials, and authority are never claimed.
- Private governance OS files, paths, hosts, services, credentials, business data, and production automation are excluded.
- Mothership does not install software, authenticate, execute models, modify settings, add hooks, or perform external actions.
- Tests use `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -m unittest discover -s tests -v`.
- `SHA256SUMS` excludes `.git` and `SHA256SUMS` itself.

### Task 1: Add composition and roadmap documents

**Files:** Create `docs/composition.md` and `docs/ecosystem-roadmap.md`; modify `README.md` and `docs/ja/README.md`.

**Interfaces:** The documentation consumes existing public repository names and URLs. It produces human-led adoption recipes only.

- [ ] Create `docs/composition.md` with four sections: Mothership alone; Agent Frontdoor then Mothership; Mothership then Secretary TUI; optional Git Vibes and Toygarden. Each section explicitly says repositories are installed, configured, and reviewed separately.
- [ ] Create `docs/ecosystem-roadmap.md` with a released Mothership row and a planned, clean-room Workflow Governance Model row. Describe Decision Record Gate, Authority Boundary Framework, and Context & Memory Trust Patterns as future generic templates requiring anonymization and independent verification.
- [ ] Link both files from the English README; add the composition-guide link to the Japanese guide.
- [ ] Run a scan for private absolute paths, operational-service names, tokens, and private-key markers in both new documents; expect no findings.
- [ ] Commit with `git add README.md docs/composition.md docs/ecosystem-roadmap.md docs/ja/README.md && git commit -m "docs: add composition and ecosystem guidance"`.

### Task 2: Prepare reproducible release metadata

**Files:** Modify `VERSION`, `CHANGELOG.md`, and `SHA256SUMS`.

**Interfaces:** The release consumes the final tracked tree and produces version `0.1.1`, a dated release note, and an integrity manifest.

- [ ] Set `VERSION` to `0.1.1`.
- [ ] Prepend `CHANGELOG.md` with a dated `0.1.1` entry for composition guidance, the planned governance roadmap, and clone-verifiable checksums; explicitly state that no runtime integration or automatic setup was added.
- [ ] Generate the manifest with `LC_ALL=C git ls-files -z | tr '\0' '\n' | LC_ALL=C sort | grep -vx 'SHA256SUMS' | xargs shasum -a 256 > SHA256SUMS`.
- [ ] Verify it with `shasum -a 256 -c SHA256SUMS` and expect every file to report `OK`.
- [ ] Commit with `git add VERSION CHANGELOG.md SHA256SUMS && git commit -m "chore: release v0.1.1"`.

### Task 3: Verify and publish v0.1.1

**Files:** Verify tracked tree and GitHub release metadata only.

**Interfaces:** Consumes committed `main`; produces tag `v0.1.1`, a GitHub Release, and an attached checksum asset.

- [ ] Run the required unittest command; expect 132 passing tests.
- [ ] Run `git diff --check`; expect no output.
- [ ] Scan `$(git ls-files)` for private absolute paths, GitHub tokens, and private-key markers; expect no findings.
- [ ] Push `main`, create annotated tag `v0.1.1`, then push the tag.
- [ ] Create GitHub Release `v0.1.1`, attach `SHA256SUMS`, and state that composition guidance and reproducible verification were added without new execution authority.
- [ ] Measure release URL, target commit, attached asset, and remote tag with `gh release view v0.1.1 --json url,tagName,targetCommitish,assets` and `git ls-remote --tags origin v0.1.1`.
