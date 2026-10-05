# Protocol reference

**Status: 0.2 compatibility surface; preserved for interoperability and history. Not the current three-product
architecture.**

Mothership preserves the frozen suite snapshot. The semantic owner names
below are historical provenance, not current adoption dependencies. A
Mothership snapshot records compatibility; it does not take ownership of
companion semantics or enter the current Action Authority path.

## Portable action review schemas

The `0.5.0.dev0` source candidate adds two closed contract kinds for the pure
`mothership.action_review` API. The optional companion is paired at
`0.3.0.dev0`; published `v0.4.2` remains the historical release. These schemas
standardize review transport between a host UI or workflow and the existing
Core action. They do not describe a new executor or a host runtime adapter.

| Contract kind | Schema version | Exact top-level fields | API role |
| --- | --- | --- | --- |
| `authority-action-review-request` | `authority-action-review-request.v0` | `schema_version`, `request_id`, `action`, `action_sha256`, `expires_at`, `host_context`, `request_sha256` | Detached data derived from a retained live `FrozenAction` |
| `authority-action-review-response` | `authority-action-review-response.v0` | `schema_version`, `request_id`, `request_sha256`, `action_id`, `action_sha256`, `decision` | Host response with `approve` or `reject` |

The request's `host_context` has exactly `host_id`, `session_id`, `actor_id`,
`runtime_generation`, and ordered `scope`. IDs and scope entries use the closed
ASCII patterns and lengths defined by the schemas. Scope may be empty; it is a
host-computed review scope, not a credential, human-authentication result,
delegation proof, or target-specific authorization.

Generic `validate_contract` checks the closed shape, field types, versions,
lengths, patterns, and unknown-field rejection. `build_review_request()` and
`validate_review_response()` add the live binding: action and expiry come from
the original Core-issued action, the request digest covers all request fields
except itself, the expected request is retained by the host, and every response
correlation field must match. Approve also requires the frozen operation to be
in scope; unchanged empty-scope reject is valid.

An action or expiry changed and rehashed is still rejected because the API
rebuilds the request from the live action and compares canonical JSON bytes with
the retained expected request. Hashes are correlation values, not signatures.
Expired actions propagate the existing Core expiry error. Host-context drift
rejects both decisions before the caller records or consumes authority.

The helper is pure and repeatable. It performs no ledger write, consume,
network call, credential read, executor callback, identity authentication,
lease/revocation enforcement, or durable cross-process resume. The trusted live
ledger remains the one-use boundary, and the host owns the effect-time check.
See [Portable action review](action-review.md) for the API example and
[Integration catalog](integrations.md) for the unimplemented host paths and
their measurable completion criteria.

The schema files are packaged under
`evidence/contracts/authority-action-review-request.v0.schema.json` and
`evidence/contracts/authority-action-review-response.v0.schema.json`. Use the
existing contract validator for shape checks; do not treat a schema-valid
response as proof of human identity, runtime interception, or external effect.

## Ordered registry

| Order | Kind | Version | Owner | Upstream source |
| ---: | --- | --- | --- | --- |
| 1 | `frontdoor-task` | `intake.v0` | Agent Frontdoor | `src/frontdoor/schema/intake.v0.json` |
| 2 | `governance-handoff` | `1.1` | Workflow Governance Model | `schemas/workflow-handoff.1.1.schema.json` |
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

The suite selects the portable 1.1 contract. The released permissive 1.0
snapshot is retained separately and is never silently reinterpreted as 1.1.

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
