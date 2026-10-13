# Portable action review API

**Status: source-candidate API for Core `0.5.0.dev0`.** The optional GitHub
companion is paired at `0.3.0.dev0`; optional adapters are `0.1.0.dev0`.
Their bounded local qualification is recorded in the [integration catalog](integrations.md),
with setup in the [host adapter guide](host-adapters.md). Published `v0.4.2`
remains the historical public release.

This page describes the additive `mothership.action_review` seam. It lets an
application keep its existing review UI, tool loop, or workflow checkpoint
while using one closed request and response shape for a live Mothership action.
It does not turn Mothership into a host runtime, executor, identity provider, or
durable resume service.

## API surface

The module exports:

```python
from mothership.action_review import (
    ActionReviewError,
    build_review_request,
    validate_review_response,
)
```

`build_review_request(frozen_action, *, request_id, host_context)` creates
detached JSON data from the original Core-issued `FrozenAction`. The caller
must retain that live object and the returned request as the expected review
pair.

`validate_review_response(
    frozen_action,
    expected_request,
    response,
    *,
    current_host_context,
)` rebuilds the request from the retained action, request ID, and current host
context. It requires canonical equality with the retained expected request,
matches every response correlation field, applies the existing decision
validator, and returns exactly:

```python
{"decision": "approve", "action_id": "...", "action_sha256": "..."}
```

The `decision` value is always either `approve` or `reject`.

Malformed, stale, mismatched, or reconstructed inputs raise `ActionReviewError`.
An expired live action propagates Core's public `ActionExpiredError` (alias
`ExpiredActionError`), not `ActionReviewError`; catch it separately. Validation
is pure: it does not append a decision event,
consume authority, call a transport, read credentials, or execute an effect.
Import `ActionExpiredError` from `mothership.action_authority` and catch it
before `ActionReviewError` when the caller reports expiry separately.

## The request and response objects

The request has exactly these top-level fields. Unknown fields and type changes
are rejected by the closed schema validator.

| Field | Meaning |
| --- | --- |
| `schema_version` | `authority-action-review-request.v0` |
| `request_id` | Fresh caller-owned correlation ID |
| `action` | Detached representation derived from the live `FrozenAction` |
| `action_sha256` | Digest of the Core action representation |
| `expires_at` | The original Core action expiry; it cannot be extended here |
| `host_context` | Host-owned review context at request creation |
| `request_sha256` | Canonical digest of every preceding request field |

The response has exactly these top-level fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `authority-action-review-response.v0` |
| `request_id` | Must match the retained request |
| `request_sha256` | Must match the retained request digest |
| `action_id` | Must match the live action and retained request |
| `action_sha256` | Must match the live action and retained request |
| `decision` | `approve` or `reject` |

`host_context` has exactly `host_id`, `session_id`, `actor_id`,
`runtime_generation`, and `scope`. The four IDs are ASCII strings of 1–128
characters matching `[A-Za-z0-9][A-Za-z0-9._:-]*`. `scope` is an ordered list
of at most 64 unique strings, each 1–128 characters matching
`[a-z][a-z0-9_.:-]*`. An empty scope is meaningful and is preserved.

Scope is the host's effective review scope. It is not a credential,
authentication result, delegation proof, or target-specific authorization. An
`approve` response also requires the frozen operation name to be present in
scope. A `reject` response with an unchanged empty scope remains valid.

## Install the source candidate

The remote default branch includes this portable review API because [PR #43](https://github.com/UMEBOSHIISAN/mothership/pull/43)
is merged. The commands below pin its reviewed runtime revision,
`6793c87d2c7866d53d2966d4794be82aafeae917`, then install Core `0.5.0.dev0`
and companion `0.3.0.dev0` together from that same checkout. This is a pinned
unreleased source example for the main portable review runtime, separate from
the published v0.4.2 release and the newer PR #45 readback candidate. Review a
later revision separately before substituting it.

Use Python 3.12 or newer and run this in a new directory:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git mothership-portable-review
cd mothership-portable-review
git fetch origin 6793c87d2c7866d53d2966d4794be82aafeae917
git switch --detach 6793c87d2c7866d53d2966d4794be82aafeae917
python3 -m venv .venv-portable
. .venv-portable/bin/activate
python -m pip install . ./packages/mothership-github
python -m pip check
python -I -B examples/portable_action_review.py
mothership verify
```

Git downloads the source; pip may obtain build tooling. Both installs stay in
the selected virtual environment. Core has no runtime dependencies; companion
requires this exact Core version. Neither package installs a host SDK or
activates a plugin. The final example and `verify` run offline.
`pip check` checks declared dependencies; `mothership verify` checks Core's
bundled resources and does not check the companion or qualify a host adapter.

The example is a source file, not an installed command. `-I` excludes source
import paths so its Core and companion imports come from the installed pair.
It uses a temporary ledger and synthetic transport, then removes the ledger.
Expected output includes `fake_puts: 1`, `replay: "blocked"`,
`receipt_status: "SUCCESS"`, and `verification_status: "UNKNOWN"`.
All five host-context fields appear in `context_drift_blocked`. These are
simulated observations, not a GitHub merge or a qualified host adapter.

For the Core-only lifecycle and wheel installation, see
[installation](installation.md). For an existing source environment that
already exposes both packages, the `PYTHONPATH` invocation below remains valid.

## Minimal offline call

The following is the shape a host application uses after it has obtained an
exact action. The response below is explicitly simulated; it is not a model
output or proof of human identity.

```python
from mothership.action_review import build_review_request, validate_review_response

host_context = {
    "host_id": "my-host",
    "session_id": "session-01",
    "actor_id": "operator-01",
    "runtime_generation": "generation-7",
    "scope": ["github.merge_pr"],
}

request = build_review_request(
    frozen_action,
    request_id="review-01",
    host_context=host_context,
)

# The host's own UI or workflow supplies this response after review.
response = {
    "schema_version": "authority-action-review-response.v0",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "action_id": request["action"]["action_id"],
    "action_sha256": request["action_sha256"],
    "decision": "approve",
}

decision = validate_review_response(
    frozen_action,
    request,
    response,
    current_host_context=host_context,
)
```

The complete source example uses the real local Core and GitHub companion with
synthetic transport:

```sh
PYTHONPATH=.:packages/mothership-github python examples/portable_action_review.py
```

It labels the response as simulated, stops before ledger and transport work on
each changed context field, reaches a `SUCCESS` Receipt and a separate
`UNKNOWN` Verification in the valid path, and shows that replay produces at
most one fake PUT. This is offline composition evidence; it is not a live
Dots, OpenClaw, Agents SDK, LangGraph, MCP, or UME-HARNESS integration test.

## What validation binds

The caller owns the trust boundary around the helper:

1. Keep the original live `FrozenAction`; never reconstruct it from request JSON.
2. Keep the original expected request; never replace it with a request returned
   by a client or model.
3. Supply a fresh `request_id` for each review and a fresh action ID for each
   freeze.
4. Pass the host context observed at the point where the host is ready to
   review or resume.
5. Treat the returned mapping as a decision binding. The existing ledger still
   records the decision and enforces one consume in its trusted live history.

The request digest covers `action`, `action_sha256`, `expires_at`,
`host_context`, `request_id`, and `schema_version`. Recomputing a digest after
changing the action or expiry does not make the response valid: the helper
rebuilds the request from the live action and compares canonical bytes with the
retained request. Hashes correlate records; they are not signatures and do not
authenticate the host, operator, or model.

Expiry and any drift in `host_id`, `session_id`, `actor_id`,
`runtime_generation`, or ordered `scope` reject both decisions. The check is
before the caller records a decision or invokes its executor. It does not close
a later race between validation and the effect. A host must recheck its own
lease, revocation, delegation, and runtime-generation rules at the actual
effect boundary, including after suspension or a workflow resume.

## Boundaries that remain with the host

This API deliberately does not:

- authenticate a human or turn a model response into human authority;
- add an executor callback to the unchanged GitHub companion;
- add a global issuance registry or distinguish two misissued actions that reuse
  identical IDs, bytes, and expiry;
- renew an action, change its Core-owned clock, or add a send deadline;
- persist a cross-process resume token or recover a spent action after restart;
- enforce a host's lease, revocation, delegation ceiling, sandbox, or network
  boundary;
- make a generic operation profile executable; only the reviewed
  `github.merge_pr` companion path is currently executable.

The companion's opt-in `verify_merge_pr()` producer remains a separate read-back
path. It consumes no authority and does not turn a Receipt `SUCCESS` into
independent confirmation. Missing, contradictory, or uncertain observations
remain `UNKNOWN` or `MISMATCH` under that producer's documented rules.

For proposed host entry paths and measurable completion criteria, see the
[integration catalog](integrations.md). For the schema kinds and generic
validator boundary, see the [protocol reference](protocols.md#portable-action-review-schemas).
