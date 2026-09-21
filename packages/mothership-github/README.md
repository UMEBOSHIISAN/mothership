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
The 10-minute TTL ends eligibility to consume, not necessarily the time to start
PUT. Expected base is checked at preflight only; PUT has no atomic base condition.
See [candidate limits](../../docs/option-a-candidate.md) before choosing a consumer.
