# GitHub Ingestion Minimum Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch one explicit public GitHub PR or Issue with exactly one GET, preserve it as a source observation, map only deterministic facts into the existing Frontdoor/WGM inputs, and produce the existing ephemeral Decision Card without recommendation, persistence, retry, or GitHub mutation.

**Architecture:** Add a standard-library-only source adapter in `orchestration/lib/github_observation.py`. The adapter parses a canonical public GitHub web reference, performs one GET against the corresponding `api.github.com` endpoint, and returns an internal observation object. A separate mapping function copies existing Frontdoor/WGM documents, appends only a stable evidence reference, puts selected source facts in existing Card reasons, and marks only secondary data that was not fetched as existing Frontdoor unknowns. The CLI composes those mapped inputs with the existing `build_decision_card()` producer.

**Tech Stack:** Python 3.12+, `urllib.request`, existing strict JSON decoder and protocol validator, existing Decision Card producer, `unittest`/pytest.

**Spec:** User-approved `GITHUB_INGESTION_MIN_SLICE` / `GO_WITH_3_CORRECTIONS` implementation brief in the current task.

## Global Constraints

- Accept one explicit public GitHub PR or Issue reference only.
- Perform exactly one read-only GET; do not follow an external redirect, retry, search, list, paginate, or call secondary endpoints.
- Do not read credentials and do not support private repositories in v0.
- Keep source observation separate from governance semantics.
- Do not infer `human_gate`, `risk`, `authority`, `consequence_if_approved`, or `recommendation` from GitHub data.
- Reuse the existing Frontdoor, WGM, and Decision Card contracts exactly; add no schema fields.
- Put stable source identifiers in existing evidence-reference fields, not GitHub facts.
- Distinguish internal `not_fetched` from internal `not_evaluated`; only `not_fetched` becomes Card unknown text.
- Fail closed on invalid refs, non-2xx responses, malformed JSON, malformed required fields, and timeout; emit no fabricated Card and perform no retry.
- Keep all mapping in memory; do not write queues, snapshots, caches, comments, reviews, labels, merges, or other GitHub state.

---

### Task 1: Source observation boundary

**Files:**
- Create: `orchestration/lib/github_observation.py`
- Test: `tests/test_github_observation.py`

**Interfaces:**
- Consumes: canonical refs shaped as `https://github.com/{owner}/{repo}/pull/{number}` or `https://github.com/{owner}/{repo}/issues/{number}` and an injected opener only for tests.
- Produces: `GitHubRef`, immutable `GitHubObservation`, `parse_github_ref()`, and `fetch_github_observation()`.

- [x] **Step 1: Write the failing source-boundary tests**

  Add tests that use a complete fake API response and assert:

  ```python
  observation = fetch_github_observation(
      "https://github.com/UMEBOSHIISAN/mothership/pull/3",
      opener=one_response_opener,
  )
  assert observation.kind == "pull_request"
  assert observation.title == "docs: make Mothership the AI agent flight recorder"
  assert observation.head_sha == "a" * 40
  assert "comments" in observation.not_fetched
  assert "body" in observation.not_evaluated
  ```

  Add one test for an Issue ref, one test that records exactly one GET request with no Authorization header, and negative tests for a non-GitHub host, query string, malformed JSON, HTTP 404, timeout, and a second attempted call. The expected failure before implementation is `ModuleNotFoundError: No module named 'orchestration.lib.github_observation'`.

- [x] **Step 2: Run the focused tests and verify the expected RED state**

  Run:

  ```bash
  env PYTHONDONTWRITEBYTECODE=1 python3.14 -m pytest tests/test_github_observation.py -q
  ```

  Expected: collection fails because the new module and public functions do not yet exist.

- [x] **Step 3: Implement the minimal source observation**

  Implement strict URL parsing, exact endpoint construction, a no-redirect opener, a five-second timeout, a one-megabyte response cap, strict JSON decoding, required field validation, and a single GET. Store only selected facts in `GitHubObservation`; retain `not_fetched=("comments", "reviews", "files", "checks")` and an explicit `not_evaluated` tuple for primary-response fields intentionally ignored. Never inspect response body text, comments, labels, reviews, or permissions.

- [x] **Step 4: Run the focused tests and verify GREEN**

  Run the same focused command and require all source-boundary tests to pass with no warnings.

---

### Task 2: Deterministic mapping into existing contracts

**Files:**
- Modify: `orchestration/lib/github_observation.py`
- Test: `tests/test_github_observation.py`

**Interfaces:**
- Consumes: `GitHubObservation`, validated Frontdoor `intake.v0`, and validated WGM `1.1` documents.
- Produces: `map_observation_to_contracts(observation, frontdoor_task, governance_handoff)` returning detached existing-contract-shaped dictionaries, plus `build_github_decision_card()` delegating to `build_decision_card()`.

- [x] **Step 1: Write the failing mapping tests**

  Use hand-written valid Frontdoor/WGM fixtures and assert that mapping:

  ```python
  mapped_frontdoor, mapped_handoff = map_observation_to_contracts(
      observation, frontdoor, handoff
  )
  assert "github-pr-UMEBOSHIISAN-mothership-3" in mapped_handoff["evidence_references"]
  assert "github.not_fetched=comments" in mapped_frontdoor["unknowns"]
  assert "github.not_fetched=checks" in mapped_frontdoor["unknowns"]
  assert "github.not_evaluated=body" not in mapped_frontdoor["unknowns"]
  assert frontdoor["unknowns"] == []
  assert handoff["evidence_references"] == ["evidence:base"]
  ```

  Assert that selected facts appear only in the explicit reasons returned by `observation.card_reasons()`, that no GitHub fact is inserted into `evidence_references`, that an explicit recommendation is preserved by `build_github_decision_card()` and a missing recommendation remains `None`, and that `authority_effect` and `execution_effect` remain false. The expected RED state is missing mapping symbols.

- [x] **Step 2: Run the mapping tests and verify RED**

  Run:

  ```bash
  env PYTHONDONTWRITEBYTECODE=1 python3.14 -m pytest tests/test_github_observation.py -q
  ```

  Confirm the failures are missing implementation symbols, not malformed fixtures.

- [x] **Step 3: Implement the minimal mapping**

  Validate and deep-copy the two existing protocols. Append only the stable, schema-safe GitHub observation reference to WGM evidence references. Append deterministic selected facts to the reasons input. Append `github.not_fetched=<field>` only for the four secondary endpoints that were not called. Do not append `not_evaluated` fields to unknowns. Pass all caller-supplied governance and human-facing fields unchanged into `build_decision_card()`; default recommendation to `None`.

- [x] **Step 4: Run the mapping tests and verify GREEN**

  Run the focused test file and require all source and mapping tests to pass.

---

### Task 3: Explicit one-ref CLI vertical slice

**Files:**
- Modify: `mothership/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `--ref`, existing absolute `--frontdoor` and `--wgm` protocol files, optional `--router`, explicit question/consequence/reasons/recommendation.
- Produces: one canonical `decision-card.v0` JSON object on stdout or exit 1 with generic stderr and no Card on any ingestion failure.

- [x] **Step 1: Write the failing CLI tests**

  Add parser/command tests for `github-decision-card` using a deterministic opener fixture. Assert that the command emits a valid Decision Card with the live-shaped source facts, stable evidence reference, `github.not_fetched=*` unknowns, `recommendation: null` by default, and both effect flags false. Add a failure test where the opener returns 404 and assert empty stdout, nonzero exit, and no retry. The expected RED state is the missing CLI command/function.

- [x] **Step 2: Run the focused CLI tests and verify RED**

  Run:

  ```bash
  env PYTHONDONTWRITEBYTECODE=1 python3.14 -m pytest tests/test_cli.py -q
  ```

  Confirm the new tests fail because the parser/command is absent while the existing CLI tests remain green.

- [x] **Step 3: Implement the CLI wiring**

  Add `github-decision-card` with required `--ref`, `--frontdoor`, `--wgm`, `--question`, and `--consequence-if-approved`, plus the existing optional recommendation/reason/router inputs. Load only existing protocol files, invoke `build_github_decision_card()`, emit canonical JSON, and catch ingestion/production errors behind the existing generic fail-closed stderr behavior. Do not expose response bodies, exception details, paths, or credentials.

- [x] **Step 4: Run focused CLI tests and the decision-discovery regression set**

  Run:

  ```bash
  env PYTHONDONTWRITEBYTECODE=1 python3.14 -m pytest tests/test_github_observation.py tests/test_cli.py tests/test_decision_discovery.py -q
  ```

  Require the new tests and the existing 28-test focused baseline to pass.

---

### Task 4: Verification and live public read-only E2E

**Files:**
- Modify: none beyond Tasks 1–3.
- Test: live command output only; no repository fixture or persistent snapshot.

- [x] **Step 1: Re-read the plan and inspect the diff**

  Verify that the diff contains only the adapter, CLI wiring, tests, and this plan; no schema, queue, persistence, scheduler, retry, auth, or mutation code is present.

- [x] **Step 2: Run the full test suite with the project Python**

  Run:

  ```bash
  env PYTHONDONTWRITEBYTECODE=1 python3.14 -m pytest
  ```

  Record the pre-existing environment failures separately if they remain; do not modify unrelated doctor or packaging tests.

- [x] **Step 3: Run the real public PR #3 command**

  Use validated Frontdoor/WGM fixture inputs and the explicit public ref:

  ```text
  https://github.com/UMEBOSHIISAN/mothership/pull/3
  ```

  Verify the command performs one GET, produces a valid Decision Card, leaves recommendation null unless explicitly supplied, and contains no approval or execution effect. Write the emitted JSON to an ephemeral temporary regular file and pass that file to the existing Secretary read-only renderer; do not save a repository snapshot or mutate GitHub.

- [x] **Step 4: Report exact diff scope and verification status**

  Return `GITHUB_INGESTION_IMPLEMENTED_GREEN` only if focused tests, contract validation, full verification accounting, and the live PR #3 render all pass. Otherwise return `HOLD` with the exact failing boundary and leave the branch uncommitted and unpublished.
