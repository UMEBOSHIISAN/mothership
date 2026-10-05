# Portable action review — 0.5 source candidate

Status: implementation design; reviewed in a bounded read-only CC consultation
on 2026-10-05. Publication and host runtime integration are separate work.

## Purpose

Let an application reuse Mothership's exact-action boundary with its existing
approval UI, tool runtime and workflow framework. Standardize the JSON review
request and response that callers otherwise construct themselves. Preserve the
original live `FrozenAction`, existing ledger and bounded GitHub companion.

## Additive API

`mothership.action_review` exports `ActionReviewError`,
`build_review_request(frozen_action, *, request_id, host_context)` and
`validate_review_response(frozen_action, expected_request, response, *, current_host_context)`.

The request has exactly `schema_version`, `request_id`, `action`,
`action_sha256`, `expires_at`, `host_context`, `request_sha256`.
The schema version is `authority-action-review-request.v0`; its digest covers
every field except `request_sha256`. Action and expiry come only from the live
Core-issued action. Output is detached JSON data.

The response has exactly `schema_version`, `request_id`, `request_sha256`,
`action_id`, `action_sha256`, `decision`. Its schema version is
`authority-action-review-response.v0`; decision is `approve` or `reject`.

Host context has exactly `host_id`, `session_id`, `actor_id`,
`runtime_generation`, `scope`. IDs, generation and request ID are strings of
1–128 ASCII characters matching `[A-Za-z0-9][A-Za-z0-9._:-]*`.
Scope is an ordered JSON list of at most 64 unique strings matching
`[a-z][a-z0-9_.:-]*`, each 1–128 characters. Preserve `[]`. The host computes its
effective scope; these names are not credentials, authentication, delegation
proof or target-specific authorization.

Validation uses the existing closed schema validator and canonical JSON
implementation. Rebuild the request from the retained live action, retained
request ID and fresh host context, and require canonical equality to the
host-retained expected request. Match every response correlation field. Then
delegate to the existing decision validator. Approve additionally requires
the frozen operation to be present in scope; reject with an unchanged empty
scope is valid. Expiry or any host-context drift rejects both decisions.
Return exactly the existing `decision`, `action_id`, `action_sha256` mapping.

Register schema kinds `authority-action-review-request` and
`authority-action-review-response`. Generic schema validation checks shape;
the API checks live issuance, expiry, canonical digests and correlation.

## Trust and lifecycle boundaries

The application retains its original expected request and original live
FrozenAction. Never accept a returned client/model request as the expected
value. Hashes are correlation, not signatures. Callers issue a fresh action ID
per freeze and fresh request ID per review. Equal bytes do not distinguish two
misissued actions with reused IDs and identical expiry: this API adds no
issuance registry or authenticated host identity. Reconstructed objects remain
invalid. The source clock stays Core-owned; tests patch the existing internal
clock, and no caller-supplied runtime clock is added.

The helpers neither record nor consume authority, perform network calls, read
credentials, maintain sessions, nor execute effects. Repeated validation is
allowed. The existing trusted live ledger enforces consumption. Review context
is not added to ledger v0 and must be retained by the application if needed as
evidence. The companion executor remains unchanged and has no host callback.
Hosts must enforce their own lease/revocation/delegation rules at the actual
effect boundary, including after suspension. A pre-execution comparison does
not close a later context-change race or undo an already-issued effect.

## Evidence and packaging

Add unit and installed-wheel tests for strict shape, detachment, canonical
binding, each context field, scope ordering/emptiness, tampered-and-rehashed
action/expiry, request mismatch, expiry and reconstructed issuance. Add a
same-process offline example using the real Core and companion, explicitly
simulated response, fake transport, separate Receipt and UNKNOWN Verification.
Show drift stops before ledger/PUT and duplicate execution produces at most
one PUT. This is not a live Dots/OpenClaw integration test.

Core becomes `0.5.0.dev0`; companion becomes `0.3.0.dev0` solely to pair its
exact Core dependency. Runtime dependencies stay empty; published `v0.4.2`
remains the historical release. Refresh both README files, contract docs,
installation/candidate notes, deterministic explanatory SVG/GIF/poster sources
and outputs. Preserve historical evidence and brand identity assets.

## Expansion map

Document Dots/plugin entry, OpenAI Agents SDK, OpenClaw exact plugin tools,
Lobster, LangGraph, MCP, UME-HARNESS, evidence export and future exact action
profiles. Reuse existing host approval and checkpoint facilities. Each proposed
adapter needs its own effect-path qualification; none becomes implemented by
listing it in a matrix. No plugin activation, configuration/auth/CI/deploy
changes, real merge, automatic retry, release tag or publication is included.
