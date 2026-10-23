# Composition guide

**Current status: Core `0.5.0.dev0`, optional companion `0.3.0.dev0`, and
optional adapters `0.1.0.dev0` source candidate; historical `v0.4.2` and 0.2
provenance remain separate.** The candidate pairing is not a published release
or host-runtime integration.

Mothership is the Consequential Authority Plane in a three-product UME Stack:

| Plane | Responsibility boundary | Authority boundary |
| --- | --- | --- |
| UME Presence | human-facing presentation contracts | no decision or execution authority |
| UME-HARNESS thin candidate | non-executing request preview and presentation; host-native work control | no external consequential authority |
| Mothership | evidence, human decisions, and exact one-use action authority | no model, worker, or generic executor |

There is no automatic runtime dependency between these products. The table is a
responsibility map, not an implemented end-to-end pipeline. The bounded host
routes around this source candidate are cataloged separately; local adapter
checks do not certify a live host or external effect.

## UME Stack responsibility map

UME-HARNESS turns human intent into a bounded local-work preview.
Mothership binds a human decision to bounded authority for one external action.

This is a responsibility relationship, not a runtime dependency. The current
public releases do not contain an automatic Harness-to-Mothership bridge.

The [explicit thin handoff candidate](thin-harness-handoff.md) uses advisory
Harness JSON, real bounded Git observation and the existing retained Session.
It returns distinct execution/readback records to the same foreground entry and
preserves files for offline reread. Its local tests use synthetic interpretation,
terminal answers and transports. No custom Lease or permission conversion is
introduced. The old Lease-specific bridge remains historical compatibility.

## Current receipt connection (source candidate)

The optional [GitHub companion](../packages/mothership-github/README.md) now
provides a pure [attempt-to-receipt adapter](../examples/github_receipt_adapter.md).
The closed `github-execution-attempt.v1` terminal pair becomes an
`external-action-receipt.v0`. Core validates that record and binds separately
supplied Verification to its canonical digest and expected action identity.
This is an implemented package connection, not a Harness runtime bridge.

```text
Trusted caller context: action ID + action digest + consume event ID
                             |
Companion start/finish ------+--> adapter --> Core Receipt
                                                |
Separate Verification --------------------------+--> exact binding
```

The caller takes the expected identity from trusted context, retains exactly
`{"started": start, "finished": finish}` as the referenced evidence, and owns
access to that evidence. The adapter does not fetch, store, or authenticate it.
A caller-supplied consume ID is not proof of durable consumption. Use the
existing executor for its own ledger checks; conversion alone grants nothing.

The integration regression in
[`test_pipeline.py`](../packages/mothership-github/tests/test_pipeline.py)
executes the real local Core/companion path with fake transport, reads the
persisted attempt rows, converts them, binds a separately supplied UNKNOWN
verification, and attempts replay. It covers SUCCESS, FAILED and UNKNOWN,
wrong consume identity, unchanged ledgers during conversion, and one fake PUT
only. Even an executor SUCCESS does not promote that verification to CONFIRMED.
This is offline integration evidence, not a live GitHub or cross-repository test.

## Optional GitHub read-back verification

The companion also provides an explicit `verify_merge_pr()` producer for the
same `github.merge_pr` profile. This producer is included as an opt-in
companion capability; it is separate from the Receipt adapter and does not make
Verification part of Core's execution path. It accepts the exact Core-issued
`FrozenAction`, a validated external-action Receipt, and an optional injected
opener. With the default opener it performs at most two public tokenless GETs:
one pull-request request and, only after a coherent merged PR matches the
frozen head and base, one Git Database commit request. It never consumes
authority, writes either ledger, calls the executor, retries, or polls.

The returned bundle keeps a sanitized pull-request projection, ordered commit
parents, UTC request boundaries, fixed reason codes, and canonical hashes for
the observed state and complete evidence. Remote prose, authors, emails,
headers, raw response bodies, and exception text are discarded. Malformed,
contradictory, future, or pre-existing observations remain `UNKNOWN`; a valid
wrong target or merge topology is `MISMATCH`. Receipt status remains separate
from Verification status, and the receipt input remains unchanged.

The [offline example](../examples/github_readback_verification.md) uses an
explicit synthetic opener. Its result demonstrates contract binding only; it
does not authenticate GitHub, the executor, a human, or the method used to
create a merge. Two GETs are a bounded non-atomic snapshot, and the current
action profile does not bind a base commit SHA.

### Read back a recorded bundle

For a retained bundle whose Core action is no longer live, the companion also
provides `verify_recorded_merge_pr(action, receipt, *, opener=None)`. It accepts
a plain detached action mapping and its bound Receipt as caller-attested data.
It validates the action digest and Receipt binding, then shares the existing
read-only observer; it never restores or reissues a `FrozenAction`, consumes
authority, calls an executor, or changes a ledger. This entry point can observe
after the Core action has expired because it has no authority operation. The
existing `verify_merge_pr()` remains strict and still requires the live
Core-issued `FrozenAction` in the same process.

The installed adapter exposes this path only through the explicit
`mothership-evidence readback` command. Before any GET it validates one complete
`host-evidence-bundle.v0`, its derived Receipt, and `missing == ["verification"]`;
an incomplete bundle or an existing Verification is rejected and cannot be
replaced. A successful command writes a distinct verified bundle to stdout and
the complete sanitized observer evidence as one JSON sidecar on stderr:

```sh
mothership-evidence readback < original.json > verified.json 2> readback-evidence.json
```

Require exit status `0`, keep `original.json` unchanged, and retain the sidecar.
The Python helper `mothership_adapters.readback.readback_evidence(bundle, *,
opener=None)` returns `{"bundle": ..., "evidence": ...}`. Its complete
`evidence` sidecar's canonical SHA-256 must equal the `sha256` in the new
Verification's `evidence_refs`. The observer performs at most two public tokenless GETs and
does not use credentials, an `Authorization` header, retry, polling, authority,
or an external effect. Input/setup failures use a fixed sanitized stderr
diagnostic and nonzero exit; the command emits the sidecar before stdout and
callers must discard both streams on any nonzero exit, including partial output.
Do not merge stdout and stderr with `2>&1`. `UNKNOWN` and `MISMATCH`
observations remain valid output bundles with their status preserved. `export`, `inspect`,
`inspect --human`, and the MCP tools remain offline and do not initiate this
read-back.

The producer writes an allowlisted fixed reason code and bounded explanation
into the existing `observed_state.summary`. `inspect --human` displays that
caller-reported summary after escaping it for terminal output, while keeping
the `caller-attested` / `source-unverified`, `authority=false`, and
`external_effect_verified=false` qualifications. The summary is display data;
the inspector does not parse it into a trusted structured reason or authenticate
the source.

Supplying `inspect --human --readback-evidence readback-evidence.json` with
`verified.json` on stdin also checks the existing sidecar's canonical hash,
action identity/digest and observed-state binding offline. It displays the
sidecar's structured reason as caller-reported data. Hash consistency does not
change source authentication, effect status, timing or causation guarantees.
The [adapter guide](host-adapters.md#read-only-evidence-routes) describes the
bounded regular-file input, failure behavior and preserved UNKNOWN cases.

## Portable action review seam

The source candidate adds the pure
[`mothership.action_review`](action-review.md) API. A host builds one detached
request from its retained live `FrozenAction`, a fresh request ID, and its
host-owned context. After its own review UI or workflow responds, the host
validates that response against the retained request and the same live action.
The request digest covers the action, expiry, and host context, but it is a
correlation value rather than a signature.

The helper performs no ledger write, consume, network call, credential read,
executor callback, or durable resume. It does not authenticate a human or
enforce a lease, revocation, delegation, or runtime-generation rule at the
effect boundary. The optional adapters recheck caller-provided context after
suspension and immediately before transport; these observations are not atomic fences. The unchanged companion executor
has no host callback. Host-specific entry paths and completion evidence are
listed in the [integration catalog](integrations.md) and the practical [host
adapter guide](host-adapters.md). The source candidate has eight bounded routes
with recorded local checks. Their qualification is route-specific; no row claims full gateway coverage,
credentials, a live GitHub effect, or an automatic runtime bridge.

## Delivery replies and one-use authority

Keep delivery, review, authority use, execution reports, and independent
Verification separate when connecting a host. Mothership does not implement a
delivery ACK record, a retrying delivery service, or a durable owner restart.
The existing owner protocol binds `result`/`error` replies to one command; the
reply envelope does not promote its payload into another kind of evidence.
For example, a reply to `prepare` carries a review request, not approval. A
reply to `execute` can carry an executor SUCCESS Receipt, while Verification
is still absent.

When an execution reply is lost, retain the uncertainty and inspect existing
records. Do not recover delivery by invoking the action again. Reading an
exported bundle is a data-only operation: the inspector keeps
`authority=false`, `source-unverified`, and `external_effect_verified=false`.
These fields qualify the inspection, even when it reports internally
consistent decision, consume, and Receipt records. Missing records do not
prove that the corresponding events never occurred.

The owner regressions in
[`test_owner.py`](../packages/mothership-adapters/tests/test_owner.py) compose
the existing Core, companion, and evidence functions at this boundary:

| Bounded trace | Variants | Required observation |
| --- | --- | --- |
| Drain an execution reply as simulated application-delivery loss; inspect retained records; send another `execute` with the same owner/request/action IDs | SUCCESS or UNKNOWN, each with identical or changed PR parameters: four traces | One GET callback and one merge callback, one approval and consume, one start/finish pair; read-only inspections leave records unchanged; replay stops without another callback or Verification |
| Reply to an execution context callback with the next sequence number but stale correlation or an unsupported ACK frame | Old `reply_to`, wrong request ID, or `ack`: three traces | A terminal sanitized error before consume, attempt recording, GET, or merge; the existing approval record stays unchanged |

The second trace currently surfaces a `session` error because Session sanitizes
nested callback failures; it does not expose the underlying protocol exception.
The ACK case is a negative input, not a supported message or new approval form.
These seven cases are bounded regression traces, not exhaustive state-space
exploration, a formal proof, or cross-repository delivery acceptance. They use
synthetic callback payloads and temporary fixture records, never production
approvals or external transports. They do not test timing; existing
[`test_action_review.py`](../tests/test_action_review.py) tests already use a
fixed clock for expiry and host-context binding. No caller-controlled runtime
clock, model checker, event store, or retry policy is added.

## Application and host handoff obligations

These obligations identify the owner of each boundary. They are not new Core
APIs or claims that the corresponding products enforce them today.

| Requested capability | Owner | Connection condition / current limit |
| --- | --- | --- |
| Async continuation authority fence | Runtime host / UME-HARNESS | Recheck lease, session, actor, runtime generation and scope at the effect boundary, including after suspension. Core consume is not a continuation permit; the optional supplemental bridge observes leases but provides no atomic continuation fence. |
| Delegation permission ceiling | Runtime host / UME-HARNESS | Child scope must not exceed parent ceiling, delegated scope or current runtime scope; preserve an explicit empty set and account for parent revocation. Core does not maintain the delegation graph. |
| Fresh observation reference | Source owner and host | Preserve source identity, revision and first-observed expiry; observed text, speaker identity and model inference are evidence, not operator instructions. Re-reading must not silently renew an expired source or authorize retry of an uncertain effect. No global two-minute TTL is imposed by Core. |
| Portable plugin / review-first admission | UME Presence / extension owner | Prepare without package-code execution, review exact bytes, recheck fingerprint, then install disabled and separately admit. Lifecycle scripts, imports and plugin loads are not review preparation. This repo has no package admission engine. |
| Provenance-pinned read and skill usage / CAS | MOON / knowledge lifecycle owner | Keep source content, location, digest and observation context bound; preserve lineage through candidate, usage, review and target comparison. A Core evidence ref does not resolve source ownership, freshness or target CAS. |
| Retained accessibility tree | UME Presence sensor | Revisions and incremental refresh describe observed state; they confer no permission. Capture and privacy controls remain with the source owner. |
| Reviewed deterministic GUI operation | Runtime host with knowledge lifecycle owner | Bind app/window, preconditions and expected result. Compilation or repeated success cannot bypass supported action authority. No generic click or storage profile is added here. |

For a concrete host integration, qualify the actual effect path: suspend it,
change or revoke the host context, resume it, and show that no effect occurs.
Also test an empty delegated scope, stale source reference, changed action or
evidence digest, missing finish, and uncertain outcome without automatic retry.
A pure predicate or synthetic receipt cannot establish those host guarantees.
Already-issued effects cannot be undone by a later revocation.

Only `github.merge_pr` is currently executable through the bounded companion.
A storage, device or other operation requires its own reviewed exact profile
and separately configured executor. Do not relabel it as a GitHub operation,
reconstruct a FrozenAction from JSON, or import a legacy adapter that supplies
caller-controlled `now` into the current runtime API. Core issuance and its
clock must remain authoritative within their documented local scope.

## Public protocol, private policy

Public protocol describes what happened, what evidence exists, what exact object or action is referenced, and which
schema version and stable digest apply. Mothership currently publishes the contracts it already enforces:

- Decision Card and Decision Approval for non-authorizing human review evidence;
- Authority-Action Approval and Authority-Action Consume for one exact supported consequential action;
- `FrozenAction`, exact parameter binding, and trusted-live-ledger one-use consumption;
- `authority-action-review-request.v0` and `authority-action-review-response.v0`
  for the pure portable action review seam;
- the legacy 0.2 compatibility schemas documented below.

These public contracts are descriptive and verifiable. They do not select a model or worker, choose a retry policy,
set confidence or escalation thresholds, route memory, compress context, name customer connectors, or carry secrets.
Those operational choices remain private policy. Production cross-plane orchestration, connector recipes, domain
policy, memory and learning metabolism, worker routing, and incident corpora also remain private.

No new cross-plane contract is implied here. A future contract should be added only when the existing public schemas
cannot express the required boundary, and it must not transfer authority between planes.

## Legacy 0.2 compatibility composition

This legacy section remains the **0.2 compatibility surface** preserved for interoperability and history.

This document describes the legacy 0.2 Frontdoor → WGM → Router → Secretary composition.
Mothership preserves the exact frozen interchange evidence for historical
compatibility. This chain is not the current Mothership authority flow or
adoption path.

Composition means exchanging explicitly supplied, versioned metadata. It does not mean automatic installation,
process invocation, shared credentials, or authority transfer.

## Ordered handoff

| Stage | Protocol | Owner | Meaning |
| ---: | --- | --- | --- |
| 1 | `frontdoor-task` | Agent Frontdoor | bounded task intake |
| 2 | `governance-handoff` | Workflow Governance Model | portable evidence relationship |
| 3 | `router-manifest` | Mothership Router | approval-bound dry-run recommendation |
| 4 | `observation-snapshot` | Secretary TUI | sanitized read-only display data |

The Router and observation documents carry `authority_effect: false` and `execution_effect: false`. A successful
Mothership demo labels its claim `protocol-composition-only`.

## Mothership alone

Install and verify Mothership without any companion. You can inspect public APIs, validate your own explicit protocol
documents, and run fixed diagnostics. This is the recommended first adoption step.

## One companion

Install the chosen project separately, review its own boundary, and export only its documented public interchange
object. Validate that file with Mothership before passing it onward. No project scans the machine for another checkout.

## Full synthetic chain

`mothership demo` reads only the bundled fictional fixtures. It checks schema versions, protocol adjacency, identifier
and capability continuity, and non-escalating effect fields. It does not call companion commands or perform real work.

## Historical responsibility map

- Agent Frontdoor historically owned `intake.v0` task-card semantics.
- Workflow Governance Model historically owned public handoff semantics.
- Mothership Router historically owned dry-run recommendation semantics.
- Secretary TUI historically owned read-only presentation semantics.
- Mothership owns the frozen suite registry, snapshots, digests, fixtures, and compatibility checks.

These names document snapshot provenance only. The historical repositories
are not linked as current adoption dependencies; the bundled schemas and
fixtures in this repository are the current compatibility reference.

## Human-led real workflow

For a real task, a human decides whether to run each independent tool and which explicit output may cross the next
boundary. The human also owns any later command that obtains credentials or executes work. No schema-valid document
can substitute for that decision.

## Updating one stage

A schema change is coordinated, not inferred:

1. the semantic owner releases and documents the new schema;
2. Mothership adds a reviewed snapshot without overwriting unrelated versions;
3. the registry digest and compatibility table change together;
4. valid, invalid, transition, and privacy fixtures are updated;
5. every affected repository runs its conformance suite;
6. publication remains a separate explicit action.

See [Protocol reference](protocols.md), [Portable action review](action-review.md),
[Integration catalog](integrations.md), and the [0.2 compatibility history](legacy/compatibility-0.2.md)
for the exact snapshot, current candidate seam, and historical provenance.
