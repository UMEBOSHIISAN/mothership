# Adapter interoperability: first reference connection

Date: 2026-09-26
Status: PROPOSED — written design for review; not implemented or released
Source baseline: `ba21c5167d07281303288879b110977be31616f5`

## Purpose

Mothership should give separately maintained applications a precise connection
boundary for human decisions, exact actions and evidence. Application-specific
devices, inference, storage and workflows stay in their respective products.
The first deliverable is a working, offline-testable reference seam using the
existing GitHub companion and existing Core record contracts.

This is record interoperability. It does not imply that arbitrary operations,
remote executors or other repositories already integrate with Authority Core.

## Existing capabilities and the concrete gap

- `mothership/contracts.py` exports dedicated proposal, receipt, verification
  and receipt/verification binding validators.
- `orchestration/lib/external_action.py` requires a state digest and evidence
  references for conclusive verification, and binds verification to the
  canonical receipt digest and expected action identity.
- `mothership_github/receipts.py` records and validates
  `github-execution-attempt.v1` start/finish events, including their relationship.
- `mothership_github/executor.py` returns these events after a bounded attempt.
- No converter currently connects these companion events to
  `external-action-receipt.v0`. The companion's execution record is not itself
  that Core receipt contract.
- Existing `mothership.adapters` builds legacy model invocation plans. It is
  not the home for this consequence/evidence adapter.

These are repository observations, not missing functionality inferred from a
product name. No third-party framework, service or dependency is needed.

## Scope choice

Three possible approaches were considered:

1. **Companion-owned pure conversion plus a reference example (recommended).**
   Reuse the current Core schemas and exercise a real format boundary. Small
   enough to verify, while making the connection reproducible by other repos.
2. Document the boundary only. Useful guidance, but no executable evidence that
   the formats connect correctly.
3. Introduce a universal adapter registry/runtime or arbitrary action profiles.
   This expands execution authority and lifecycle design before the first seam
   is demonstrated. It is outside this slice.

## Responsibilities at the connection boundary

| Owner | Responsibility | What the handoff must not imply |
| --- | --- | --- |
| Source/application | Capture data, provenance, retention and access controls | Observation is not a human command |
| Runtime host | Actor/session/lease validity, delegation ceiling, effect-time checks | Work assignment is not consequential authority |
| Mothership Core | Supported exact action, decision binding, ledger consume | Consume is not proof that an effect occurred |
| Operation companion | Operation-specific execution and normalized attempt report | Executor SUCCESS is not independent verification |
| Independent verifier | Read-back evidence and comparison with the expected action | A receipt alone does not establish external truth |
| Evidence owner | Retain and resolve referenced artifacts under access policy | A digest grants neither read access nor authenticity |

Adapter code belongs with the operation/product that understands its input.
Core owns the shared contracts. Integrators import the public Core facade;
they do not copy validators into each product. Core does not import products.

Source freshness, runtime continuation guards and permission ceilings remain
host contracts. This slice documents their boundary but does not claim to
implement or test those other products' enforcement.

## First adapter API

Proposed location:
`packages/mothership-github/mothership_github/external_action.py`.

Proposed public callable:

```python
build_external_action_receipt(
    started,
    finished,
    *,
    expected_action_id,
    expected_action_sha256,
    expected_consume_event_id,
    executor_ref,
) -> dict[str, object]
```

The inputs are supplied records, not file paths or a live `FrozenAction`.
The expected identity and consume-event ID must come from the caller's trusted
execution context, not be copied blindly from the untrusted records under test.
The converter validates agreement with those expectations. It cannot prove
that the supplied rows were ever durably written, or authenticate the caller.

Validation is closed and fail-closed:

1. Deep-copy the input records and `executor_ref` so later caller mutation
   cannot change the output. Deep-copy the final validated receipt as well;
   the existing Core validator alone only returns a shallow top-level copy.
2. Require one exact v1 `attempt_started` row and one exact v1
   `attempt_finished` row. Reuse the companion's pure event/history validation;
   do not invoke its ledger-opening or append functions.
3. Require caller-supplied expected IDs and digest to be strings matching the
   corresponding existing closed-contract patterns before comparing them.
   Check event IDs, start/finish linkage, matching action ID, action digest and
   consume-event ID. Reject mismatched expected identity, duplicate IDs, unknown
   fields, invalid schema versions, and inconsistent observation/outcome pairs
   rejected by the existing event validator. Apply the additional conservative
   failure normalization below; event-shape validity alone is insufficient.
4. Validate real UTC dates and finish time at or after start time using the
   existing companion validation. A timestamp-shaped impossible date is invalid.
5. Validate `executor_ref` using the existing closed reference contract through
   the final Core receipt validator. This reference is caller-supplied evidence
   metadata, not authenticated executor identity.
6. Construct and validate an `external-action-receipt.v0` through the public
   `mothership.contracts.validate_external_action_receipt` helper.

Malformed inputs, including companion `ReceiptError` validation failures,
raise `ContractError` with fixed diagnostic text. No partial
receipt, retry, fallback or automatic repair is returned. Companion validation
errors are translated at this public boundary; raw input values are not echoed.

## Exact projection and evidence

| Core receipt field | Source |
| --- | --- |
| `schema_version` | Literal `external-action-receipt.v0` |
| `action_id`, `action_sha256` | Validated matching attempt identity |
| `executor_ref` | Validated copy of the caller-provided reference |
| `started_at` | Start row `recorded_at` |
| `finished_at` | Finish row `recorded_at` |
| `status` | Mapping below |
| `executor_observation_ref.ref_id` | `github-attempt:` followed by the start event ID |
| `executor_observation_ref.sha256` | Canonical SHA256 of the exact evidence object below |

The referenced evidence object is exactly
`{"started": <validated start row>, "finished": <validated finish row>}`.
Use the existing `canonical_json_sha256` implementation; JSON key order does
not change the digest. No HTTP response body, token, local path or extra
metadata enters this object. The caller retains these supplied rows and makes
this exact object available to its evidence store. The converter neither stores
it nor silently publishes a resolvable endpoint. Evidence retention/access is
an explicit integration obligation.

| Validated finish outcome | Core status |
| --- | --- |
| `success` | `SUCCESS` |
| `failure` with an executor-recognized client failure observation | `FAILED` |
| Other valid `failure` observations | `UNKNOWN` |
| `reconciliation_required` | `UNKNOWN` |

Explicit reconciliation stays UNKNOWN even if its observation looks positive.
For a failure row, pass only its validated observation to the existing pure
executor normalizer and return FAILED only when that normalizer returns
`failure`. This reuses its recognized client-failure set rather than creating a
second status-code policy. A failure label with status 0, 5xx, or otherwise
ambiguous facts becomes UNKNOWN, without modifying the original row. A 3xx
receipt does not preserve the executor's `redirect_rejected` flag: the converter
cannot reconstruct it, so it also projects to UNKNOWN. This intentionally loses
certainty, not evidence; the exact original pair remains referenced.

SUCCESS retains executor-local meaning. A missing finish is not a completed
UNKNOWN receipt: reject it, leaving the host's unfinished attempt unresolved.
Do not invent a finish timestamp, fabricate a receipt or re-consume authority.

## Reference flow and compatibility

```text
Existing companion attempt start + finish
             |
             v
Pure conversion adapter -> Core receipt validator
             |
             +---- retained source evidence (caller-owned)
             |
             v
Separately supplied verification -> existing exact binding validator
```

Add a source-checkout example using synthetic attempt rows and separately
labelled synthetic verification. It must run without network, credentials,
model calls, services or writes to an authority ledger. Demonstrate a valid
binding, a digest mismatch rejection, and UNKNOWN remaining UNKNOWN after
successful binding. The example must not claim real independent observation.

No automatic call from `execute_action_merge_pr` is added. Its existing result
shape, receipt ledger and authority behavior remain compatible. Callers opt into
conversion and explicitly supply their expected identities and executor ref.

Keep the companion's existing exact Core dependency pin. No schema changes,
new action profile, registry, plugin loading, remote execution token, credentials
or CLI switch are introduced. Unsupported versions and operations stay rejected.
`FrozenAction` remains interpreter-issued; JSON transport does not recreate it.

Future adapters can reuse the shared record validators and the reference
rejection cases. Supporting a new *executable operation* still requires its own
exact profile and design review. This slice does not turn GitHub fields into
generic storage or device actions.

## Acceptance evidence required for implementation

- Valid success, failure and reconciliation produce the exact expected receipt.
- Explicit reconciliation with apparently positive facts remains UNKNOWN.
- Failure labels with status 0, 503, 302, or HTTP 200 without a positive merge
  outcome project to UNKNOWN; recognized client failure 409 projects to FAILED.
- Start/finish/action/consume mismatches and malformed closed records reject.
- Impossible dates and reversed timestamps reject; equal timestamps are valid.
- Missing finish rejects without fabricating completion.
- Core-valid long action IDs remain accepted; evidence reference length stays
  bounded because it uses the fixed-length start event ID.
- Evidence digest equals the canonical source-pair digest, changes when either
  source row changes, and is insensitive to JSON key ordering.
- Inputs remain unchanged, and subsequent caller mutation does not mutate output.
- Dedicated Core validators accept the produced receipt; independent synthetic
  verification binds only to its exact canonical digest and expected identity.
- Conversion and its example never call transport, consume, ledger access,
  subprocess, clocks or evidence-store IO. Existing public Core validation reads
  bundled schemas; those package-resource reads are permitted. No live effect
  is used in acceptance.
- Relevant companion/Core regression suites and repository integrity checks pass.

## Review and delivery boundary

This document is the architectural design stage, not an implementation plan.
Written-design review, the required high-risk advisory design gate and a reviewed
implementation plan precede product changes. The independent code audit supports
the source observations; it does not grant human approval.

The design branch starts from the hardening change in PR #29. It does not merge
or release that PR. This slice is complete only when the approved adapter and
reference example are implemented, independently reviewed and verified; the
present document alone does not complete the user's interoperability request.
