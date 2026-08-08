# Protocol reference

Mothership is the **installable hub** for the frozen suite snapshot. Each semantic owner remains **independently
adoptable**. In plain terms, every companion is independently adoptable and can release on its own schedule. A
Mothership snapshot records compatibility; it does not take ownership of companion semantics.

## Ordered registry

| Order | Kind | Version | Owner | Upstream source |
| ---: | --- | --- | --- | --- |
| 1 | `frontdoor-task` | `intake.v0` | Agent Frontdoor | `src/frontdoor/schema/intake.v0.json` |
| 2 | `governance-handoff` | `1.0` | Workflow Governance Model | `schemas/workflow-handoff.schema.json` |
| 3 | `router-manifest` | `1.0` | Mothership Router | `src/mothership_router/schema/router-manifest.1.0.schema.json` |
| 4 | `observation-snapshot` | `1.0` | Secretary TUI | `schemas/observation-snapshot.1.0.schema.json` |

Every v0.2 entry has `authority_capable: false` and `execution_capable: false`. Router and observation documents also
carry `authority_effect: false` and `execution_effect: false`.

## Registry fields

Each entry contains an exact kind, version, owner repository, upstream source path, bundled schema path, schema SHA-256,
predecessors, successors, effect capabilities, and the Mothership version that froze it. Unknown fields fail closed.

## List and validate

List installed snapshots with `mothership protocol list`.

Validate an explicit file with:

```text
mothership protocol validate KIND ABSOLUTE_FILE
```

A valid result exits 0 and reports the kind, protocol version, and false effect fields. Invalid input exits 1. Every
unknown kind is rejected before file access. Usage errors exit 2.

The validator rejects relative or non-normalized paths, symbolic links, special files, oversized input, malformed UTF-8,
duplicate keys, non-finite numbers, version drift, unknown fields, type errors, secret-like keys, and private paths.

## Protocol meanings

### `frontdoor-task`

A bounded, reviewable task card. It carries requested work, allowed and forbidden actions, evidence needs, risk tags,
unknowns, assumptions, and a human-gate state. It cannot select or invoke a worker.

### `governance-handoff`

Portable evidence metadata for one task and capability with a bounded token budget. It contains references, not raw
prompts, model output, credentials, or approval.

### `router-manifest`

A dry-run recommendation with status, optional candidate alias, registry digest, and reasons. It explicitly carries no
authority or execution effect.

### `observation-snapshot`

A sanitized view of explicitly supplied governance or Router state. It makes no freshness claim and cannot mutate the
observed system.

## Golden path

The bundled fixtures share one fictional task identifier and capability. `mothership demo` validates each schema, the
ordered edges, continuity, and non-escalating effects. Its only claim is `protocol-composition-only`.

## Development companion audit

`tools/check_companion_conformance.py` audits source owners before Mothership records compatibility. It requires four
explicit, normalized repository roots in protocol order and rejects symbolic links, traversal, missing artifacts, wrong
owners, stale commits, schema drift, example drift, and effect escalation. It never searches the filesystem for a
repository.

```text
python tools/check_companion_conformance.py \
  --frontdoor-root /abs/path/to/agent-frontdoor \
  --wgm-root /abs/path/to/workflow-governance-model \
  --router-root /abs/path/to/mothership-router \
  --secretary-root /abs/path/to/secretary-tui
```

Success is one canonical, path-free JSON report. The command pins the exact commit set listed in
[Compatibility](compatibility.md); a different commit fails closed until the suite is reviewed and deliberately updated.

## Schema update procedure

1. The semantic owner publishes and documents a versioned schema.
2. Mothership reviews the public owner bytes and adds a frozen snapshot.
3. The registry version, source path, bundled path, and SHA-256 are updated together.
4. Positive, negative, transition, privacy, and package-inventory tests are updated.
5. Compatibility and composition documentation are updated in the same change.
6. All affected companion conformance suites pass before a release candidate is described as compatible.

Never overwrite a snapshot silently or reinterpret a prior version in place.
