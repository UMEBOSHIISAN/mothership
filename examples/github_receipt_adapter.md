# GitHub attempt to Core receipt adapter

The optional companion provides an explicit, pure conversion from its closed
`github-execution-attempt.v1` start/finish pair to Core's
`external-action-receipt.v0`. It does not change the executor's result or run
automatically. Core remains independent of the companion.

From a source checkout with Python >=3.12, run:

```sh
PYTHONPATH=.:packages/mothership-github python examples/github_receipt_adapter.py
```

Expected output:

```text
SYNTHETIC ONLY
binding: accepted
mismatch: rejected
receipt status: UNKNOWN
```

The example uses synthetic records and synthetic UNKNOWN verification. It
demonstrates exact binding and rejection, not real execution or independent
external observation. It does not use credentials, an authority ledger,
network, models or a service. Core validation reads bundled schema resources.
The example itself is source-checkout only; the converter is in the companion
package. The existing exact Core dependency pin is unchanged.

## Integrator call

```python
from mothership_github.external_action import build_external_action_receipt

receipt = build_external_action_receipt(
    started, finished,
    expected_action_id=trusted_action_id,
    expected_action_sha256=trusted_action_digest,
    expected_consume_event_id=trusted_consume_event_id,
    executor_ref=executor_reference,
)
```

`started` and `finished` are plain JSON dictionaries, for example the
`attempt_started` and `attempt_finished` rows returned by the existing executor.
The expected identities must come from trusted caller context. Copying the
values from untrusted rows merely checks those rows against themselves. The
comparison is caller-attested; the converter does not authenticate the caller,
executor or source records, and cannot prove durable authority consumption.

The adapter checks the closed row types, event linkage, identity, timestamps
and outcome facts. Invalid records or references raise `ContractError` with
fixed text. It returns an isolated copy of the validated receipt.

| Input outcome | Projected status |
| --- | --- |
| Strong normalized `success` | `SUCCESS` (executor-local only) |
| `failure` with a recognized client failure, such as HTTP409 | `FAILED` |
| Other valid `failure` observations, including 0, 5xx, 3xx | `UNKNOWN` |
| Explicit `reconciliation_required`, even with positive facts | `UNKNOWN` |
| Missing finish or invalid/inconsistent closed records | Reject; no receipt |

The original receipt does not retain the transport's `redirect_rejected` flag.
Consequently a failure-labelled 3xx projects to UNKNOWN, without altering the
original source row. A failure classification does not prove an unmerged PR.
An absent finish does not justify inventing a completion timestamp or retrying.

## Evidence retention and later verification

The observation reference is `github-attempt:<start event ID>` and its digest is
`canonical_json_sha256({"started": started, "finished": finished})` after
validation. Retain that exact source pair under your evidence store's access
and retention policy. The converter neither persists nor resolves evidence.
A digest does not supply authenticity, access rights or a storage guarantee.
JSON key order is irrelevant; changing the retained facts changes the digest.

A separate verifier can bind its observation through the existing
`mothership.contracts.validate_receipt_verification_binding` helper, using
`receipt:<action ID>` and the canonical digest of the projected receipt.
Binding does not upgrade either status and supplies no new authority. A
SUCCESS receipt is never a substitute for independent verification.

Other products can follow this pattern: own their operation-specific adapter,
reuse Core's public validators, preserve source evidence and keep execution
separate. This converter supports only the existing GitHub attempt version;
it does not add executable profiles, runtime lease checks, remote authority
transport, retries, or arbitrary data-store actions.
