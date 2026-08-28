# Architecture

Mothership is the decision and consequential-authority plane in a fixed three-product architecture. It owns the
bounded consequential-authority boundary; it does not run models, choose local workers, or ship a general production
executor.

## Current three-product architecture

```mermaid
flowchart LR
    U[UME Presence (private)<br/>human-facing presence<br/>authority: none]
    H[UME-HARNESS<br/>local work governance<br/>external authority: none]
    M[MOTHERSHIP<br/>evidence, decisions,<br/>consequential authority]
    X[Separately configured<br/>bounded executor]
    V[Receipt and verification]

    U -. human-facing surface .-> M
    H -. proposal and evidence .-> M
    M -->|one trusted-live-ledger consumption| X --> V
```

| Product | Owns | Authority boundary |
| --- | --- | --- |
| UME Presence (private) | presentation, voice, persona, and human interaction | no decision or execution authority |
| UME-HARNESS | task intake, local execution leases, local tools, and worktree policy | no external consequential authority |
| MOTHERSHIP | evidence, decisions, exact action freeze, caller-attested binding, and trusted-ledger consume | exact, short-lived, bounded authority only |

This document does not create runtime dependencies between the products. A future Harness-to-Mothership protocol would
require a separate reviewed migration.

## Current Mothership flow

Decision review and Action Authority are separate inputs. A Decision Card never automatically becomes a
`FrozenAction`.

```mermaid
flowchart TD
    E[Proposal and evidence]
    C["Decision Card<br/>authority_effect: false<br/>execution_effect: false"]
    H1{{Human review}}
    D["Decision Approval<br/>review evidence only"]

    P[Exact supported<br/>execution parameters]
    F["FrozenAction<br/>action SHA + short TTL"]
    H2{{Human action decision}}
    A[File-fsynced authority-action decision]
    O["One-shot consume<br/>trusted live ledger"]
    X[Separately configured<br/>bounded executor]
    R[Receipt and verification]

    E --> C --> H1 --> D
    P --> F --> H2 --> A --> O --> X --> R
```

`freeze_action()` accepts an `action_id`, the closed `github.merge_pr` operation, and exact execution parameters. It
validates those parameters, derives the human display from them, freezes the action, computes `action_sha256`, and
sets a fixed ten-minute deadline. A caller cannot inject display fields. In particular, `consequence_if_approved` is
derived presentation; it is not executable input.

`FrozenAction` issuance relies on interpreter-local in-memory state. The object cannot be reconstructed after
serialization, restart, or transfer into a fresh interpreter. On POSIX, however, a child forked after issuance inherits
a copy of both the object and the issuance registry; the API therefore does not provide process-identity isolation.
Freeze, human response handling, and `record_action_decision()` must remain in that issuing interpreter lineage and
complete before the fixed TTL. Remote approval transport and distributed multi-process authority are not supported.

`validate_decision_transport()` accepts only `approve` or `reject` bound to the exact `action_id` and action digest.
`record_action_decision()` writes a caller-supplied, action-bound decision to the dedicated authority-action ledger.
The public API does not authenticate human identity; the calling integration must establish the human ceremony before
recording the decision. The action digest excludes `expires_at`; re-freezing the same `action_id` and parameters after
expiry reproduces the digest, so the library does not bind a response to one unique issuance. The integration must use
a fresh action_id for every freeze and correlate each response to the exact live issuance, including the displayed
expiry, before recording it. Delayed or reused responses must be rejected outside this API.

`consume_action()` atomically permits one use in one trusted, non-rollbackable live ledger history, then rejects
approval replay and action replay there. The API has no global or monotonic ledger anchor: copied, forked, rolled-back,
or restored pre-consume state is another replay domain and must not become an authority source. Mismatch, expiry,
malformed state, unsafe ledger paths, and tamper all fail closed.

After file-fsyncing the event, `consume_action()` returns `(consume event, exact validated action)` in that order. It does
not execute the action. Creating a new ledger file does not fsync its parent directory, so crash durability of that new
directory entry is not claimed. The default package and CLI do not contain a general production bounded executor.
Actual external effects require a separately configured bounded executor that emits receipt and verification evidence.

## Three approval concepts

| Concept | Meaning | Current role |
| --- | --- | --- |
| Decision Approval | a caller attests that a human reviewed one exact Decision Card | review evidence; no execution authority or identity authentication |
| Legacy Invocation Approval | alias, registry, task, prompt, scope, and invocation evidence plus attempt lifecycle | legacy invocation-evidence compatibility |
| Action Authority Decision / Authority-Action Approval | a caller attests that a human approved or rejected one exact `FrozenAction` digest | canonical current consequential-authority path; human provenance is an integration trust assumption |

`validate_decision_approval_binding()` validates a Decision Card and Decision Approval by canonical-JSON SHA-256 and
`decision_id`. Both objects keep `authority_effect: false` and `execution_effect: false`. The result is evidence of
review, not an action decision.

The legacy `mothership.approval` facade remains backed by `orchestration.lib.ledger` and preserves
`approval_granted`, `attempt_started`, and `attempt_finished` evidence. It is not the owner of new consequential
authority.

## Legacy 0.2 Protocol Compatibility

**Status: 0.2 compatibility surface; preserved for interoperability and history. Not the current three-product
architecture.**

```mermaid
flowchart LR
    F[Agent Frontdoor] --> W[Workflow Governance Model]
    W --> R[Mothership Router]
    R --> S[Secretary TUI]
    M[(Mothership<br/>compatibility registry)]
    W -. explicit document .-> M
    M -. validated snapshot .-> S
```

The frozen protocol order remains:

1. `frontdoor-task`
2. `governance-handoff`
3. `router-manifest`
4. `observation-snapshot`

The demo claim remains `protocol-composition-only`. These documents keep `authority_effect` and `execution_effect`
false and do not enter the current authority flow. Frontdoor/WGM/Router-based Decision Card ingestion remains a
compatibility input until a separately reviewed migration.

## Legacy 0.1 compatibility

The packaged `frontdoor`, `safety`, legacy executor registry, invocation contracts, and
`orchestration.lib.ledger` preserve older import and evidence surfaces. They remain distribution compatibility, not
architectural owners. Removing or migrating them would require a major-version decision.

## Installed package and read-only CLI

The distribution is `mothership-control-plane`; Python 3.12 or newer is required and runtime dependencies are empty.
The default CLI remains read-only with respect to consequential external state.

| CLI surface | Responsibility |
| --- | --- |
| `mothership verify` | check immutable packaged resources and protocol consistency |
| `mothership doctor` | run fixed local availability probes in a sanitized environment |
| `mothership protocol` | list or validate frozen 0.2 compatibility protocols |
| `mothership demo` | validate the bundled 0.2 synthetic chain |
| decision-card and decision-batch commands | render review-only Decision Cards or ephemeral batches |
| GitHub observation commands | perform explicit read-only public observation and render candidates or Cards |

No CLI command freezes, records, consumes, or executes an authority action. The GitHub observation commands can issue
read-only requests; they do not mutate GitHub.

## Public modules

| Public module | Implementation source | Contract |
| --- | --- | --- |
| `mothership.action_authority` | `orchestration.lib.action_authority*` | exact action freeze, caller-attested decision, and trusted-live-ledger consume |
| `mothership.scope` | `orchestration.lib.paths` | legacy bounded local paths and staging |
| `mothership.approval` | `orchestration.lib.ledger` | legacy invocation approval and attempt evidence |
| `mothership.adapters` | `orchestration.lib.adapters` | immutable plans and diagnostics |
| `mothership.contracts` | canonical, JSON, contract, registry, and decision modules | strict data and Decision Card / Decision Approval binding |
| `mothership.protocols` | protocol registry and validator | 0.2 compatibility validation |

The facades keep one authoritative implementation for each behavior. Existing library calls create output or ledger
evidence only for an explicit caller-supplied target; those writes are not side effects of the read-only CLI.

## Immutable packaged resources

Mothership ships immutable packaged resources for the 0.2 compatibility lane: a closed registry, schema snapshots and
SHA-256 digests, golden-path fixtures, inert executor examples, and an inventory. `mothership verify` checks inventory
membership, sizes, hashes, registry shape, schema digests, inert executors, and golden-path transitions.

## Compatibility protocol validation flow

```text
explicit normalized absolute path
  -> no-follow component traversal
  -> bounded regular-file read
  -> strict UTF-8 JSON decode
  -> exact version and closed schema
  -> metadata safety scan
  -> recursively detached result
```

Unknown protocol kinds fail before file access. A schema-valid document remains metadata; validation never promotes it
to a Decision Approval or an Action Authority Decision. See the [protocol reference](protocols.md).

## Trust and failure boundaries

- Exact action inputs and every ledger row are untrusted until their closed validation succeeds.
- FrozenAction decision recording must remain in its issuing interpreter lineage, including any inherited fork state.
- Consume-once semantics require one trusted, non-rollbackable live ledger history.
- Packaged schemas and fixtures are trusted only after inventory and registry hashes pass.
- Explicit local JSON is untrusted and must cross the strict file and schema boundary.
- Diagnostic and observation output is untrusted evidence, never permission.
- Credentials, separately configured executors, external preconditions, receipts, and verification remain outside the
  default CLI.
- Public commands and authority APIs fail closed; they do not retry, repair input, choose a fallback, or reinterpret a
  failed check as success.
