# Mothership Hub Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an installable, standard-library-only Mothership package with stable public facades, a fail-closed protocol registry, deterministic offline verification, and one synthetic ecosystem demo.

**Architecture:** Keep `orchestration.lib` as the implementation SSOT and expose thin `mothership.*` facades. Package immutable schemas, registry metadata, and fixtures under `mothership/resources/`; load them through `importlib.resources`, validate them with a deliberately small closed-schema validator, and expose all behavior through one argparse CLI shared by the console script and `python -m mothership`.

**Tech Stack:** Python 3.12+, standard library at runtime, `unittest`, `setuptools` build metadata, JSON Schema Draft 2020-12 documents as frozen protocol artifacts.

## Global Constraints

- Preserve `bootstrap/doctor.sh`, `orchestration/bin/llm-doctor`, `orchestration/bin/llm-seat`, `frontdoor.route`, and all current `orchestration.lib` imports.
- Runtime commands may read only explicit files or packaged resources. They must not discover companion repositories, install software, read credentials, retry, invoke a model, mutate configuration, or direct traffic to an external network.
- `doctor` may issue only the already documented fixed diagnostic probes through `orchestration.lib.adapters.doctor_adapter`. The `ollama list` probe may query an installed Ollama daemon on its default loopback endpoint after endpoint overrides are removed from the child environment.
- The new `mothership` CLI does not mutate user or repository state. Compatibility APIs write only when the caller explicitly supplies a bounded scope/output/ledger target; the preserved `llm-seat approve` command explicitly appends its ledger event.
- Every JSON command writes exactly one canonical JSON object to stdout. Human-readable diagnostics go to stderr only when argument parsing itself fails.
- A valid protocol document is metadata, not approval. `authority_effect` and `execution_effect` remain false in Router and observation documents.
- Use test-first cycles: add one focused failing test, run it and observe the intended failure, implement the minimum behavior, then rerun the focused and regression tests.
- Do not push, tag, release, upload, or change a remote as part of this wave.

---

### Task 1: Establish installable package metadata and entry-point parity

**Files:**
- Create: `pyproject.toml`
- Create: `mothership/__init__.py`
- Create: `mothership/__main__.py`
- Create: `mothership/cli.py`
- Create: `tests/test_package_entrypoints.py`
- Modify: `VERSION`

- [ ] **Step 1: Write failing version and entry-point tests**

Add tests that require:

```python
from importlib.metadata import version
from pathlib import Path
import mothership

self.assertEqual("0.2.0", mothership.__version__)
self.assertEqual(Path("VERSION").read_text("utf-8").strip(), mothership.__version__)
self.assertEqual(mothership.__version__, version("mothership-control-plane"))
```

Run:

```sh
python3 -m unittest tests.test_package_entrypoints -v
```

Expected: FAIL because the package and distribution metadata do not exist.

- [ ] **Step 2: Add the minimal package and metadata**

Use this distribution contract in `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "mothership-control-plane"
dynamic = ["version"]
requires-python = ">=3.12"
dependencies = []
readme = "README.md"
license = "MIT"

[project.scripts]
mothership = "mothership.cli:main"

[tool.setuptools.dynamic]
version = {file = ["VERSION"]}

[tool.setuptools.packages.find]
include = ["mothership*", "orchestration*", "frontdoor*", "safety*", "evidence*"]

[tool.setuptools.package-data]
mothership = ["resources/**/*.json"]
```

Set `VERSION` to `0.2.0`. `mothership.__version__` must read installed distribution metadata and use the repository `VERSION` only as a clone-first fallback. `mothership.__main__` must contain only `raise SystemExit(main())` under the main guard.

- [ ] **Step 3: Add parser-only help behavior**

`mothership.cli.build_parser()` defines `verify`, `doctor`, `protocol`, and `demo` subcommands. At this task, handlers may return a closed `not_implemented` object and exit 1; `--help` must already exit 0 with no import-time side effects.

- [ ] **Step 4: Verify both entry forms**

Run:

```sh
python3 -m unittest tests.test_package_entrypoints -v
python3 -m mothership --help
python3 -m unittest discover -s tests -v
```

Expected: new tests pass and all pre-existing tests remain green.

- [ ] **Step 5: Commit**

```sh
git add pyproject.toml VERSION mothership/__init__.py mothership/__main__.py mothership/cli.py tests/test_package_entrypoints.py
git commit -m "feat: add installable Mothership package"
```

---

### Task 2: Expose compatibility facades without duplicating implementations

**Files:**
- Create: `mothership/scope.py`
- Create: `mothership/approval.py`
- Create: `mothership/adapters.py`
- Create: `mothership/contracts.py`
- Create: `tests/test_public_facades.py`

- [ ] **Step 1: Write identity-based failing tests**

Assert facade objects are the authoritative objects, not wrappers or copies:

```python
from mothership import adapters, approval, contracts, scope
from orchestration.lib import adapters as old_adapters
from orchestration.lib import ledger, paths

self.assertIs(scope.prepare_scope, paths.prepare_scope)
self.assertIs(scope.validate_relative_path, paths.validate_relative_path)
self.assertIs(approval.make_binding, ledger.make_binding)
self.assertIs(approval.start_attempt, ledger.start_attempt)
self.assertIs(adapters.doctor_adapter, old_adapters.doctor_adapter)
```

Also assert every facade has a closed, alphabetized `__all__`, and importing it performs no I/O.

Run the focused test and observe `ModuleNotFoundError`.

- [ ] **Step 2: Add explicit re-export modules**

Re-export only documented public dataclasses, exceptions, and functions. Do not use wildcard imports. `mothership.contracts` must expose strict JSON loading, canonical bytes/digests, built-in contract validation, and registry loading from the current authoritative modules.

- [ ] **Step 3: Verify old and new names together**

Run:

```sh
python3 -m unittest tests.test_public_facades tests.test_paths tests.test_ledger tests.test_adapters tests.test_contracts -v
```

Expected: facade identity checks and old import tests pass.

- [ ] **Step 4: Commit**

```sh
git add mothership/scope.py mothership/approval.py mothership/adapters.py mothership/contracts.py tests/test_public_facades.py
git commit -m "feat: expose stable Mothership APIs"
```

---

### Task 3: Freeze the four suite protocols and their ownership metadata

**Files:**
- Create: `mothership/resources/__init__.py`
- Create: `mothership/resources/protocols/registry.json`
- Create: `mothership/resources/protocols/schemas/frontdoor-task.intake.v0.schema.json`
- Create: `mothership/resources/protocols/schemas/governance-handoff.1.0.schema.json`
- Create: `mothership/resources/protocols/schemas/router-manifest.1.0.schema.json`
- Create: `mothership/resources/protocols/schemas/observation-snapshot.1.0.schema.json`
- Create: `tests/test_protocol_registry.py`

- [ ] **Step 1: Write registry invariant tests**

The test must require exactly this ordered kind set:

```python
KINDS = (
    "frontdoor-task",
    "governance-handoff",
    "router-manifest",
    "observation-snapshot",
)
```

For every entry assert exact keys:

```text
kind, schema_version, owner_repository, upstream_source_path,
bundled_schema_path, schema_sha256, predecessors, successors,
authority_capable, execution_capable, frozen_in_mothership
```

Require `frozen_in_mothership == "0.2.0"`; lowercase 64-hex digests; one connected chain; no unknown registry keys; and false authority/execution capability for every initial protocol.

Run and observe missing-resource failure.

- [ ] **Step 2: Copy the two owner-defined schemas byte-for-byte**

Copy Agent Frontdoor `src/frontdoor/schema/intake.v0.json` and WGM `schemas/workflow-handoff.schema.json` without semantic edits. Record their upstream paths and exact SHA-256 values.

- [ ] **Step 3: Define Router manifest 1.0**

The closed object has these required fields:

```json
{
  "schema_version": "1.0",
  "task_id": "<nonempty string or null>",
  "capability": "<nonempty string or null>",
  "status": "invalid_input | human_review_required | no_ready_executor | approval_required | approved_dry_run",
  "recommended_alias": "<nonempty string or null>",
  "registry_sha256": "<64 lowercase hex or null>",
  "reasons": ["<nonempty string>", "..."],
  "authority_effect": false,
  "execution_effect": false
}
```

`additionalProperties` is false. The planned owner path is `mothership-router:src/mothership_router/schema/router-manifest.1.0.schema.json`.

- [ ] **Step 4: Define Secretary observation snapshot 1.0**

The closed object has these required fields:

```json
{
  "schema_version": "1.0",
  "task_id": "<nonempty string or null>",
  "source_kind": "governance-handoff | router-manifest",
  "source_schema_version": "<nonempty string>",
  "status": "<nonempty string>",
  "summary": ["<sanitized nonempty line>", "..."],
  "authority_effect": false,
  "execution_effect": false
}
```

No summary line may contain control characters. `additionalProperties` is false. The planned owner path is `secretary-tui:schemas/observation-snapshot.1.0.schema.json`.

- [ ] **Step 5: Verify hashes and package-resource loading**

Compute each digest from bytes loaded through `importlib.resources.files("mothership.resources")`, not from a repository-relative path. Recompute `schema_sha256` and require exact equality.

Run:

```sh
python3 -m unittest tests.test_protocol_registry -v
```

- [ ] **Step 6: Commit**

```sh
git add mothership/resources tests/test_protocol_registry.py
git commit -m "feat: freeze ecosystem protocol registry"
```

---

### Task 4: Implement strict protocol file loading and closed validation

**Files:**
- Create: `mothership/protocols.py`
- Create: `tests/test_protocol_validation.py`
- Create: `tests/fixtures/protocols/duplicate-key.json`
- Create: `tests/fixtures/protocols/nonfinite.json`
- Create: `tests/fixtures/protocols/malformed-utf8.json`

- [ ] **Step 1: Write failing loader boundary tests**

Require `load_protocol_file(path)` to reject:

- non-absolute or non-normalized paths;
- symlinks, directories, FIFOs, sockets, non-regular descriptors, and component swaps;
- files larger than 1 MiB;
- malformed UTF-8 or JSON, duplicate keys, `NaN`, `Infinity`, and trailing JSON;
- secret-bearing keys at any depth (`password`, `secret`, `api_key`, `access_token`, `refresh_token`, `credential`, `private_key`);
- raw-content keys (`prompt`, `model_output`, `command`, `provider_endpoint`, `private_path`).

Reuse the repository's descriptor-relative/no-follow patterns; do not use `Path.read_text()` as the security boundary.

- [ ] **Step 2: Write failing closed-schema tests**

Public API:

```python
list_protocols() -> tuple[dict[str, object], ...]
validate_protocol(kind: str, document: object) -> dict[str, object]
validate_protocol_file(kind: str, path: Path) -> dict[str, object]
```

Success returns the same validated document. Failure raises a public `ProtocolError` whose message includes a JSON path and reason but never includes source values or private paths.

Tests must cover every schema keyword used by the four snapshots: `type`, `required`, `properties`, `additionalProperties: false`, `const`, `enum`, `minLength`, `minItems`, `items`, `minimum`, `pattern`, and `oneOf`. Reject unsupported schema keywords at registry verification time.

- [ ] **Step 3: Implement the minimal validator**

Implement only the fixed supported subset. Treat booleans as distinct from integers. Reject unknown kind and schema version before validating other fields. Sort object keys and error paths for deterministic failure precedence.

- [ ] **Step 4: Run focused and boundary regressions**

```sh
python3 -m unittest tests.test_protocol_validation tests.test_jsonio tests.test_paths -v
```

- [ ] **Step 5: Commit**

```sh
git add mothership/protocols.py tests/test_protocol_validation.py tests/fixtures/protocols
git commit -m "feat: validate suite protocols offline"
```

---

### Task 5: Add the deterministic synthetic golden path

**Files:**
- Create: `mothership/resources/golden-path/01-frontdoor-task.json`
- Create: `mothership/resources/golden-path/02-governance-handoff.json`
- Create: `mothership/resources/golden-path/03-router-manifest.json`
- Create: `mothership/resources/golden-path/04-observation-snapshot.json`
- Create: `mothership/resources/golden-path/expected-summary.json`
- Create: `mothership/demo.py`
- Create: `tests/test_demo.py`

- [ ] **Step 1: Write a failing exact-summary test**

Require:

```python
{
  "schema_version": "mothership.demo.v1",
  "status": "passed",
  "task_id": "demo-review-001",
  "capability": "code-review",
  "stages": [
    {"kind": "frontdoor-task", "schema_version": "intake.v0", "valid": True},
    {"kind": "governance-handoff", "schema_version": "1.0", "valid": True},
    {"kind": "router-manifest", "schema_version": "1.0", "valid": True},
    {"kind": "observation-snapshot", "schema_version": "1.0", "valid": True}
  ],
  "authority_effect": False,
  "execution_effect": False,
  "claim": "protocol-composition-only"
}
```

The expected summary is itself bundled and the test compares canonical bytes.

- [ ] **Step 2: Add fictional, credential-free fixtures**

Use one task ID and capability throughout. Use only repository-relative evidence labels. The Frontdoor request text must be synthetic and must not mention private product names, paths, people, provider endpoints, prompts, or credentials.

- [ ] **Step 3: Implement transition validation**

`run_demo()` loads only package resources and verifies:

- registry order and predecessor/successor edges;
- exact schema versions;
- `request_id` → `task_id` continuity;
- Frontdoor `predicted_worker_capability` → WGM/Router `capability` continuity;
- WGM → Router/observation task identity continuity;
- Router → observation status continuity;
- false authority/execution effects.

Add one isolated negative test for each drift: order, stale version, task ID, capability, status, authority, execution, secret-like key, private absolute path, and command/raw-content key.

- [ ] **Step 4: Verify deterministic bytes**

Run the demo twice in separate processes with different `HOME`, locale, cwd, and hash seed. Assert byte-identical stdout after the CLI handler is connected in Task 7.

- [ ] **Step 5: Commit**

```sh
git add mothership/resources/golden-path mothership/demo.py tests/test_demo.py
git commit -m "feat: add synthetic ecosystem demo"
```

---

### Task 6: Implement installed-resource integrity verification

**Files:**
- Create: `mothership/verify.py`
- Create: `mothership/resources/inventory.json`
- Create: `tests/test_verify.py`

- [ ] **Step 1: Write failing inventory and tamper tests**

`verify_installation()` returns:

```python
{
  "schema_version": "mothership.verify.v1",
  "status": "passed",
  "version": "0.2.0",
  "checks": {
    "inventory": "passed",
    "protocol_registry": "passed",
    "schema_digests": "passed",
    "golden_path": "passed",
    "executor_example": "passed"
  },
  "authority_effect": False,
  "execution_effect": False
}
```

For each corrupted copy of registry, schema, fixture, inventory, and `config/executors.example.json`, require status `failed`, one stable error code, no raw file content, and exit code 1 at the CLI layer.

- [ ] **Step 2: Define the inventory**

`inventory.json` lists every packaged JSON resource with relative path, byte size, and SHA-256, except itself. The verifier rejects absent, extra, duplicate, unsafe, or digest-mismatched entries.

- [ ] **Step 3: Verify the example executor registry is inert**

Require the fixed three aliases, staged/not-ready state as currently documented, and absence of command, executable, shell, environment, credential, endpoint, retry, fallback, or automatic-selection fields.

- [ ] **Step 4: Run focused tests**

```sh
python3 -m unittest tests.test_verify -v
```

- [ ] **Step 5: Commit**

```sh
git add mothership/verify.py mothership/resources/inventory.json tests/test_verify.py
git commit -m "feat: verify installed Mothership resources"
```

---

### Task 7: Complete the stable CLI with exact output and exit codes

**Files:**
- Modify: `mothership/cli.py`
- Modify: `tests/test_package_entrypoints.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write subprocess-level failing tests**

Test console/module parity for:

```text
mothership verify
mothership doctor
mothership doctor codex-cli claude-code-agent ollama-local
mothership protocol list
mothership protocol validate KIND ABSOLUTE_FILE
mothership demo
```

Require canonical JSON (`sort_keys=True`, separators `(',', ':')`, one trailing newline), stdout-only success, exit 0 success, exit 1 validation/verification/diagnostic failure, and exit 2 argparse usage errors. Unknown and duplicate aliases fail before any runner call.

- [ ] **Step 2: Connect pure handlers**

Expose testable functions receiving explicit dependencies:

```python
command_verify() -> tuple[int, dict[str, object]]
command_doctor(aliases: tuple[str, ...], runner=...) -> tuple[int, dict[str, object]]
command_protocol_list() -> tuple[int, dict[str, object]]
command_protocol_validate(kind: str, path: Path) -> tuple[int, dict[str, object]]
command_demo() -> tuple[int, dict[str, object]]
```

`doctor` with no aliases checks all three in fixed sorted order. It performs exactly two fixed probes per available adapter, never retries, and preserves existing result objects under `results`.

- [ ] **Step 3: Test failure precedence and path privacy**

Unknown kind precedes file access. Invalid alias precedes all probes. A protocol error does not print an explicit private path or document value. Broken pipe exits without a traceback.

- [ ] **Step 4: Run all CLI and legacy command tests**

```sh
python3 -m unittest tests.test_cli tests.test_doctor tests.test_seat_cli tests.test_frontdoor -v
```

- [ ] **Step 5: Commit**

```sh
git add mothership/cli.py tests/test_cli.py tests/test_package_entrypoints.py
git commit -m "feat: complete Mothership command surface"
```

---

### Task 8: Prove wheel, editable install, clone-first, and resource parity

**Files:**
- Create: `tests/test_distribution.py`
- Modify: `RELEASE_CHECKLIST.md`

- [ ] **Step 1: Add a build-artifact manifest test**

The test opens the wheel as ZIP and requires:

- `mothership`, required compatibility packages, schemas, fixtures, and inventory;
- no tests, `.git`, caches, private absolute paths, symlinks, sockets, FIFOs, credentials, or unlisted executables;
- metadata version `0.2.0`, Python `>=3.12`, MIT license, and zero runtime dependencies.

- [ ] **Step 2: Build without changing project files**

Use a fresh temporary environment. Install only build tooling into that environment if it is not already available. Run:

```sh
python3 -m build --wheel --sdist
```

Expected: one wheel and one sdist. Do not commit `dist/`.

- [ ] **Step 3: Install the wheel into a second fresh environment**

Run all five command forms from outside the repository with a minimal environment and no network. Compare `verify`, `protocol list`, and `demo` bytes to clone-first output.

- [ ] **Step 4: Test editable installation separately**

Install `-e .` in a third fresh environment and repeat entry-point/module parity. Confirm uninstall removes the console entry point and does not modify repository files.

- [ ] **Step 5: Update the release checklist with measured commands**

Add explicit unchecked items for wheel, sdist, clean install, editable install, clone-first regression, and resource inventory. Do not mark publication, tag, or remote reachability complete.

- [ ] **Step 6: Run the full wave verification**

```sh
python3 -m unittest discover -s tests -v
python3 -m mothership verify
python3 -m mothership protocol list
python3 -m mothership demo
git diff --check
git status --short
```

- [ ] **Step 7: Commit**

```sh
git add tests/test_distribution.py RELEASE_CHECKLIST.md
git commit -m "test: verify Mothership distributions"
```

---

### Task 9: Wave 1 review and evidence record

**Files:**
- Create: `docs/verification/2026-08-09-hub-wave1.md`

- [ ] **Step 1: Inspect every intended diff and worktree owner**

Run `git status`, `git diff --stat`, `git diff --check`, and review each commit. Do not stage unrelated files.

- [ ] **Step 2: Run an independent Codex review**

Review the complete Wave 1 commit range, focusing on path safety, JSON failure precedence, package-data completeness, mutation/network/model boundaries, and old-import compatibility. Fix every actionable finding through a new red/green cycle.

- [ ] **Step 3: Record current-state evidence**

Record exact commit range, Python version, test count, wheel/sdist names and SHA-256 values, command exit codes, and unresolved publication items. Evidence level is `self-verified` unless a distinct actor actually verifies it.

- [ ] **Step 4: Commit the evidence**

```sh
git add docs/verification/2026-08-09-hub-wave1.md
git commit -m "docs: record hub verification evidence"
```
