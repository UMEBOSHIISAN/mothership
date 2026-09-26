# Adapter Interoperability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the GitHub companion's closed attempt records to existing Core receipt contracts with a pure adapter and a reproducible offline example.

**Architecture:** The companion owns conversion and reuses its existing pure receipt/history validators and outcome normalizer. The Core public facade validates the resulting receipt and binds a separately supplied verification. No automatic invocation or authority behavior changes.

**Tech Stack:** Python >=3.12, standard library unittest; existing Core/companion only.

**Spec:** [Approved design](../specs/2026-09-26-adapter-contract-design.md), SHA256 `d09c7276dc5331b1059b993ddcd6e0c3940bfa7267a86a2335ebf33269d500e9`. Human approved the written specification on 2026-09-26. This plan and its execution method still require review.

## Global Constraints

- “Keep the companion's existing exact Core dependency pin.”
- “No schema changes, new action profile, registry, plugin loading, remote execution token, credentials or CLI switch are introduced.”
- “No automatic call from `execute_action_merge_pr` is added.”
- “Explicit reconciliation stays UNKNOWN even if its observation looks positive.”
- “Do not invent a finish timestamp, fabricate a receipt or re-consume authority.”
- “Existing public Core validation reads bundled schemas; those package-resource reads are permitted.”
- No private application content, production data, network effects, services, credentials or model calls in fixtures or examples.
- Bounded CC advisory review returned PASS_WITH_CONDITIONS, no blockers, on 2026-09-26. Its accepted conditions are included below. Human plan review is separate; no future paid review is authorized by this plan itself.

## Review Focus

1. Foreign expected identity types or pattern-invalid strings must reject with fixed ContractError diagnostics (Task1).
2. Nested caller mutation must not change output or hashed evidence; result must not mutate caller inputs (Task1).
3. A valid failure-labelled 302 lacks redirect rejection evidence and must remain UNKNOWN (Task1).
4. Reordered JSON keys must preserve source-pair digest; changed source facts must change it (Task1).
5. A Core-valid long action ID must not overflow the bounded observation reference (Task1); binding a valid receipt to the wrong expectation must reject (Task2).

## File map

| Path | Responsibility |
| --- | --- |
| `packages/mothership-github/mothership_github/external_action.py` (new) | One pure public converter; private validation helpers if needed |
| `packages/mothership-github/tests/test_external_action_adapter.py` (new) | Synthetic closed-record fixtures and conversion regression cases |
| `examples/github_receipt_adapter.py` (new) | Offline source-checkout demonstration, no ledger |
| `examples/github_receipt_adapter.md` (new) | Commands, exact evidence payload and integration obligations |
| `packages/mothership-github/tests/test_receipt_adapter_example.py` (new) | Exercise example through import and capture stdout |
| `packages/mothership-github/README.md` | Link to optional adapter and offline example |
| `docs/architecture.md` | Replace absence-of-adapter statement with exact implemented seam and remaining limits |
| `SHA256SUMS` | Refresh tracked-file integrity for changed/new files |

No changes to Core schemas/facade, executor/transport behavior, dependency pins, CLI, workflows or private repositories. The existing receipts/executor private helpers are reused within their own companion package; no new public API is exposed from those modules.

### Task 1: Pure receipt conversion

**Interfaces:**
- Consumes: companion `receipts._validate_event`, `receipts._validate_history`, `executor._normalized_observation`; Core public `ContractError`, `canonical_json_sha256`, `validate_external_action_receipt`.
- Produces: `mothership_github.external_action.build_external_action_receipt(started: object, finished: object, *, expected_action_id: str, expected_action_sha256: str, expected_consume_event_id: str, executor_ref: object) -> dict[str, object]`.

- [ ] **Write failing tests** in `test_external_action_adapter.py`. Use plain synthetic dictionaries (no tempfile, freeze, consume or ledger fixture). Start ID `event-` +32`1`, finish ID `event-` +32`2`, consume ID `event-` +32`3`; action `act-adapter-001`, digest64`a`, executor ref `executor:synthetic`/64`b`, start `2026-09-26T00:00:00Z`, finish `2026-09-26T00:00:01Z`. Use exact v1 closed rows from the approved spec/source validator.

  Pin these assertions using unittest subtests, deep copies and locally defined fixture helpers:

  ```python
  self.assertEqual("SUCCESS", build(success_pair)["status"])
  self.assertEqual("FAILED", build(failure_409_pair)["status"])
  for status in (0, 503, 302, 200):
      self.assertEqual("UNKNOWN", build(failure_pair(status))["status"])
  self.assertEqual("UNKNOWN", build(explicit_reconciliation_with_positive_facts)["status"])
  self.assertEqual(receipt, validate_external_action_receipt(receipt))
  self.assertEqual(canonical_json_sha256({"started": start, "finished": finish}),
                   receipt["executor_observation_ref"]["sha256"])
  ```

  `build(pair)` is a test-local wrapper supplying the independently fixed expected identity and executor ref. Do not derive expectations from malformed rows. Test names must distinguish exact projection, conservative outcome mapping, closed-shape rejection, identity binding, timestamps, evidence digest, long identity and copy isolation.

  Reject swapped row types, missing finish, unknown fields/version, orphan finish, duplicate event IDs, changed action/digest/consume, malformed expected identities (None/bool/int/list/invalid strings), impossible and reversed dates, malformed references and positive failure facts. Assert ContractError text never contains an injected input marker. Accept equal dates and `act-` +300`a`. Reverse key order and assert equal digest; change a valid timestamp and assert changed digest. Mutate start, finish and nested executor ref after conversion and assert unchanged output; assert original inputs unchanged before those mutations.

- [ ] **Run RED:** `PYTHONPATH=.:packages/mothership-github python -m unittest discover -s packages/mothership-github/tests -p test_external_action_adapter.py -v`. Expect missing converter import failure; record it without altering tests to hide failure.
- [ ] **Implement the named function.** Enforce plain JSON records and exact expected string patterns; deep-copy records/ref; validate exact start/finish types and pair history; compare to trusted expected identity/consume ID. Translate companion validation failures into fixed ContractError. Map success and explicit reconciliation directly; map failure to FAILED only when the existing normalizer returns failure, otherwise UNKNOWN. Hash exactly the validated source pair. Build the closed receipt, validate via Core public facade and return a deep copy. Do not accept a transport, paths, callbacks, clocks or credentials.
- [ ] **Run GREEN and purity guards.** Add test mocks which fail if conversion calls consume, receipt append/ledger access, transport, subprocess or clocks. Permit bundled schema reads. Run the same test command; all cases must pass. Inspect imports/calls for absence of evidence-store IO or hidden executor invocation. Same inputs must return equal records without clock dependence.
- [ ] **Pin the advisory review conditions.** State in the converter docstring that expected consume identity is caller-attested, and returned receipt is not durable-consume proof. Reject a projected receipt passed to the authority ledger's event validator; it has a different closed event contract. Use exact equality without coercion/case-folding. Keep JSON key-order invariance; reject renamed/extra source-row fields. Do not add a non-authority field to the existing closed Core schema. Reuse the same companion normalizer function used by its executor, not a second implementation.
- [ ] **Review own hunks, update SHA256SUMS and commit** only the converter, regression tests and required manifest entries. No other session's changes may be staged. A local commit does not close the task.

### Task 2: Offline integration example and consumer guidance

**Interfaces:**
- Consumes: Task1 converter; `mothership.contracts.validate_receipt_verification_binding(receipt, verification, *, expected_action_id, expected_action_sha256)` and `canonical_json_sha256`.
- Produces: `examples/github_receipt_adapter.py:main() -> int`, returning0 after deterministic assertions and fixed output. Source checkout only; not an installed console command.

- [ ] **Write failing example test** using importlib to load the new example and capture stdout. Assert `main()` returns0 and prints `SYNTHETIC ONLY`, `binding: accepted`, `mismatch: rejected`, `receipt status: UNKNOWN`. Mock consequential functions/transport to fail if reached; no subprocess is required for this test. Run `PYTHONPATH=.:packages/mothership-github python -m unittest discover -s packages/mothership-github/tests -p test_receipt_adapter_example.py -v`; expect missing example failure.
- [ ] **Implement example.** Create fixed synthetic explicit-reconciliation attempt rows, convert them, and create separately labelled synthetic UNKNOWN verification with null state digest, empty evidence refs and the exact canonical receipt ref. Assert the valid pair binds, then assert wrong expected digest and modified receipt-reference digest each reject. Confirm receipt remains UNKNOWN after binding. Print the four fixed lines and return0. Never generate real authority or contact a provider.
- [ ] **Write companion/example documentation.** Show `PYTHONPATH=.:packages/mothership-github python examples/github_receipt_adapter.py` from repository root, explain source-checkout requirements and evidence object retention, fixed identity provenance, no authenticity/durability claim, 3xx-to-UNKNOWN projection, missing-finish rejection, supported v1 only and no retry authority. Link from companion README. Update the architecture paragraph that says there is no adapter, keeping no automatic execution connection/independent verifier limitations explicit.
- [ ] **Run example tests and command.** Both must pass with exact output. Document that synthetic verification demonstrates binding only, never real independent external truth.
- [ ] **Review own hunks, refresh SHA256SUMS and commit** only Task2 files and the manifest. Do not stage the primary checkout or private application files.

## Final verification and review

- [ ] Run `PYTHONPATH=.:packages/mothership-github python -m unittest discover -s packages/mothership-github/tests -v` and `PYTHONPATH=.:packages/mothership-github python -m unittest discover -s tests -v` using supported Python. Resolve actual sandbox socket restrictions through the normal permission path if encountered; do not weaken fixtures.
- [ ] Run `python -m mothership verify`, `python -m mothership demo`, `python tools/run_evaluation.py`, integrity test and `git diff --check`; verify current CLI entry point before invocation if it differs from these commands. No live GitHub mutation or model invocation is part of acceptance.
- [ ] Obtain one fresh independent whole-diff implementation review; give exact base/revision and acceptance criteria. Fix any in-scope findings and rerun affected checks. Record evidence and scorecard; do not label self-verification cross-verified.
- [ ] Present exact changed behavior, checks and unresolved limitations. If publishing a draft PR within the authorized workflow, check the dependency on unmerged PR #29 and avoid bundling duplicate base changes; attach any created PR to this task. No merge or release.
- [ ] Checkpoint the existing task result. Record local commit and remote persistence separately. Do not claim generic cross-product integration, authenticated authority transport or production readiness.

## Plan self-review

Spec projection, outcome mapping, expected identity, closed inputs, evidence/copy semantics and all five review-focus inputs are covered in Task1. Reference binding, synthetic labeling and ownership/compatibility guidance are covered in Task2. No unsupported operation is introduced. New implementation is limited to one pure function and one offline example; verification uses existing tools. Proposed execution: parent implements the two dependent tasks in this session, followed by one independent final review. CC advisory gate is conditional on the listed implementation evidence, not product verification. Human plan review and execution-method selection remain prerequisites.
