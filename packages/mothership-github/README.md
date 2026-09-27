# Mothership GitHub companion — local candidate

Version0.2.0.dev0 requires Core0.4.3.dev0 exactly. This is an isolated integration
candidate, not a published package or live-operation proof.

HTTP observation and bounded merge execution live here; Core owns the closed
FrozenAction and authority ledger. All credentials are explicit constructor
inputs. No environment credential discovery, retry or daemon is provided.

`mothership-github` supports `observe-pr`, `github-decision-card` and
`github-candidate-window`. The latter two preserve the Core observation CLI
arguments. The merge executor is a Python API requiring a Core-issued action,
authority/receipt ledger paths, an approval event ID and an explicit transport;
there is no mutation CLI.

Attempt rows use `github-execution-attempt.v1` and are distinct from the public
external receipt/Verification contracts. Unclear mutation results and receipt
write failures do not create replay authority. See the root candidate document
for failure windows, ledger trust assumptions and cutover constraints.

Unknown mutation facts remain null; a failure classification does not prove an
unmerged PR. Rejection bodies are bounded and checked on both normal and
HTTPError paths. Unreadable or contradictory responses require reconciliation.
Receipt success is an executor observation, not independent verification.
An opt-in [receipt adapter](../../examples/github_receipt_adapter.md) projects
validated attempt pairs into Core's existing external-action receipt contract.
It preserves uncertainty and does not establish durable consume or executor
authenticity. The offline example demonstrates binding with synthetic records;
the executor does not invoke the adapter automatically.

The opt-in `verify_merge_pr()` producer performs an independent bounded read-back
for a Core-issued `FrozenAction` and a validated Receipt. It uses at most two
public tokenless GETs: the pull request and its Git Database merge commit. It
retains only sanitized projections, UTC request boundaries, fixed reason codes,
and canonical evidence references. Invalid or contradictory observations stay
`UNKNOWN`; a valid but wrong head, base, or merge topology is `MISMATCH`.
`SUCCESS` on the Receipt never selects the Verification status. The producer
does not consume authority, write a ledger, invoke an executor, retry, poll, or
prove the API or human method that caused a merge. See the [offline read-back
example](../../examples/github_readback_verification.md).

An injected opener is explicit synthetic/host-attested provenance for offline
use. The default path does not discover credentials and sends no Authorization
header. A two-request read-back is a bounded snapshot rather than an atomic
external observation; the current action profile also leaves base commit SHA
binding outside the producer.
The verifier requires the live Core-issued `FrozenAction` in the same process;
persisted JSON cannot reconstruct its binding. Read-back remains available
after consume expiry because it does not consume or renew authority. The caller
retains the bundle and judges freshness; the `transport` label is metadata and
cannot authenticate transport by itself.
The 10-minute TTL ends eligibility to consume, not necessarily the time to start
PUT. Expected base is checked at preflight only; PUT has no atomic base condition.
See [candidate limits](../../docs/option-a-candidate.md) before choosing a consumer.
