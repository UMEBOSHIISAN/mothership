# Composition guide

**Current status: public product boundaries and protocols; private operating policy and composition.**

Mothership is the Consequential Authority Plane in a three-product UME Stack:

| Plane | Responsibility boundary | Authority boundary |
| --- | --- | --- |
| UME Presence | human-facing presentation contracts | no decision or execution authority |
| UME-HARNESS | local work governance and exact local execution leases | no external consequential authority |
| Mothership | evidence, human decisions, and exact one-use action authority | no model, worker, or generic executor |

There is no automatic runtime dependency between these products. The table is a responsibility map, not an
implemented end-to-end pipeline.

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

This document describes the legacy 0.2 Frontdoor → WGM → Router → Secretary composition. The companions remain
independently adoptable, and Mothership preserves their exact frozen interchange evidence. This chain is not the
current Mothership authority flow.

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

## Responsibility map

- [Agent Frontdoor](https://github.com/UMEBOSHIISAN/agent-frontdoor) owns `intake.v0` task-card semantics.
- [Workflow Governance Model](https://github.com/UMEBOSHIISAN/workflow-governance-model) owns public handoff semantics.
- [Mothership Router](https://github.com/UMEBOSHIISAN/mothership-router) owns dry-run recommendation semantics.
- [Secretary TUI](https://github.com/UMEBOSHIISAN/secretary-tui) owns read-only presentation semantics.
- Mothership owns the frozen suite registry, snapshots, digests, fixtures, and compatibility checks.

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

See [Protocol reference](protocols.md) for the exact v0.2 snapshot.
