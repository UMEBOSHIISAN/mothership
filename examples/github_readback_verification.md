# GitHub read-back verification

Run this source-checkout example with:

```sh
PYTHONPATH=.:packages/mothership-github python examples/github_readback_verification.py
```

The example injects two explicit JSON responses into
`verify_merge_pr`: one pull-request response and one Git Database commit
response. The injected opener is synthetic test provenance. It does not
authenticate GitHub, an executor, or a human, and it does not perform a live
GitHub read.

`verify_merge_pr()` requires the live Core-issued `FrozenAction` object in the
same process; persisted JSON cannot reconstruct that binding. A read-back may
run after the action's consume expiry because it does not consume or renew
authority. The caller retains the returned bundle and decides how fresh it
must be; the `transport` label is metadata and cannot authenticate the
transport on its own.

A merge timestamp before the receipt's start is `UNKNOWN` (`preexisting_merge`).
A timestamp in the same second is also `UNKNOWN` (`ambiguous_merge_time`):
second-resolution timestamps cannot exclude a merge just before the attempt.
A later timestamp still does not establish that the executor caused the merge.
An explicitly injected opener is always retained, even if it evaluates as false;
only `opener=None` selects the default network transport.

The returned bundle retains only the fixed read-back version, the exact Core
action identity, the transport label, one endpoint and UTC start/finish pair
per GET, a sanitized pull-request projection, an ordered commit-parent
projection, and a fixed reason code. The Verification's existing
`observed_state.summary` carries an allowlisted `status`, reason code, and
bounded explanation for human display. It drops titles, bodies, authors, email
addresses, headers, raw payloads, and exception text.

The verification's `observed_state.state_sha256` is the canonical SHA-256 of
the evidence `state` object. The evidence reference uses the canonical SHA-256
of the complete evidence object, including observation timestamps and reason.
The verification receipt reference
uses the canonical SHA-256 of the validated receipt. These hashes bind the
returned record; they do not make the synthetic opener an independent actor.

The producer is opt-in and read-only. It has no action authority, ledger write,
consume, retry, polling, or executor call. A live default call uses the public
tokenless GitHub origin and at most two GETs. The two GETs are a bounded
snapshot, not an atomic observation: a later PR or base-branch change outside
the requests can remain undetected. The current action profile does not bind a
base commit SHA, and the result does not prove which API or human method caused
the merge. This example makes no medical, fitness, certification, production
safety, or general GitHub reliability claim.

## Read back a persisted bundle

`verify_recorded_merge_pr(action, receipt, *, opener=None)` is the separate
caller-attested entry point for a detached plain JSON action and its bound
Receipt. It validates the action digest and Receipt identity, then reuses the
same observer. It does not reconstruct a `FrozenAction`, renew an expired
action, consume authority, call an executor, or write a ledger. The strict
`verify_merge_pr()` API above still requires the live Core-issued action.

The installed adapters expose the persisted path through one explicit command.
The input must be a complete `host-evidence-bundle.v0` with a derived Receipt
and exactly `missing == ["verification"]`; an existing Verification is
rejected before any GET. Keep the original file and retain the complete
sanitized evidence sidecar:

```sh
mothership-evidence readback < original.json > verified.json 2> readback-evidence.json
```

Use the command only when its exit status is `0`. The sidecar's canonical
SHA-256 must match `verified.json`'s `verification.evidence_refs` entry. The
command performs at most two public tokenless GETs, with no credentials,
`Authorization` header, retry, polling, authority, executor, ledger write, or
external effect. Input/setup failures use a fixed sanitized stderr diagnostic
and nonzero exit; the sidecar is emitted before stdout. Successful stderr is
data, so do not merge streams with `2>&1`; discard both files, including any
partial output, on a nonzero exit. `UNKNOWN` and `MISMATCH` observations are
still returned as valid bundles. `export`, `inspect`, `inspect --human`, and
MCP stay offline.

The Python helper
`mothership_adapters.readback.readback_evidence(bundle, *, opener=None)` returns
`{"bundle": ..., "evidence": ...}` so the caller can retain the complete
sidecar. `inspect --human` displays the escaped
caller-reported `observed_state.summary`; the summary is bounded display data,
and its reason text is not parsed into a trusted structured reason or treated
as source authentication. A recorded `CONFIRMED` result still does not prove
human identity, GitHub authentication, execution causation, merge method, or
base-commit binding.

For an offline explanation including the retained structured reason, run:

```sh
mothership-evidence inspect --human --readback-evidence readback-evidence.json < verified.json
```

This reads a bounded regular file explicitly; it rejects symlinks and nonregular
inputs. It checks the sidecar's canonical evidence hash, action ID/digest and
observed-state hash against the already-validated bundle. A mismatch stops before
human output. Matching bindings do not authenticate the source or re-evaluate the
external observation. In particular, clock rollback evidence remains a reported
`UNKNOWN`, and no branch recommends automatic retry or reconsume. Existing
`inspect --human` without a sidecar retains its prior output. See the
[adapter guide](../docs/host-adapters.md#read-only-evidence-routes) for limits and
the distinction between inspection exit status and the reported action status.
