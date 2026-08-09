# Mothership Companion Conformance Wave 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agent Frontdoor, Workflow Governance Model, Mothership Router, and Secretary TUI independently prove conformance to the protocol snapshots frozen by Mothership 0.2.0 without merging repositories or overwriting unrelated local work.

**Architecture:** Each semantic owner keeps its schema and one synthetic example in its own repository. Each repository records a small closed conformance manifest and tests its own public output. Mothership snapshots exact owner bytes, verifies digests and chain continuity, and records the exact companion commits used for the suite audit.

**Tech Stack:** Python 3.10+/3.12+, Go 1.26.x, standard repository-native test runners, JSON Schema artifacts, Git worktrees for isolation.

## Global Constraints

- Companion repositories remain independently installable and releasable. Do not add Mothership as a runtime dependency.
- Use separate worktrees. Never edit the dirty Agent Frontdoor checkout or overwrite the unpushed Secretary TUI branch.
- Before staging in any repository, inspect `git diff -- <file>` and confirm every hunk belongs to this wave.
- Schema ownership is one-way: owner repository source bytes → Mothership frozen snapshot. Never silently edit both into agreement; change owner first, test it, then refresh the snapshot and digest.
- Conformance means shape/version/safety compatibility only. It does not mean approval, execution, freshness, remote publication, or release reachability.
- Use each repository's native full test command; a green Mothership suite cannot substitute for companion tests.
- No push, tag, release, deployment, GitHub settings change, or cleanup of pre-existing work is authorized.

---

### Task 0: Isolate all repository state and record immutable baselines

**Files:**
- Create in Mothership: `docs/verification/2026-08-09-companion-baselines.md`
- No source modifications in companion repositories yet.

- [ ] **Step 1: Re-read project rules in each repository**

For each companion, read root `README.md`, `CLAUDE.md`, `AGENTS.md`, and `active_next.md` when present. Record absent files explicitly. Stop if a more specific policy conflicts with this plan.

- [ ] **Step 2: Record current ownership state**

For each checkout record:

- absolute checkout used only for inspection;
- current branch and HEAD;
- `origin/main` commit;
- tracked modifications and untracked paths;
- latest tag;
- native language/tool version;
- current full-test command and result.

Do not copy private paths into public docs; keep the public evidence to repository name and commit ID.

- [ ] **Step 3: Create isolated worktrees**

Use explicit new branch names:

```text
codex/mothership-0.2-conformance-frontdoor
codex/mothership-0.2-conformance-wgm
codex/mothership-0.2-conformance-router
codex/mothership-0.2-conformance-secretary
```

Base Frontdoor, WGM, and Router on their inspected `origin/main`. Base Secretary on the reviewed local commit that contains the already-created governance reader only if every ahead commit is verified as intended user work; otherwise base on `origin/main` and reapply no user changes.

- [ ] **Step 4: Verify isolation**

Original checkout status must remain byte-for-byte unchanged. New worktrees must be clean. Record branch, base commit, and worktree ownership.

- [ ] **Step 5: Commit baseline evidence in Mothership**

```sh
git add docs/verification/2026-08-09-companion-baselines.md
git commit -m "docs: record companion conformance baselines"
```

---

### Task 1: Prove Agent Frontdoor owns `frontdoor-task` intake.v0

**Repository:** `agent-frontdoor`

**Files:**
- Create: `suite/mothership-0.2-conformance.json`
- Create: `examples/mothership-task.json`
- Create: `tests/test_mothership_conformance.py`
- Create: `docs/mothership-suite.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write a failing owner/digest conformance test**

The manifest has exact fields:

```json
{
  "schema_version": "mothership.conformance.v1",
  "suite_release": "0.2.0",
  "repository": "agent-frontdoor",
  "protocol_kind": "frontdoor-task",
  "protocol_version": "intake.v0",
  "schema_path": "src/frontdoor/schema/intake.v0.json",
  "schema_sha256": "<lowercase digest>",
  "example_path": "examples/mothership-task.json",
  "authority_effect": false,
  "execution_effect": false
}
```

The test rejects extra fields, mismatched repository/kind/version, non-canonical paths, stale digest, missing files, and authority/execution true.

- [ ] **Step 2: Add one synthetic output card**

Use task ID `demo-review-001` and capability `code-review`, with fictional metadata matching Mothership's golden fixture. Validate it through the existing production `load_card`/validator path and through the owner schema.

- [ ] **Step 3: Prove CLI output ownership**

Run `agent-frontdoor validate examples/mothership-task.json`; require exit 0 and `VALID demo-review-001`. The test must also confirm `card` and `explain` never add protocol fields or authority claims.

- [ ] **Step 4: Document suite relationship**

State that Agent Frontdoor owns intake semantics, Mothership freezes exact bytes for composition, and neither validation nor a `human_gate` value executes work. Link the exact Mothership protocol reference.

- [ ] **Step 5: Run native verification and commit**

```sh
python -m pytest -q
python -m build --wheel --sdist
git diff --check
git add suite examples/mothership-task.json tests/test_mothership_conformance.py docs/mothership-suite.md README.md CHANGELOG.md
git commit -m "test: prove Mothership frontdoor conformance"
```

---

### Task 2: Prove WGM owns `governance-handoff` 1.0

**Repository:** `workflow-governance-model`

**Files:**
- Create: `suite/mothership-0.2-conformance.json`
- Create: `tests/test_mothership_conformance.py`
- Create: `docs/mothership-suite.md`
- Modify: `examples/handoff.valid.json`
- Modify: `README.md`
- Modify: `docs/compatibility.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write the failing conformance-manifest test**

Use the same closed manifest shape as Task 1 with:

```text
repository = workflow-governance-model
protocol_kind = governance-handoff
protocol_version = 1.0
schema_path = schemas/workflow-handoff.schema.json
example_path = examples/handoff.valid.json
```

- [ ] **Step 2: Align the public example with the golden chain**

Use `task_id: demo-review-001`, `capability: code-review`, a low risk, a positive fictional token budget, and non-path evidence identifiers. Run it through `validate_handoff` and require zero errors.

- [ ] **Step 3: Test forbidden authority carriers**

For every `execution_permission`, `approved`, `command`, `prompt`, `model_output`, `credential`, and private absolute path field, require the production validator to reject the document. Do not change the 1.0 accepted field set.

- [ ] **Step 4: Document compatibility**

Record Mothership 0.2.0 / governance-handoff 1.0 compatibility and the owner/snapshot relationship. Make explicit that Router receives reviewed metadata, not execution authority.

- [ ] **Step 5: Run native verification and commit**

```sh
python3 -m unittest discover -s tests -v
python3 -m build --wheel --sdist
git diff --check
git add suite tests/test_mothership_conformance.py docs/mothership-suite.md examples/handoff.valid.json README.md docs/compatibility.md CHANGELOG.md
git commit -m "test: prove Mothership handoff conformance"
```

---

### Task 3: Version and emit the Router manifest protocol

**Repository:** `mothership-router`

**Files:**
- Create: `src/mothership_router/schema/router-manifest.1.0.schema.json`
- Create: `src/mothership_router/schema/__init__.py`
- Create: `suite/mothership-0.2-conformance.json`
- Create: `examples/router-manifest.json`
- Create: `tests/test_mothership_conformance.py`
- Modify: `src/mothership_router/core.py`
- Modify: `src/mothership_router/__main__.py`
- Modify: `tests/test_core.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/composition.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing exact-manifest tests**

Require every `advisory_route` branch to return exactly:

```text
schema_version, task_id, capability, status, recommended_alias,
registry_sha256, reasons, authority_effect, execution_effect
```

For WGM input, preserve its task ID and capability. For legacy simple task input, `task_id` is null and a valid capability is preserved. Invalid values become null; they are never stringified.

- [ ] **Step 2: Add the owner schema**

Use the exact closed Router manifest 1.0 shape frozen in Wave 1. Package it via:

```toml
[tool.setuptools.package-data]
mothership_router = ["schema/*.json"]
```

The conformance test validates every production branch against this schema and requires byte identity between the owner schema and Mothership's eventual snapshot.

- [ ] **Step 3: Implement the smallest compatible manifest change**

Add `schema_version: "1.0"`, `task_id`, and `capability` to `_manifest`. Keep existing statuses, recommendation logic, digest binding, reason codes, and false effect flags. Do not add execution or fallback.

- [ ] **Step 4: Make CLI JSON deterministic and non-leaking**

Emit canonical compact JSON plus one newline. File read/parse failures return a fixed error code/message without echoing paths or exception details. Preserve two explicit input files and exit code 2 for input/usage failure.

- [ ] **Step 5: Add the synthetic example and conformance manifest**

The example is the exact output for WGM `demo-review-001` against a ready fictional `code-review` executor without an approval; status is `approval_required` and both effects are false.

- [ ] **Step 6: Version compatibility accurately**

Bump the package minor version to `0.3.0` because the closed output object gains required fields. Record that old consumers ignoring unknown fields remain source-compatible, but exact-shape consumers must select manifest 1.0 deliberately.

- [ ] **Step 7: Run native verification and commit**

```sh
python3 -m unittest discover -s tests -v
python3 -m build --wheel --sdist
git diff --check
git add src/mothership_router pyproject.toml suite examples/router-manifest.json tests README.md docs/composition.md CHANGELOG.md
git commit -m "feat: version Router manifests for Mothership"
```

---

### Task 4: Make Secretary TUI emit a read-only observation snapshot

**Repository:** `secretary-tui`

**Files:**
- Create: `schemas/observation-snapshot.1.0.schema.json`
- Create: `suite/mothership-0.2-conformance.json`
- Create: `examples/router-manifest.json`
- Create: `examples/observation-snapshot.json`
- Create: `conformance_test.go`
- Modify: `governance.go`
- Modify: `governance_test.go`
- Modify: `main.go`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing observation-object tests**

Add a pure function:

```go
func observationSnapshot(snapshot governanceSnapshot) (observationDocument, error)
```

The output has the exact Wave 1 schema fields: schema version, task ID, source kind/version, status, sanitized summary lines, and false authority/execution effects. It rejects unavailable or unsafe snapshots.

- [ ] **Step 2: Accept Router manifest 1.0 explicitly**

Extend `routerManifest` with schema version, task ID, and capability. Require schema version 1.0 for the new form. Keep a tested compatibility path for the previous unversioned 0.2.x form only when the user explicitly displays it; only the 1.0 form is eligible for observation export.

- [ ] **Step 3: Add one isolated export mode**

CLI form:

```sh
secretary-tui --snapshot-json --governance FILE
```

It reads only that explicit file, performs no dashboard refresh and no external command, emits one canonical JSON observation, and exits. `--snapshot-json` without `--governance`, or combined with `--dump`, exits 2 before reading anything.

- [ ] **Step 4: Test read-only and terminal-safety behavior**

Require no file writes, no `llm-seat.sh`, no timers, no home-directory reads, stable output under different locale/home/cwd, control-character sanitization, 1 MiB limit, secret-key rejection, false effects, and fixed path-free errors.

- [ ] **Step 5: Add owner schema, examples, and manifest**

The conformance manifest uses:

```text
repository = secretary-tui
protocol_kind = observation-snapshot
protocol_version = 1.0
schema_path = schemas/observation-snapshot.1.0.schema.json
example_path = examples/observation-snapshot.json
```

The example is generated from the bundled Router example and must byte-match the public CLI output.

- [ ] **Step 6: Run native verification and commit**

```sh
go test ./...
go vet ./...
go build ./...
git diff --check
git add schemas suite examples conformance_test.go governance.go governance_test.go main.go README.md CHANGELOG.md
git commit -m "feat: emit safe Mothership observation snapshots"
```

---

### Task 5: Refresh Mothership from owner bytes and audit the live chain

**Repository:** `mothership`

**Files:**
- Modify: `mothership/resources/protocols/registry.json`
- Modify: `mothership/resources/protocols/schemas/*.json`
- Modify: `mothership/resources/golden-path/*.json`
- Modify: `mothership/resources/inventory.json`
- Create: `tools/check_companion_conformance.py`
- Create: `tests/test_companion_conformance_tool.py`
- Modify: `docs/compatibility.md`
- Modify: `docs/protocols.md`
- Modify: `README.md`
- Modify: `docs/ja/README.md`

- [ ] **Step 1: Write a failing explicit-path audit test**

The development-only tool accepts four explicit repository roots and never auto-discovers paths. It checks:

- closed conformance manifest shape;
- expected repository/kind/version tuple;
- schema and example existence below the supplied root;
- owner schema SHA-256;
- byte identity with bundled Mothership snapshot;
- example validation through Mothership;
- exact ordered chain and shared ID/capability/status fields.

It must reject symlinks, path traversal, wrong repository ordering, missing owners, stale commits, and effect escalation.

- [ ] **Step 2: Refresh snapshots only from tested owner commits**

Copy exact owner schema bytes. Update registry digest and upstream source path. Refresh Router/Secretary fixtures from their public examples, then regenerate the packaged inventory. Do not hand-edit Mothership copies after copying.

- [ ] **Step 3: Record exact commit compatibility**

In `docs/compatibility.md`, list repository, owner release/version, protocol, exact tested commit, schema digest, and verification result. Label every remote-unreachable commit `local-only / publication pending`.

- [ ] **Step 4: Run the explicit conformance tool**

Run it against the four isolated worktrees. Require one canonical JSON report with four passing owners and a passing chain, false effects, and no absolute paths in output.

- [ ] **Step 5: Re-run all Mothership checks**

```sh
python3 -m unittest discover -s tests -v
python3 -m mothership verify
python3 -m mothership demo
python3 -m build --wheel --sdist
git diff --check
```

- [ ] **Step 6: Commit**

```sh
git add mothership/resources tools/check_companion_conformance.py tests/test_companion_conformance_tool.py docs/compatibility.md docs/protocols.md README.md docs/ja/README.md
git commit -m "test: verify the Mothership companion chain"
```

---

### Task 6: Execute the suite matrix and close local implementation truthfully

**Files:**
- Create in Mothership: `docs/verification/2026-08-09-companion-conformance-wave3.md`
- Modify in Mothership: `RELEASE_CHECKLIST.md`
- Modify in Mothership: `SHA256SUMS`

- [ ] **Step 1: Run every repository from a clean environment**

Record exact tool versions, commands, test counts, build artifacts, and SHA-256 values. Repeat the Mothership explicit-path conformance audit only after all owner commits are final.

- [ ] **Step 2: Review each repository independently**

Run Codex review on each exact conformance commit/range. Fix actionable findings in the owning repository first, then refresh Mothership snapshots and repeat the whole chain audit.

- [ ] **Step 3: Prove original worktrees were preserved**

Compare original checkout status and HEAD against Task 0 baselines. Record that pre-existing untracked/modified/ahead state is unchanged. Do not clean it.

- [ ] **Step 4: Freeze Mothership integrity last**

Regenerate `SHA256SUMS`, verify it in a clean Mothership checkout, rerun package/README/link/privacy/boundary checks, and commit only the intended final bytes.

- [ ] **Step 5: Record publication boundary**

The closeout must distinguish:

- local implementation complete;
- local tests/build/conformance complete;
- commits created;
- push reachability unknown or pending;
- tags/releases/packages not created;
- GitHub-rendered pages not yet measured.

Do not mark the public rollout complete until remote commit reachability and GitHub rendering are separately measured after explicit publication authorization.

- [ ] **Step 6: Commit final evidence**

```sh
git add docs/verification/2026-08-09-companion-conformance-wave3.md RELEASE_CHECKLIST.md SHA256SUMS
git commit -m "docs: record suite conformance evidence"
```
