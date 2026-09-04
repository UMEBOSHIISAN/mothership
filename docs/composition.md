# Composition guide

**Current status: public product boundaries and protocols; historical 0.2 provenance.**

Mothership is the Consequential Authority Plane in a three-product UME Stack:

| Plane | Responsibility boundary | Authority boundary |
| --- | --- | --- |
| UME Presence | human-facing presentation contracts | no decision or execution authority |
| UME-HARNESS | local work governance and exact local execution leases | no external consequential authority |
| Mothership | evidence, human decisions, and exact one-use action authority | no model, worker, or generic executor |

There is no automatic runtime dependency between these products. The table is a responsibility map, not an
implemented end-to-end pipeline.

## UME Stack responsibility map

UME-HARNESS turns human intent into bounded local work.
Mothership turns a human decision into bounded external consequence.

This is a responsibility relationship, not a runtime dependency. The current
public releases do not contain an automatic Harness-to-Mothership bridge.

## Public protocol, private policy

Public protocol describes what happened, what evidence exists, what exact object or action is referenced, and which
schema version and stable digest apply. Mothership currently publishes the contracts it already enforces:

- Decision Card and Decision Approval for non-authorizing human review evidence;
- Authority-Action Approval and Authority-Action Consume for one exact supported consequential action;
- `FrozenAction`, exact parameter binding, and trusted-live-ledger one-use consumption;
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

See [Protocol reference](protocols.md) and the [0.2 compatibility history](legacy/compatibility-0.2.md)
for the exact snapshot and its historical provenance.
