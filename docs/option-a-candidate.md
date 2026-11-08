# Option A source candidate

This source candidate extends the earlier Option A changes on `main`; its
development versions are not a tagged release. It preserves historical v0.4.2
record reading while changing new live merge issuance to a six-field profile.
The portable review contract remains separate.
It is not a release, a migration of live grants, or evidence of real GitHub
operation. Core is `0.5.0.dev1`; the optional GitHub companion is
`0.3.0.dev1` and requires exactly this Core version. Other public, split and
consolidation version pairs are not supported by this metadata.

The [portable review API](action-review.md) binds a host's review response to
the original live action, expiry and current host context. It performs no
ledger writes or effects. The dev1 companion adds base-SHA and pre-dispatch
checks; its executor has no host callback. Optional `mothership-adapters`
`0.1.0.dev1` wraps the retained action and transport with best-effort fresh-context
checks. Eight bounded routes and their local tests are recorded in the
[integration catalog](integrations.md) and [host adapter guide](host-adapters.md).
This is not an atomic revocation fence, full-host qualification or live effect.

## What changes

Core's GitHub HTTP observation implementation lives in the companion. Importing
Core or its CLI does not import the companion or HTTP transport. The existing
`orchestration.lib.github_observation` functions remain lazy compatibility APIs;
calling them requires the matching companion. Its observation type exports also
require the companion. This is a package boundary, not runtime confinement when a
caller explicitly invokes an installed companion through the facade.

With the companion available, both CLIs expose `github-decision-card` and
`github-candidate-window`. `mothership-github observe-pr --repo owner/repo --pr 1`
is read-only and does not discover credentials. The adapter accepts an explicit
token for callers that need it; no environment token fallback is retained. Its
responses now undergo the public observation validator. Missing optional PR facts
remain null rather than being converted into false. Injected openers/transports
are trusted I/O dependencies, intended for offline testing or controlled hosts.

The companion executor accepts only a Core-issued FrozenAction, exact ledger
paths, an approval event ID and an explicit transport. Old mutable contexts,
input aliases and caller-supplied clocks are not supported. New live issuance
binds the expected base branch and base commit SHA. The executor checks both
at initial GET, consumes under Core's current clock, records a durable start,
then checks the PR again before issuing at most one mutation. After durable
start it rechecks the live action deadline immediately before PUT. Expiry or
destination drift leaves the attempt unresolved without sending PUT or retrying.
The PUT binds expected head SHA but has no atomic base branch or SHA condition.
An intervening base change can still race with PUT. Independent read-back checks
the resulting merge commit's first parent against the frozen base SHA and reports
a mismatch when observed; it does not retroactively prevent an effect. Consumers
requiring an atomic destination guarantee have an unmet adoption condition.
Historical five-field action records remain readable, but cannot be used for
new live execution.

The 10-minute TTL is checked before consume and immediately before the client
dispatches PUT. It does not prove GitHub received the request before expiry.
This candidate adds no authority renewal.

## Attempt records and unresolved outcomes

Companion `github-execution-attempt.v1` JSONL rows are a distinct local contract.
A start must reference a real consumed action in the complete strict authority
ledger; a finish must match an existing start and cannot repeat it. Both ledgers
require normalized absolute paths, real immediate parent directories mode0700,
regular no-follow files mode0600, and distinct file identities. These checks do
not authenticate the human, protect every ancestor path, or authenticate writes
made by the same trusted OS user.

A success observation requires HTTP200, exact `merged=true` and a lowercase
40-hex merge commit SHA without ambiguity. Empty/malformed/contradictory results,
5xx, timeouts and unknown exceptions remain `reconciliation_required`. No raw
response/exception/header/token text is stored in attempt rows. These executor
reports are not independent verification of external reality. `success` means
the executor observed those response facts, not that a separate verifier proved
the merge or its destination.

The REST transport inspects a bounded strict JSON object on normal responses and
HTTPError responses, including rejections. Contradictory merge facts survive to
the normalizer. Empty, unreadable, oversized or malformed rejection bodies stay
unresolved. A recognized rejection with a valid non-contradictory object may be
`failure`; it does not establish `merged=false`. An unobserved merge fact is
`null`, and HTTP status `0` means no valid response status was observed (not a
synthetic HTTP599). Redirects remain blocked, with no follow-up request.

Receipt validation rejects `failure` carrying positive merge facts (`merged=true`
or a merge SHA), as well as `success` lacking strong facts. It deliberately accepts
`reconciliation_required` with apparent success facts: other detected ambiguity
may require reconciliation. It does not independently reclassify remote reality.
Old contradictory failure rows now fail validation; they are not silently rewritten
or upgraded into success.

Authority can be consumed before a failed start append: then no PUT occurs, no
success is returned, and authority stays consumed. A crash after start but before
PUT cannot be distinguished from an unresolved attempt by these records alone.
A failed finish after PUT also leaves the outcome unresolved. None of these
states retries, reconsumes, unconsumes or automatically repairs authority.

Public `external-action-receipt.v0`, Verification, and their binding validator
are unchanged. The optional [pure receipt adapter](../examples/github_receipt_adapter.md)
now converts validated terminal attempt pairs with caller-supplied expected
identities. The companion also exposes an explicit `verify_merge_pr()`
read-back producer. It uses the exact Core-issued action and validated Receipt,
then performs at most two public tokenless GETs and retains sanitized PR and
Git Database commit projections. It preserves uncertainty, keeps Receipt and
Verification status independent, and grants no authority. The caller retains
the canonical source records; the adapters do not authenticate evidence or
restore `reconcile_merge_state`. The legacy invocation ledger is also separate.
One-shot protection remains per trusted, non-restored authority history;
copying/rolling back histories can defeat it. Receipt paths are not a global
deduplication service.

## Cutover limits

Preserve old split/consolidation data unchanged. Do not translate unused grants
into usable public-Core grants, reissue them automatically, or extend expiry.
Unknown/unresolved external results stay unknown/unresolved. The future operator
must identify concrete consumers and decide how to retire unused authority and
resolve old attempts before any real cutover. This candidate has no such authority
and makes no claim that unidentified consumers do not exist.

Automated repository tests and included offline examples use fake transport
responses and local files. They do not require live credentials, mutation, or
publication. A separate bounded tokenless public read-back may provide
observational evidence, but it is not a live executor or canary test and does
not publish a release. The read-back example's injected opener is synthetic
provenance and does not authenticate an independent actor. Existing public
baseline evidence remains scoped to its original revision and operation.

## Offline source checks

Run the Core tests without the companion to exercise the optional-dependency
boundary. Observation-specific tests explicitly skip when the companion is absent.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

For the integration suite, put `packages/mothership-github` on `PYTHONPATH` along
with the repository root and run the Core and companion roots in separate
processes:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:packages/mothership-github \
  python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:packages/mothership-github \
  python3 -m unittest discover -s packages/mothership-github/tests -v
```

The companion CI job adds guards that fail on zero discovered tests or any
skipped test; the Core-only job intentionally preserves its optional-companion
skips. No transport test needs live credentials or network access. A plain
source archive has no Git index, so Git-tracked inventory tests require
separate manifest checks.
Build/install tests need pre-existing build tools and must not download implicitly.
