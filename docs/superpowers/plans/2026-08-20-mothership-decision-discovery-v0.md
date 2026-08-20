# Mothership Decision Discovery v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one ephemeral, human-gated Decision Card v0 from validated Frontdoor intake and WGM handoff, with an optional Router recommendation.

**Architecture:** Add one pure producer beside the existing Decision Card/Approval binding. The producer validates already-owned protocol objects through Mothership's existing protocol validator, preserves source semantics in the existing Card fields, and requires caller-supplied human-facing proposal text. It returns no Card for `human_gate=NONE`, creates no approval, performs no execution, and stores nothing.

**Tech Stack:** Python 3.12+, existing Mothership protocol validator, existing closed Decision Card contract, `unittest`.

**Spec:** Human decision `DECISION-DISCOVERY-V0-001` in the current task.

## Global Constraints

- Required inputs: validated Frontdoor intake and validated WGM handoff.
- Optional input: Router manifest/recommendation; Router is advisory only.
- `question` and `consequence_if_approved` are explicit proposal inputs; Mothership does not invoke a model.
- Unknowns are copied exactly; no inferred unknowns or facts.
- `authority_effect` and `execution_effect` remain false.
- v0 is ephemeral; no queue storage, sorting, deduplication, dismissal, freshness, or lifecycle.
- No new public protocol, schema version, execution path, retry, fallback, or companion mutation.

---

### Task 1: Lock the producer behavior with red tests

**Files:**
- Create: `tests/test_decision_discovery.py`

**Interfaces:**
- Test the planned public function `build_decision_card(frontdoor_task, governance_handoff, *, decision_id, question, consequence_if_approved, router_manifest=None)` from `orchestration.lib.decision`.
- The function returns a validated Card mapping or `None` when no human decision is required.
- Invalid protocol inputs, identity drift, high-risk/no-gate drift, and invalid proposal inputs raise `DecisionCardProductionError`.

- [x] **Step 1: Add the Frontdoor and WGM fixtures.**

Use the existing golden-path values, changing only `human_gate` to `CONFIRM` for the card-producing case. Keep the Frontdoor `request_id` and WGM `task_id` equal.

- [x] **Step 2: Add a failing Frontdoor + WGM producer test.**

Assert that the producer returns a valid `decision-card.v0` with `task_id` from WGM, exact WGM `evidence_references`, exact WGM `risk`, exact Frontdoor `unknowns`, explicit proposal text, and both effect flags false.

- [x] **Step 3: Add a failing Router-optional test.**

Call the producer without a Router manifest and assert `recommendation is None`; call it with the existing Router fixture and assert the exact `recommended_alias` is copied and Router reasons/status are provenance-prefixed.

- [x] **Step 4: Add failing boundary tests.**

Cover `human_gate=NONE` returning `None`, high-risk plus `NONE` failing closed, mismatched `request_id`/`task_id` failing, invalid optional Router input failing, and invalid explicit proposal text failing.

- [x] **Step 5: Add failing no-inference tests.**

Assert Frontdoor `unknowns` are copied exactly, empty unknowns stay empty, and no Card fields contain an inferred approval, execution, worker, model, command, or authority value.

- [x] **Step 6: Run the focused tests before implementation.**

Run:

```bash
/opt/homebrew/bin/python3.12 -m unittest tests.test_decision_discovery -v
```

Expected result: collection/import failure because the producer function does not yet exist. This is the required RED evidence.

### Task 2: Implement the pure Decision Card producer

**Files:**
- Modify: `orchestration/lib/decision.py`
- Modify: `mothership/contracts.py`

**Interfaces:**
- `DecisionCardProductionError(ContractError)` is the producer-specific failure type.
- `build_decision_card(frontdoor_task, governance_handoff, *, decision_id, question, consequence_if_approved, router_manifest=None) -> dict[str, object] | None`.

- [x] **Step 1: Validate the two required inputs with existing ownership validators.**

Call `validate_protocol("frontdoor-task", frontdoor_task)` and `validate_protocol("governance-handoff", governance_handoff)`. If either raises `ProtocolError`, wrap it as `DecisionCardProductionError` without rewriting the owner contract.

- [x] **Step 2: Enforce the existing identity and human-gate boundary.**

Require Frontdoor `request_id == handoff.task_id`. Return `None` for `human_gate=NONE` when WGM risk is not `high`; reject high-risk/no-gate drift. Continue only for `CONFIRM` or `BLOCKING`.

- [x] **Step 3: Validate the optional Router input only when supplied.**

Call `validate_protocol("router-manifest", router_manifest)`, require its task ID to equal the handoff task ID, and copy only `recommended_alias` and provenance-prefixed `status`/`reasons`. Never use Router as a required source or authority.

- [x] **Step 4: Construct and validate the existing Card shape.**

Use WGM `task_id`, WGM `evidence_references`, WGM `risk`, exact Frontdoor `unknowns`, explicit `decision_id`, `question`, and `consequence_if_approved`. Set `recommendation` to the optional Router alias or `None`; set `authority_required` to the existing Card constant `human`; set both effects to `False`; validate with `validate_contract("decision-card", card)`.

- [x] **Step 5: Export the producer through the existing Mothership contracts facade.**

Re-export only `DecisionCardProductionError` and `build_decision_card`. Do not add a CLI command, protocol registry entry, schema, storage, or approval side effect.

- [x] **Step 6: Run the focused tests and confirm GREEN.**

Run:

```bash
/opt/homebrew/bin/python3.12 -m unittest tests.test_decision_discovery -v
```

Expected result: all focused tests pass.

### Task 3: Verify the vertical slice and scope

**Files:**
- No additional production files.
- Modify: `tests/test_public_facades.py` (public facade compatibility assertion only)

- [x] **Step 1: Run the existing Decision Card/Approval tests.**

```bash
/opt/homebrew/bin/python3.12 -m unittest tests.test_contracts.TestDecisionPlaneContracts tests.test_contracts.TestDecisionApprovalBinding -v
```

- [ ] **Step 2: Run the full Mothership suite under the declared Python floor.**

Result: 247 tests ran; the new Decision Discovery tests and all related
regressions pass. Six unrelated pre-existing/environment failures remain
(doctor worktree bytecode, isolated-install setuptools backend, and staged
package log scanning).

```bash
/opt/homebrew/bin/python3.12 -m unittest discover -s tests -v
```

- [x] **Step 3: Exercise the approval boundary without auto-approval.**

Build one Card from Frontdoor + WGM alone, create the existing human Approval fixture explicitly in the test, and pass both to `validate_decision_approval_binding()`. Assert the binding succeeds only after the explicit Approval object exists and that no producer call creates one.

- [x] **Step 4: Review the diff and scope.**

```bash
git -C /Users/umeboshi/Workspace/oss_staging/mothership diff --check
git -C /Users/umeboshi/Workspace/oss_staging/mothership status --short
git -C /Users/umeboshi/Workspace/oss_staging/mothership diff -- orchestration/lib/decision.py mothership/contracts.py tests/test_decision_discovery.py
```

Confirm that only the producer, facade export, focused tests, the required public-facade compatibility assertion, and this plan artifact changed. Do not commit or push.

## Explicitly out of scope

- Mothership Router changes
- Agent Frontdoor changes
- WGM changes
- Secretary changes
- EVIDENCE-001 or MOON changes
- durable queue/persistence/lifecycle
- automatic model or LLM invocation
- execution, approval creation, retry, fallback, scheduler, daemon, or new public protocol
