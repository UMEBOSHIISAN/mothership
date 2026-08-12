# Mothership Flight Recorder Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic local Flight Bundle that imports Generic JSONL, verifies authority and evidence lineage, replays a run, and renders a Markdown report with safe-run and scope-drift demonstrations.

**Architecture:** Keep the v0.2 protocol registry and commands intact. Add a separate `mothership.flight_*` subsystem: closed data contracts, descriptor-safe explicit I/O, a pure run evaluator, and pure renderers; wire those functions into optional v0.3 CLI paths only after the library behavior is covered. Bundle synthetic fixtures as immutable package resources and treat every report and declared verdict as derived, independently recomputable output.

**Tech Stack:** Python 3.12+, standard library only at runtime, `unittest`, `argparse`, `dataclasses`, strict JSON/JSONL, SHA-256, packaged resources through `importlib.resources`, setuptools package data.

## Global Constraints

- Preserve the v0.2 registry, fixtures, `mothership verify`, `mothership doctor`, `mothership protocol`, `mothership demo`, public facades, and legacy imports.
- Runtime dependencies remain exactly empty; supported Python remains `>=3.12`.
- The initial measured target is Python 3.12–3.14 on Linux and macOS. Do not claim an environment that was not actually tested.
- The only run verdicts are `COMPLETE`, `INCOMPLETE`, `DRIFTED`, and `INVALID`, with precedence `INVALID > DRIFTED > INCOMPLETE > COMPLETE`.
- Missing required material is `INCOMPLETE`; malformed, substituted, digest-mismatched, or contradictory material is `INVALID`; valid evidence of scope, authority, result, or persistence mismatch is `DRIFTED`.
- `metadata-only` is the default privacy profile. `portable-evidence` includes only explicitly selected, scanned artifacts.
- Import, verify, replay, and report do not invoke a model, use a subprocess, access credentials or environment files, contact a network, discover repositories or home directories, retry, repair, or mutate outside an explicit output target.
- Raw prompts, completions, credentials, tokens, environment dumps, private absolute paths, and secret-like keys are rejected rather than copied.
- Reuse Workflow Governance Model semantics through references. Do not invent a second claim/approval/receipt protocol inside the event envelope.
- Keep the Generic JSONL adapter as the only importer in this plan. OpenAI Agents SDK, LangGraph, Claude Code, Codex, and AutoGen adapters are deferred.
- Do not modify CI/CD, release metadata, `VERSION`, deployment, remote state, tags, or GitHub settings in this plan.
- Small safety, correctness, and first-use improvements discovered during implementation may be included only when they remain inside this approved design and receive focused tests. Authority expansion, ambient capture, vendor coupling, background operation, or a changed public promise requires a new design decision.
- Use test-first cycles. Observe the intended failure, add the smallest implementation, rerun the focused test, then run the listed regression set.
- Commit only the files listed in each task after reviewing every staged hunk.

## File Structure

| Path | Responsibility |
| --- | --- |
| `mothership/flight_contracts.py` | Closed Flight Index, Flight Event, Generic Event, identifiers, timestamps, privacy, and action-class validation |
| `mothership/flight_io.py` | Descriptor-safe explicit bundle loading and Generic JSONL import; bundle digest computation |
| `mothership/flight_verify.py` | Pure graph, authority, evidence, verification, persistence, and verdict evaluation |
| `mothership/flight_render.py` | Pure deterministic replay JSON and Markdown report rendering |
| `mothership/flight_demo.py` | Read-only loading and evaluation of bundled safe and drift fixtures |
| `mothership/cli.py` | Argparse surface and stable exit-code mapping |
| `mothership/verify.py` | Installed-resource inventory verification for `.json` and `.jsonl` resources |
| `mothership/resources/flight/schemas/flight-index.v1.schema.json` | Frozen closed Flight Index schema |
| `mothership/resources/flight/schemas/flight-event.v1.schema.json` | Frozen closed Flight Event schema |
| `mothership/resources/flight/schemas/generic-event.v1.schema.json` | Frozen closed Generic Event schema |
| `mothership/resources/flight/{safe-run,scope-drift}/` | Credential-free deterministic demonstration bundles |
| `tests/test_flight_*.py` | Focused contract, I/O, verdict, rendering, demo, and boundary tests |

---

### Task 1: Remove false failures from ordinary local verification

**Files:**
- Modify: `tests/test_doctor.py:101-105,380-469`
- Modify: `tests/test_documentation.py:1-12,210-254`

**Interfaces:**
- Consumes: existing test helpers and optional test dependency contract from `pyproject.toml`.
- Produces: a test suite that remains meaningful after ordinary Python commands create ignored bytecode and that skips only the isolated source-install check when `setuptools>=77` is genuinely unavailable.

- [ ] **Step 1: Reproduce both environment-dependent failures without deleting ignored files**

Run:

```sh
python3 -m mothership verify
python3 -m unittest tests.test_doctor tests.test_documentation -v
```

Expected before the fix: at least the doctor bytecode assertion fails when `__pycache__` already exists; on a Python installation without `setuptools>=77`, the isolated pre-provisioned quickstart test also fails during the source build.

- [ ] **Step 2: Change the doctor assertion from global absence to no-new-artifacts**

Replace `_assert_package_bytecode_absent` with:

```python
def _package_bytecode_artifacts(self) -> tuple[str, ...]:
    return tuple(sorted(
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ))

def _assert_package_bytecode_unchanged(self, before: tuple[str, ...]) -> None:
    self.assertEqual(before, self._package_bytecode_artifacts())
```

For every doctor subprocess test that currently calls `_assert_package_bytecode_absent()`, capture `before = self._package_bytecode_artifacts()` immediately before the subprocess and assert `_assert_package_bytecode_unchanged(before)` afterward. Preserve the existing `PYTHONDONTWRITEBYTECODE=1` child environment assertions.

- [ ] **Step 3: Gate the offline source-install test on its declared build backend**

Add:

```python
from importlib import metadata


def _setuptools_77_available() -> bool:
    try:
        raw = metadata.version("setuptools")
        major = int(raw.split(".", 1)[0])
    except (metadata.PackageNotFoundError, TypeError, ValueError):
        return False
    return major >= 77
```

Decorate only `test_quickstart_succeeds_in_an_isolated_preprovisioned_environment` with:

```python
@unittest.skipUnless(
    _setuptools_77_available(),
    "setuptools>=77 is required for offline source-install verification",
)
```

Do not skip runtime, documentation structure, wheel-content, or CLI tests.

- [ ] **Step 4: Verify the ordinary command order no longer poisons the suite**

Run:

```sh
python3 -m mothership verify
python3 -m unittest tests.test_doctor tests.test_documentation tests.test_distribution -v
python3 -m unittest discover -s tests -v
```

Expected: PASS, with only dependency/platform skips whose messages identify the missing prerequisite.

- [ ] **Step 5: Commit**

```sh
git add tests/test_doctor.py tests/test_documentation.py
git commit -m "test: make local verification environment-stable"
```

---

### Task 2: Define closed Flight data contracts

**Files:**
- Create: `mothership/flight_contracts.py`
- Create: `mothership/resources/flight/schemas/flight-index.v1.schema.json`
- Create: `mothership/resources/flight/schemas/flight-event.v1.schema.json`
- Create: `mothership/resources/flight/schemas/generic-event.v1.schema.json`
- Create: `tests/test_flight_contracts.py`

**Interfaces:**
- Consumes: `orchestration.lib.canonical.canonical_json_bytes`, `orchestration.lib.jsonio.loads_strict`.
- Produces: `FlightError`, `REQUIRED_STAGES`, `VERDICTS`, `validate_safe_metadata(value)`, `validate_flight_index(value)`, `validate_flight_event(value)`, and `validate_generic_event(value)`; every object validator returns a deep-detached `dict[str, object]` or raises `FlightError(verdict, rule_id)`.

- [ ] **Step 1: Write failing closed-shape tests**

Start `tests/test_flight_contracts.py` with canonical valid objects and exact constants:

```python
REQUIRED_STAGES = (
    "intent", "scope", "decision", "approval",
    "execution", "result", "verification", "persistence",
)
VERDICTS = ("COMPLETE", "INCOMPLETE", "DRIFTED", "INVALID")
ACTION_CLASSES = (
    "none", "read_only", "file_write", "process_execute",
    "network_access", "credential_access", "deploy",
    "scheduler_change", "infrastructure_change",
)
```

Require rejection of missing/extra fields, duplicate identifiers, non-UTC timestamps, unknown stages/actions/outcomes/privacy profiles, non-lowercase digests, booleans used as integers, absolute or parent-traversing subject locations, secret-like keys at any depth, and raw-content keys including `prompt`, `completion`, `model_output`, `credential`, `token`, `secret`, and `environment`.

Run:

```sh
python3 -m unittest tests.test_flight_contracts -v
```

Expected: FAIL with `ModuleNotFoundError: mothership.flight_contracts`.

- [ ] **Step 2: Implement the error and primitive validators**

Use this public error contract:

```python
class FlightError(ValueError):
    def __init__(self, verdict: str, rule_id: str):
        self.verdict = verdict
        self.rule_id = rule_id
        super().__init__(rule_id)
```

Add private validators for exact key sets, nonempty bounded identifiers (`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`), lowercase 64-hex digests, normalized POSIX-relative locations, unique string arrays, and UTC timestamps in exact `YYYY-MM-DDTHH:MM:SSZ` form. All shape failures raise:

```python
FlightError("INVALID", "FLIGHT.INVALID.SCHEMA")
```

Run the focused tests; expected failures move from missing module to missing full-object validation.

- [ ] **Step 3: Implement the exact Flight Index contract**

Require exactly these fields:

```python
DIGEST = "a" * 64

{
    "schema_version": "mothership.flight-index.v1",
    "run_id": "run-safe-001",
    "created_at": "2026-08-12T00:00:00Z",
    "producer_class": "synthetic",  # human|agent|tool|importer|synthetic
    "event_ids": ["event-intent", "event-scope"],
    "required_stages": list(REQUIRED_STAGES),
    "protocol_registry_sha256": DIGEST,
    "privacy_profile": "metadata-only",  # metadata-only|portable-evidence
    "bundle_sha256": None,                 # null or 64 lowercase hex
    "declared_verdict": None,              # null or one of VERDICTS
}
```

`event_ids` must be nonempty and unique. The first-slice run profile requires `required_stages == list(REQUIRED_STAGES)` exactly; a later reduced profile requires a separate schema/version decision. Return `copy.deepcopy(value)`.

- [ ] **Step 4: Implement the exact Flight Event and Generic Event contracts**

Require the Flight Event fields:

```python
DIGEST = "a" * 64

{
    "schema_version": "mothership.flight-event.v1",
    "event_id": "event-intent",
    "run_id": "run-safe-001",
    "event_type": "request_recorded",
    "stage": "intent",
    "occurred_at": "2026-08-12T00:00:00Z",
    "producer_class": "synthetic",
    "tool_id": None,
    "predecessor_event_ids": [],
    "subject": {
        "storage": "external",  # external|bundled
        "protocol_kind": "frontdoor-task",
        "schema_version": "intake.v0",
        "location": "refs/intent.json",
        "sha256": DIGEST,
    },
    "scope_sha256": None,
    "action_class": "none",
    "authority_effect": False,
    "execution_effect": False,
    "outcome_status": "recorded",
    "redaction": {"profile": "metadata-only", "removed_fields": 0},
    "extension": None,
}
```

Allowed outcomes are `recorded`, `proposed`, `approved`, `started`, `succeeded`, `failed`, `verified`, `persisted`, and `observed`. A non-null extension is reference-only:

```python
{
    "namespace": "org.example.runtime",
    "schema_version": "1.0",
    "location": "artifacts/runtime-event.json",
    "content_sha256": DIGEST,
}
```

When `subject.storage` is `bundled`, `location` must begin with `artifacts/` and the loaded artifact must match the declared digest. When storage is `external`, the location is a normalized non-sensitive identifier only and no ambient file lookup is permitted.

The Generic Event has the same fields except `schema_version` is `mothership.generic-event.v1`; successful validation maps it to a new dict with `schema_version` set to `mothership.flight-event.v1`.

`validate_safe_metadata` recursively rejects forbidden normalized key names and string values beginning with `/`, `~/`, or a Windows drive prefix. It reports only `FLIGHT.INVALID.PRIVACY`, never the rejected key value or path text.

- [ ] **Step 5: Freeze matching closed JSON Schemas**

The three Draft 2020-12 schema files must express the same exact required fields, enums, regexes, `additionalProperties: false`, and nested closure as the Python validators. Tests load each schema through `importlib.resources` and assert its `$id`, required set, enums, and closed nested objects match the Python constants.

- [ ] **Step 6: Run focused and strict-JSON regressions**

```sh
python3 -m unittest tests.test_flight_contracts tests.test_jsonio tests.test_contracts -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```sh
git add mothership/flight_contracts.py mothership/resources/flight/schemas tests/test_flight_contracts.py
git commit -m "feat: define closed flight data contracts"
```

---

### Task 3: Load bundles safely and import Generic JSONL

**Files:**
- Create: `mothership/flight_io.py`
- Create: `tests/test_flight_io.py`

**Interfaces:**
- Consumes: Task 2 validators and `canonical_json_bytes`, `canonical_json_sha256`, `loads_strict`.
- Produces: frozen-container `FlightBundle` with deep-detached validated dictionaries, `load_flight_bundle(path: Path) -> FlightBundle`, `import_generic_jsonl(source: Path, output: Path) -> FlightBundle`, and `bundle_digest(index: dict[str, object], events_bytes: bytes, artifacts: tuple[tuple[str, int, str], ...]) -> str`.

- [ ] **Step 1: Write failing load and digest tests**

Define the public bundle type:

```python
@dataclass(frozen=True)
class FlightBundle:
    root: Path
    index: dict[str, object]
    events: tuple[dict[str, object], ...]
    events_bytes: bytes
    artifacts: tuple[tuple[str, int, str], ...]
```

Tests create an explicit temporary bundle and require: exact event order from `flight.json`; one terminal newline per JSONL row; duplicate-key and non-finite rejection; maximum 256 events; 1 MiB maximum per input file; regular files only; no symlink at any traversed component; no artifact outside `artifacts/`; sorted unique artifact paths; exact size/digest verification; and no echo of sensitive input in `FlightError`.

Run:

```sh
python3 -m unittest tests.test_flight_io -v
```

Expected: FAIL because `mothership.flight_io` does not exist.

- [ ] **Step 2: Implement descriptor-relative explicit reads**

Open a normalized absolute bundle directory one component at a time with `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`. Open `flight.json`, `events.jsonl`, and listed artifacts relative to held directory descriptors with `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`; require regular files and compare `(st_dev, st_ino, st_size)` before and after each read.

Use fixed limits:

```python
MAX_FILE_BYTES = 1_048_576
MAX_EVENTS = 256
CHUNK_BYTES = 65_536
```

Any unsafe open, decode, line count, or changed-file condition raises `FlightError("INVALID", "FLIGHT.INVALID.FILE")` without embedding the supplied path.

- [ ] **Step 3: Implement the non-self-referential bundle digest**

Construct this canonical digest payload:

```python
index_input = copy.deepcopy(index)
index_input["bundle_sha256"] = None
index_input["declared_verdict"] = None
payload = {
    "index": index_input,
    "events_sha256": sha256_bytes(events_bytes),
    "artifacts": [
        {"path": path, "size": size, "sha256": sha256}
        for path, size, sha256 in sorted(artifacts)
    ],
}
return canonical_json_sha256(payload)
```

An optional root `report.md` is ignored as derived output and excluded from the trusted input. Every other unlisted root file causes bundle load to fail as an unexpected entry. A missing or mismatched `bundle_sha256` raises `FLIGHT.INVALID.DIGEST`. A protocol registry digest other than the frozen packaged v0.2 digest raises `FLIGHT.INVALID.REGISTRY`; adding historical snapshots is deferred to a later compatibility design.

- [ ] **Step 4: Write failing Generic JSONL import tests**

Use a source containing eight valid `mothership.generic-event.v1` lines. Require the importer to:

- preserve event order and identifiers;
- map each line to `mothership.flight-event.v1`;
- derive the run identifier from the shared event value;
- reject mixed run identifiers;
- set `required_stages` to all eight canonical stages even when input is missing one, so evaluation reports `INCOMPLETE` rather than shrinking the requirement;
- set `producer_class` to `importer` in the index;
- copy no artifact under `metadata-only`;
- refuse an existing output path;
- create only `OUTPUT/flight.json`, `OUTPUT/events.jsonl`, and `OUTPUT/artifacts/`;
- leave the source untouched;
- make a load round-trip byte deterministic.

Run the focused test and observe failure at the unimplemented importer.

- [ ] **Step 5: Implement Generic JSONL import after complete in-memory validation**

Read and validate the entire bounded source before creating the output directory. Canonically encode mapped events as one object plus `b"\n"` per row. Build the index with:

```python
{
    "schema_version": "mothership.flight-index.v1",
    "run_id": shared_run_id,
    "created_at": mapped_events[0]["occurred_at"],
    "producer_class": "importer",
    "event_ids": [event["event_id"] for event in mapped_events],
    "required_stages": list(REQUIRED_STAGES),
    "protocol_registry_sha256": packaged_registry_sha256,
    "privacy_profile": privacy_profile,
    "bundle_sha256": None,
    "declared_verdict": None,
}
```

Calculate `packaged_registry_sha256` from the exact bytes returned by:

```python
registry_bytes = resources.files("mothership.resources").joinpath(
    "protocols/registry.json"
).read_bytes()
packaged_registry_sha256 = sha256_bytes(registry_bytes)
```

The unchanged v0.2 registry currently resolves to `cb5000ca90a1395c5efdf7362b5d9928fea70915a96af3c3b10542a7abbf0a14`; assert that value in the regression test so an unrelated registry edit cannot enter this slice unnoticed.

Compute and set `bundle_sha256`, then create the absent output directory with mode `0o700`, `artifacts/` with mode `0o700`, and both files with exclusive creation and mode `0o600`. On a write failure, return an error and leave the partial explicit target visible; do not search, retry, overwrite, or remove unrelated state.

The first Generic importer always emits `metadata-only` and accepts only `subject.storage: "external"`; `portable-evidence` import is deferred until an explicit artifact-selection interface is designed. Bundle loading still supports `portable-evidence` for the packaged demonstrations and validates each bundled JSON artifact with `validate_safe_metadata` before accepting its digest.

For `portable-evidence`, every artifact must be a `.json` regular file below `artifacts/`, every `subject.storage: "bundled"` location must resolve to one of those files, and every discovered artifact must be referenced by at least one event. For `metadata-only`, `artifacts/` must be empty and every subject must use `storage: "external"`.

- [ ] **Step 6: Prove boundary behavior without subprocesses or ambient discovery**

Patch `subprocess.run`, `socket.socket`, `Path.home`, and `os.environ` access in the focused tests so any use fails. Add race-hook tests that replace a traversed component or input leaf with a symlink and assert `FLIGHT.INVALID.FILE`. Assert output paths outside the explicit target remain byte-identical.

- [ ] **Step 7: Run focused regressions and commit**

```sh
python3 -m unittest tests.test_flight_io tests.test_flight_contracts tests.test_paths tests.test_jsonio -v
git add mothership/flight_io.py tests/test_flight_io.py
git commit -m "feat: import and load flight bundles safely"
```

---

### Task 4: Evaluate lineage, authority, evidence, and persistence

**Files:**
- Create: `mothership/flight_verify.py`
- Create: `tests/test_flight_verify.py`

**Interfaces:**
- Consumes: `FlightBundle`, `FlightError`, `REQUIRED_STAGES`, and validated event dictionaries.
- Produces: immutable `Finding`, immutable `FlightEvaluation`, `evaluate_flight(bundle: FlightBundle) -> FlightEvaluation`, and `evaluation_document(evaluation) -> dict[str, object]`.

- [ ] **Step 1: Write the failing complete-run test**

Define the output types exactly:

```python
@dataclass(frozen=True, order=True)
class Finding:
    rule_id: str
    event_id: str | None
    detail: str

@dataclass(frozen=True)
class FlightEvaluation:
    run_id: str
    verdict: str
    required_stages: tuple[str, ...]
    present_stages: tuple[str, ...]
    findings: tuple[Finding, ...]
```

Build an eight-stage valid bundle where each event after the first references its immediate predecessor; scope and approval share one scope digest and action class; execution matches approval; result carries the produced artifact digest; verification references that digest; persistence references the verified digest. Require `COMPLETE`, all eight stages, and no findings.

- [ ] **Step 2: Implement identity and graph validation**

Before semantic checks, require:

- index event IDs exactly equal event row IDs in transport order;
- all event and index run IDs match;
- event IDs are unique;
- every predecessor exists and appears earlier;
- the graph is acyclic;
- every non-intent event has at least one predecessor;
- event timestamps never precede any predecessor timestamp;
- every required stage appears at least once.

Malformed identity or graph facts raise/produce `INVALID` findings using `FLIGHT.INVALID.IDENTITY` or `FLIGHT.INVALID.GRAPH`. Missing required stages produce `FLIGHT.INCOMPLETE.STAGE`.

- [ ] **Step 3: Implement exact authority checks**

For the first slice, do not infer an action hierarchy. The scope, approval, and execution `scope_sha256` values and non-`none` `action_class` values must match exactly. Require approval outcome `approved` and `authority_effect is True`; require execution `execution_effect is True`.

Use these rules:

```text
FLIGHT.INCOMPLETE.APPROVAL   approval absent or not approved
FLIGHT.DRIFT.SCOPE          scope digest differs across scope/approval/execution
FLIGHT.DRIFT.ACTION_CLASS   action class differs across scope/approval/execution
FLIGHT.DRIFT.AUTHORITY      execution exists without authority_effect true approval
```

Approval must occur after scope and before execution. A syntactically valid but stale ordering produces `FLIGHT.DRIFT.AUTHORITY`.

- [ ] **Step 4: Implement result, verification, and persistence checks**

Require result outcome `succeeded`, verification outcome `verified`, and persistence outcome `persisted`. The result subject digest must equal the verification subject digest, and the verification subject digest must equal the persistence subject digest.

Use these rules:

```text
FLIGHT.INCOMPLETE.EVIDENCE       successful execution lacks result evidence
FLIGHT.INCOMPLETE.VERIFICATION   result lacks verification
FLIGHT.INCOMPLETE.PERSISTENCE    verification lacks persistence proof
FLIGHT.DRIFT.FALSE_SUCCESS       result says succeeded after execution failed
FLIGHT.DRIFT.PERSISTENCE         verification and persistence digests disagree
```

A failed execution may be validly recorded but cannot be `COMPLETE`; without a contradictory success claim it is `INCOMPLETE` with `FLIGHT.INCOMPLETE.EVIDENCE`.

- [ ] **Step 5: Apply deterministic verdict precedence and output**

Sort findings by `(rule_id, event_id or "", detail)`. Compute the highest verdict using:

```python
PRECEDENCE = {"COMPLETE": 0, "INCOMPLETE": 1, "DRIFTED": 2, "INVALID": 3}
```

First compute the evidence-derived verdict while ignoring `declared_verdict`. If a non-null declared value differs from that result, add `FLIGHT.DRIFT.DECLARED_VERDICT` and recompute with precedence. A declared value never overrides evidence.

`evaluation_document` returns exactly:

```python
{
    "schema_version": "mothership.flight-verdict.v1",
    "run_id": evaluation.run_id,
    "verdict": evaluation.verdict,
    "required_stages": list(evaluation.required_stages),
    "present_stages": list(evaluation.present_stages),
    "findings": [
        {"rule_id": item.rule_id, "event_id": item.event_id, "detail": item.detail}
        for item in evaluation.findings
    ],
    "authority_effect": False,
    "execution_effect": False,
}
```

- [ ] **Step 6: Add the adversarial mutation matrix**

Starting from the complete bundle, mutate exactly one invariant per subtest: missing approval, stale approval, substituted approval digest, action escalation, result success after failed execution, result digest substitution, missing verification, missing persistence, persistence digest mismatch, contradictory declared verdict, duplicate event ID, broken predecessor, reversed timestamp, mixed run ID, unknown event version, extra field, changed registry digest, and changed bundle digest. Assert the exact verdict and rule ID listed above.

- [ ] **Step 7: Run focused regressions and commit**

```sh
python3 -m unittest tests.test_flight_verify tests.test_flight_io tests.test_flight_contracts -v
git add mothership/flight_verify.py tests/test_flight_verify.py
git commit -m "feat: verify complete and drifted agent runs"
```

---

### Task 5: Render causal replay and Markdown reports

**Files:**
- Create: `mothership/flight_render.py`
- Create: `tests/test_flight_render.py`

**Interfaces:**
- Consumes: `FlightBundle`, `FlightEvaluation`, and `Finding`.
- Produces: `replay_document(bundle, evaluation) -> dict[str, object]` and `render_markdown_report(bundle, evaluation) -> str`.

- [ ] **Step 1: Write failing deterministic replay tests**

Require `replay_document` to return:

```python
{
    "schema_version": "mothership.flight-replay.v1",
    "run_id": bundle.index["run_id"],
    "verdict": evaluation.verdict,
    "timeline": [
        {
            "event_id": event["event_id"],
            "stage": event["stage"],
            "event_type": event["event_type"],
            "occurred_at": event["occurred_at"],
            "predecessor_event_ids": event["predecessor_event_ids"],
            "action_class": event["action_class"],
            "outcome_status": event["outcome_status"],
            "subject_sha256": event["subject"]["sha256"],
        }
        for event in bundle.events
    ],
    "authority_effect": False,
    "execution_effect": False,
}
```

Assert byte-identical canonical JSON across different locale, home, hash-seed, and current-directory values without invoking a subprocess inside the renderer.

- [ ] **Step 2: Implement the pure replay projection**

Build only from validated bundle/evaluation values. Do not read paths, environment, clocks, network state, or package resources. Return fresh dictionaries and lists so callers cannot mutate the bundle.

- [ ] **Step 3: Write failing Markdown report tests**

Require this fixed section order:

```text
# Mothership Flight Report
## Verdict
## Authority
## Timeline
## Findings
## Evidence boundary
```

The report states the verdict, `run_id`, required/present stage counts, approval action/scope digest prefix, one table row per event, sorted findings, and the exact sentence:

```text
This report verifies supplied records; it does not grant authority or prove unobserved real-world actions.
```

Require a trailing newline, no timestamps other than those in the bundle, no raw extension data, no locations, no private paths, and no digest longer than a 12-character display prefix.

- [ ] **Step 4: Implement the pure Markdown renderer**

Escape `|`, backslash, CR, LF, and control characters before table insertion. Use `None` when no approval exists. A no-findings run prints `- None.`; otherwise print `- RULE_ID (event-id): detail` in the evaluation's stable order.

- [ ] **Step 5: Run focused regressions and commit**

```sh
python3 -m unittest tests.test_flight_render tests.test_flight_verify -v
git add mothership/flight_render.py tests/test_flight_render.py
git commit -m "feat: replay flights and render safe reports"
```

---

### Task 6: Package safe-run and scope-drift demonstrations

**Files:**
- Create: `mothership/flight_demo.py`
- Create: `mothership/resources/flight/safe-run/flight.json`
- Create: `mothership/resources/flight/safe-run/events.jsonl`
- Create: `mothership/resources/flight/safe-run/artifacts/intent.json`
- Create: `mothership/resources/flight/safe-run/artifacts/scope.json`
- Create: `mothership/resources/flight/safe-run/artifacts/decision.json`
- Create: `mothership/resources/flight/safe-run/artifacts/approval.json`
- Create: `mothership/resources/flight/safe-run/artifacts/execution.json`
- Create: `mothership/resources/flight/safe-run/artifacts/result.json`
- Create: `mothership/resources/flight/safe-run/artifacts/verification.json`
- Create: `mothership/resources/flight/safe-run/artifacts/persistence.json`
- Create: `mothership/resources/flight/scope-drift/flight.json`
- Create: `mothership/resources/flight/scope-drift/events.jsonl`
- Create: `mothership/resources/flight/scope-drift/artifacts/intent.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/scope.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/decision.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/approval.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/execution.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/result.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/verification.json`
- Create: `mothership/resources/flight/scope-drift/artifacts/persistence.json`
- Create: `tests/test_flight_demo.py`
- Modify: `mothership/verify.py:22-63,75-107,154-187`
- Modify: `mothership/resources/inventory.json`
- Modify: `pyproject.toml:25-29`

**Interfaces:**
- Consumes: Tasks 3–5 bundle, verifier, and renderer APIs.
- Produces: `run_flight_demo(name: str) -> dict[str, object]`, packaged fixture integrity, and installation verification that accounts for every `.json` and `.jsonl` resource.

- [ ] **Step 1: Write failing demonstration tests**

Require:

```python
self.assertEqual("COMPLETE", run_flight_demo("safe")["verdict"])
self.assertEqual(8, run_flight_demo("safe")["verified_stages"])
self.assertEqual("DRIFTED", run_flight_demo("drift")["verdict"])
self.assertEqual(
    ["FLIGHT.DRIFT.ACTION_CLASS"],
    run_flight_demo("drift")["rule_ids"],
)
```

Both outputs must use schema `mothership.flight-demo.v1`, set authority/execution effects false, and remain byte-identical across process environments. Unknown names raise `FlightError("INVALID", "FLIGHT.INVALID.DEMO")`.

- [ ] **Step 2: Add the eight-stage synthetic bundles**

Use fictional IDs, UTC timestamps one second apart, and content-addressed synthetic JSON artifacts. The safe run uses one shared non-null scope digest and `action_class: "file_write"` for scope, approval, and execution. The drift run is byte-identical in meaning except scope/approval use `read_only` and execution uses `file_write`.

Set approval `authority_effect: true`, execution `execution_effect: true`, and all other event effects false. No fixture contains raw prompts, credentials, private paths, commands, vendor names, or claims of real execution. Compute every artifact and bundle digest from exact bytes.

- [ ] **Step 3: Implement read-only resource loading**

`run_flight_demo` locates only `flight/safe-run` or `flight/scope-drift` through `importlib.resources`, enters that directory with `resources.as_file(...)`, and calls `load_flight_bundle` while the context is active. It uses the same validators and evaluator as a user bundle; no separate trusted shortcut is allowed. Return exactly:

```python
{
    "schema_version": "mothership.flight-demo.v1",
    "scenario": "safe" or "drift",
    "run_id": evaluation.run_id,
    "verdict": evaluation.verdict,
    "verified_stages": len(evaluation.present_stages),
    "required_stages": len(evaluation.required_stages),
    "rule_ids": sorted({finding.rule_id for finding in evaluation.findings}),
    "authority_effect": False,
    "execution_effect": False,
    "claim": "supplied-records-only",
}
```

- [ ] **Step 4: Extend package-data and installed-resource inventory**

Change package data to:

```toml
mothership = ["resources/*.json", "resources/**/*.json", "resources/**/*.jsonl"]
```

Rename `_json_paths` to `_inventory_paths` and include regular files ending in `.json` or `.jsonl`, excluding only `inventory.json`. Inventory entries remain sorted and contain exact relative path, byte size, and SHA-256. Add tests proving an extra/missing JSONL resource fails `inventory_shape_mismatch` and a changed JSONL resource fails `inventory_digest_mismatch`.

- [ ] **Step 5: Regenerate and independently check inventory values**

Use a short standard-library command or a reviewable development helper to calculate sorted sizes and SHA-256 values. Then independently verify through `verify_installation()`; do not weaken the verifier to accept stale values.

- [ ] **Step 6: Run focused and package regressions**

```sh
python3 -m unittest tests.test_flight_demo tests.test_verify tests.test_distribution -v
python3 -m mothership verify
```

Expected: tests pass and existing `mothership verify` still emits its v1 shape with all checks passed.

- [ ] **Step 7: Commit**

```sh
git add mothership/flight_demo.py mothership/verify.py mothership/resources/flight mothership/resources/inventory.json pyproject.toml tests/test_flight_demo.py tests/test_verify.py tests/test_distribution.py
git commit -m "feat: bundle safe and drift flight demos"
```

---

### Task 7: Wire the v0.3 CLI without breaking v0.2 commands

**Files:**
- Modify: `mothership/cli.py:1-204`
- Modify: `tests/test_cli.py:1-200`
- Modify: `tests/test_package_entrypoints.py`
- Modify: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `import_generic_jsonl`, `load_flight_bundle`, `evaluate_flight`, `evaluation_document`, `replay_document`, `render_markdown_report`, and `run_flight_demo`.
- Produces: `mothership import generic`, `mothership verify run`, `mothership replay`, `mothership report`, `mothership demo safe`, and `mothership demo drift` with stable process exits.

- [ ] **Step 1: Write failing parser and handler tests**

Require these forms:

```text
mothership verify
mothership verify run BUNDLE
mothership import generic SOURCE --out OUTPUT
mothership replay BUNDLE
mothership report BUNDLE --format markdown
mothership demo
mothership demo safe
mothership demo drift
```

Plain `verify` and plain `demo` must remain byte-identical to v0.2 tracked outputs. All path arguments are lexically normalized to explicit absolute `Path` values before entering Flight I/O; no `Path.home()` or repository discovery is allowed.

- [ ] **Step 2: Add command handlers with exact exit mapping**

Use:

```python
FLIGHT_EXIT_CODES = {
    "COMPLETE": 0,
    "INCOMPLETE": 20,
    "DRIFTED": 21,
    "INVALID": 22,
}
```

`command_verify_run` loads, evaluates, and returns `evaluation_document`. `command_replay` returns replay JSON with the evaluation's exit. `command_report` returns Markdown with the evaluation's exit. `command_flight_import` returns schema `mothership.flight-import.v1`, the safe relative display name of the output leaf, run ID, bundle digest, event count, and false effect flags; it never prints an absolute path.

All caught `FlightError` results contain only schema version, verdict, rule ID, and false effect flags. Unexpected internal exceptions are not broadly swallowed in library functions; the CLI maps only explicitly documented I/O/encoding failures to exit 70 and `FLIGHT.INTERNAL` without secret values.

- [ ] **Step 3: Preserve JSON and text emission boundaries**

Keep canonical one-object JSON for all commands except successful `report --format markdown`, which uses a dedicated `_emit_text` helper. Both emitters return false on broken pipe, `OSError`, or encoding failure; `main` then returns 1 without traceback.

- [ ] **Step 4: Return exit 64 for parser usage errors**

Subclass `argparse.ArgumentParser`:

```python
class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: error: {message}\n")
```

Update the existing usage test from 2 to 64. Help remains exit 0. This is the only intentional invalid-invocation exit change; all valid v0.2 command outputs and exits remain unchanged.

- [ ] **Step 5: Add boundary and parity tests**

For each new read-only command, patch subprocess and network creation to fail if called. Test console-script and `python -m mothership` byte parity from an installed wheel. Test all four verdict exits using prepared bundles. Assert stderr is empty for evaluated run verdicts and contains usage only for parser failures.

- [ ] **Step 6: Run focused and distribution regressions**

```sh
python3 -m unittest tests.test_cli tests.test_package_entrypoints tests.test_distribution tests.test_flight_demo -v
python3 -m mothership demo
python3 -m mothership demo safe
python3 -m mothership demo drift
```

Expected: plain demo remains exit 0; safe is exit 0; drift emits its closed JSON and exits 21.

- [ ] **Step 7: Commit**

```sh
git add mothership/cli.py tests/test_cli.py tests/test_package_entrypoints.py tests/test_distribution.py
git commit -m "feat: expose flight recorder commands"
```

---

### Task 8: Rebuild the public story around proof, not fear

**Files:**
- Modify: `README.md`
- Modify: `docs/ja/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/protocols.md`
- Modify: `docs/security.md`
- Modify: `docs/compatibility.md`
- Modify: `docs/ecosystem-roadmap.md`
- Modify: `docs/installation.md`
- Create: `docs/generated/flight-safe-output.json`
- Create: `docs/generated/flight-drift-output.json`
- Create: `docs/generated/flight-safe-report.md`
- Modify: `tests/test_documentation.py`
- Modify: `tests/test_documentation_commands.py`
- Modify: `tests/test_markdown_links.py`

**Interfaces:**
- Consumes: the real Task 7 CLI and deterministic bundled fixtures.
- Produces: executable English/Japanese onboarding, generated outputs copied from real commands, and accurate security/compatibility documentation.

- [ ] **Step 1: Write failing documentation contracts**

Change the root README H2 order to require:

```python
EXPECTED_H2 = (
    "See agent scope drift in 60 seconds",
    "What Mothership proves",
    "The flight lifecycle",
    "Quick start",
    "Import and verify a run",
    "Authority as Data",
    "Safety guarantees",
    "What Mothership is not",
    "Architecture",
    "Public API",
    "Ecosystem protocols",
    "Compatibility",
    "Documentation",
    "Contributing",
    "Security",
    "Roadmap",
    "License",
)
```

Require the exact hero copy:

```text
The black box for AI agents.
Know what your agents were allowed to do—and prove what actually happened.
```

Require both generated demo outputs, the lifecycle order, the four verdicts, a link to the Flight Recorder design, and the exact disclaimer from the Markdown report. Continue rejecting guaranteed-security, production-ready, autonomous-execution, certification, private-path, secret, and unmeasured-adoption claims.

- [ ] **Step 2: Generate evidence from the real CLI**

Run with `PYTHONDONTWRITEBYTECODE=1`:

```sh
python3 -m mothership demo safe
python3 -m mothership demo drift
python3 -m mothership report mothership/resources/flight/safe-run --format markdown
```

Capture exact stdout bytes in the three generated files. The drift command's expected exit is 21; capture stdout without treating that documented verdict as command corruption. Generated files end in exactly one newline.

- [ ] **Step 3: Rewrite the README first screen and 60-second proof**

Keep the existing whale logo/banner. Place the new headline before the banner and show safe/drift output immediately after it. Explain that Mothership verifies supplied evidence and detects scope mismatch; do not frame the project as stopping “rogue AI” or as universal enforcement.

Show these clone-first commands in the one marked quickstart block:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
mothership verify
mothership demo safe
```

Keep the v0.2 protocol demo documented lower as a compatibility projection. Move the constellation below the lifecycle and component-owner map.

- [ ] **Step 4: Give Japanese onboarding semantic parity**

Use the corresponding primary copy:

```text
AIエージェントのブラックボックス。
何が許可され、実際に何が起きたかを、証拠から検証する。
```

Match the English command sequence, verdict meanings, lifecycle, limitations, and generated evidence. Do not shorten the Japanese guide into disclaimers or describe an unimplemented adapter.

- [ ] **Step 5: Update technical documents**

- `architecture.md`: distinguish v0.2 projection from the v0.3 graph and show observation as a projection.
- `protocols.md`: document the index/event schemas, owner-extension boundary, versions, digests, and verdict precedence.
- `security.md`: document explicit path I/O, privacy profiles, secret rejection, no ambient capture, and residual risk of false or omitted source records.
- `compatibility.md`: list only measured Python/OS/package forms and label unmeasured entries.
- `ecosystem-roadmap.md`: mark Generic JSONL as shipped only after tests pass; retain vendor adapters as candidates.
- `installation.md`: document import/verify/replay/report and distinguish source-install build requirements from zero runtime dependencies.

- [ ] **Step 6: Execute every documented local command**

```sh
python3 -m unittest tests.test_documentation tests.test_documentation_commands tests.test_markdown_links -v
```

Expected: generated blocks match real output exactly, shell blocks are the tested sequences, all links resolve, and every claim guard passes.

- [ ] **Step 7: Commit**

```sh
git add README.md docs/ja/README.md docs/architecture.md docs/protocols.md docs/security.md docs/compatibility.md docs/ecosystem-roadmap.md docs/installation.md docs/generated tests/test_documentation.py tests/test_documentation_commands.py tests/test_markdown_links.py
git commit -m "docs: present Mothership as an agent black box"
```

---

### Task 9: Run the complete verification and review gate

**Files:**
- No planned file changes. A confirmed in-scope defect returns to the owning task and receives a focused regression test plus a separate commit.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: fresh test, package, security-boundary, and review evidence. It does not release or push.

- [ ] **Step 1: Run every focused Flight test without the bytecode environment crutch**

```sh
python3 -m unittest tests.test_flight_contracts tests.test_flight_io tests.test_flight_verify tests.test_flight_render tests.test_flight_demo tests.test_cli -v
```

Expected: PASS with zero failures and zero errors.

- [ ] **Step 2: Run the complete suite in the documented portable mode**

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected: PASS; skips must be limited to explicitly unavailable optional build tools or unmeasured platform probes.

- [ ] **Step 3: Verify the installed resources and all public demonstrations**

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m mothership verify
PYTHONDONTWRITEBYTECODE=1 python3 -m mothership demo
PYTHONDONTWRITEBYTECODE=1 python3 -m mothership demo safe
```

Expected: exit 0 and exact tracked outputs. Run the drift demo separately and require exit 21 with exact tracked drift JSON.

- [ ] **Step 4: Build and inspect distributions when the declared build extra is present**

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m build --no-isolation
```

Expected: one wheel and one source distribution. Inspect the wheel through `tests.test_distribution`; require all inventoried JSON/JSONL files, no tests, no bytecode, no private absolute paths, and no runtime dependency.

If `build` or `setuptools>=77` is absent, record the exact skip as unverified locally; do not claim artifact verification from source tests alone and do not download dependencies without separate authority.

- [ ] **Step 5: Run security and placeholder scans**

```sh
git grep -n -I -E '(api[_-]?key|access[_-]?token|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|/Users/|/private/)' -- . ':!docs/superpowers/*'
git grep -n -E 'TODO|TBD|FIXME|PLACEHOLDER' -- mothership tests README.md docs ':!docs/superpowers/*'
git diff --check bd04f20..HEAD
```

Expected: no real credential/private-path material, no implementation placeholders, and no whitespace errors. Test fixtures may contain forbidden key names only when the value is an obvious inert sentinel and the test asserts rejection without echo.

- [ ] **Step 6: Run Codex review against the approved design base**

Run a Codex review over `bd04f20..HEAD` and explicitly ask it to check: spec coverage, authority widening, unsafe path traversal, digest self-reference, verdict precedence, false success, secret leakage, v0.2 compatibility, and test tampering. Address every confirmed in-scope finding with a focused test and separate commit; record rejected findings with file/line evidence in the closeout.

- [ ] **Step 7: Verify final repository state**

```sh
git status --short --branch
git log --oneline bd04f20..HEAD
```

Expected: clean worktree, only reviewed implementation commits ahead of the design base, and no push, tag, release, CI mutation, or remote-side claim.
