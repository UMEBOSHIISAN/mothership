# Offline GitHub read-back verification

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
projection, and a fixed reason code. It drops titles, bodies, authors, email
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
