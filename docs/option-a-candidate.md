# Option A local candidate

This source candidate preserves the published v0.4.2 Authority Core and its closed
contracts. It is not a release, a migration of live grants, or evidence of real
GitHub operation. Core is `0.4.3.dev0`; the optional GitHub companion is
`0.2.0.dev0` and requires exactly this Core version. Other public, split and
consolidation version pairs are not supported by this metadata.

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
input aliases and caller-supplied clocks are not supported. The executor validates
before preflight, consumes under Core's current clock, records a durable start,
and issues at most one mutation using the action returned by consume. The local
FrozenAction binds the expected base branch name; preflight checks that name at
GET time. The PUT binds expected head SHA but sends no base branch or base SHA
condition. A PR retargeted between GET and PUT is therefore not atomically
rejected by this client. Additional GETs would only narrow that window. Consumers
requiring an atomic destination guarantee must treat it as an unmet adoption
condition. Base commit SHA is not bound either.

The 10-minute TTL is a consume deadline, checked using Core's current clock.
It is not a guarantee that PUT starts before expiry: recording the start can
wait after consume. This candidate adds no send deadline or authority renewal.

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
are unchanged. The companion does not manufacture these independent verification
records or restore `reconcile_merge_state`. The legacy invocation ledger is
also separate. One-shot protection remains per trusted, non-restored authority
history; copying/rolling back histories can defeat it. Receipt paths are not a
global deduplication service.

## Cutover limits

Preserve old split/consolidation data unchanged. Do not translate unused grants
into usable public-Core grants, reissue them automatically, or extend expiry.
Unknown/unresolved external results stay unknown/unresolved. The future operator
must identify concrete consumers and decide how to retire unused authority and
resolve old attempts before any real cutover. This candidate has no such authority
and makes no claim that unidentified consumers do not exist.

All validation evidence for this candidate uses fake transport responses and
local files. No live credentials, network tests, GitHub operations or publication
are required or demonstrated. Existing public baseline evidence remains scoped
to its original revision and operation.

## Offline source checks

Run the Core tests without the companion to exercise the optional-dependency
boundary. Observation-specific tests explicitly skip when the companion is absent.
For the integration suite, put `packages/mothership-github` on `PYTHONPATH` along
with the repository root; those same observation tests must all run and pass.
No transport test needs live credentials or network access. A plain source archive
has no Git index, so Git-tracked inventory tests require separate manifest checks.
Build/install tests need pre-existing build tools and must not download implicitly.
