# Protocol reference

Mothership is an installable hub that composes explicit records without taking semantic ownership from independently adoptable companion protocols. It owns the Flight index, event envelope, and whole-run evaluation.

## Flight index and event envelope

`flight.json` uses `mothership.flight-index.v1`: run identifier, ordered event identifiers, required stages, privacy
profile, protocol-registry digest, bundle digest, and optional derived verdict. The declared verdict is untrusted until
recomputed. `events.jsonl` uses `mothership.flight-event.v1`: event/run identity, type, stage, timestamp, producer,
predecessors, subject protocol kind/version/location/digest, scope/action class, authority/execution flags, outcome,
redaction metadata, and optional extension namespace.

The source protocol owns its extension namespace. An extension cannot alter closed envelope fields, create authority, or
widen the verifier's interpretation.

## Versions and digests

Index, event, and Generic JSONL schemas are versioned and fail closed on unknown versions or fields where strict closure
applies. The bundle digest covers canonical index content without its digest and derived verdict, exact `events.jsonl`
bytes, and sorted content-addressed artifacts. Derived reports are excluded so they can be regenerated.

The frozen v0.2 registry has separate schema SHA-256 digests. Its projection is `frontdoor-task`,
`governance-handoff`, `router-manifest`, then `observation-snapshot`; it is `protocol-composition-only` with
`authority_effect: false` and `execution_effect: false`.

## v0.2 owner snapshot

| Kind | Version | Semantic owner | Upstream source |
| --- | --- | --- | --- |
| `frontdoor-task` | `intake.v0` | Agent Frontdoor | `src/frontdoor/schema/intake.v0.json` |
| `governance-handoff` | `1.1` | Workflow Governance Model | `schemas/workflow-handoff.1.1.schema.json` |
| `router-manifest` | `1.0` | Mothership Router | `src/mothership_router/schema/router-manifest.1.0.schema.json` |
| `observation-snapshot` | `1.0` | Secretary TUI | `schemas/observation-snapshot.1.0.schema.json` |

## Verdict precedence

```text
INVALID > DRIFTED > INCOMPLETE > COMPLETE
```

`INVALID` is malformed, contradictory, or substituted syntax/schema/identity/digest/graph material. `DRIFTED` is valid
evidence of authority, scope, action-class, result, or persistence mismatch. `INCOMPLETE` is absent required material.
`COMPLETE` is present, valid, linked, within authority, evidence-backed, verified, and persisted material.

## Generic JSONL boundary

Generic JSONL is the only shipped importer. It translates one explicit source into a Flight Bundle; it is not a runtime
integration. OpenAI Agents SDK, LangGraph, Claude Code, Codex CLI, and AutoGen are candidates, not adapters.

## v0.2 validation

`mothership protocol validate KIND ABSOLUTE_FILE` validates one explicit snapshot. An unknown kind is rejected before file access. The validator rejects relative/non-normalized paths, symbolic links, special files, oversized input,
malformed UTF-8, duplicate keys, non-finite numbers, unsupported versions, unknown fields, secret-like keys, and private
paths.

## Schema update procedure

1. The semantic owner publishes a versioned schema.
2. Mothership reviews the public owner bytes and freezes a new snapshot.
3. Registry version, owner source, bundled path, and SHA-256 update together.
4. Positive, negative, transition, privacy, and package-inventory tests update together.
5. Compatibility and composition documentation update with the verified snapshot.

Never overwrite a snapshot silently or reinterpret a prior version in place.
