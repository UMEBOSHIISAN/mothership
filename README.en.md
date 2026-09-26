# Mothership

> Unreleased public source-main candidate (Core 0.4.3.dev0 plus optional companion 0.2.0.dev0).
> It is not a release or live-operation proof. See [candidate changes and limits](docs/option-a-candidate.md).

[日本語](README.md) · [v0.4.2](https://github.com/UMEBOSHIISAN/mothership/releases/tag/v0.4.2) ·
[CI](https://github.com/UMEBOSHIISAN/mothership/actions)

<p align="center">
  <img src="assets/mothership-banner.png" alt="Linocut-style Mothership whale swimming through ocean currents" width="100%">
</p>

Published v0.4.2 was a docs-only release. Public source main retains its
documentation, imagery, and Authority Core contracts, and adds the unreleased
Option A implementation.

> Keep control of your work, even as the AI you use changes.
>
> Humans should not have to do everything.
> Nor should they hand everything over to AI.

Mothership is an open-source core implementation for sharing work between humans
and AI. It freezes the operation to be entrusted in advance and binds it to a
human decision.
It treats decisions, authority use, execution reports, and independent result
verification as separate records.

With GitHub PR merging as its first reference example, the current implementation
provides operation freezing, decision matching, and one-time authority consumption
within the same trusted local ledger history.

It is not an AI chat app or a complete business system. Model execution, human
identity authentication, business-system connections, and the processes that
execute actions and verify results must be configured separately.
It does provide explicitly invoked, read-only GitHub observation commands.

## PURPOSE

Sharing work between humans and AI requires separating what a system can do
from what it may do. Mothership exists to make that handoff explicit so a
human can entrust concrete work without surrendering all control.

| Distinction | Meaning |
| --- | --- |
| Capability | what an AI or tool can do |
| Authority | which part it may do |
| Decision | what a human chose to entrust this time |
| Execution | what operation actually occurred |

Security is not the product category. It is a condition for keeping those
responsibilities distinct.

## Responsibility split

UME-HARNESS turns human intent into a bounded local-work preview.
Mothership binds a human decision to bounded authority for one external action.

<p align="center">
  <img src="assets/readme/en/ume-stack-responsibility.svg"
       alt="Responsibility map in which UME-HARNESS bounds local work and Mothership handles consequential authority across an unimplemented dashed bridge."
       width="760">
</p>

This diagram shows a responsibility direction. The current public releases have no automatic runtime bridge. The dashed connection is not implemented.
The external executor and verifier are separately configured too.

## CURRENT: v0.4.2

Published v0.4.2, the historical public baseline, freezes one supported external operation, checks a
caller-attested human decision, records it in a local ledger, and permits one
consume.

Implemented:

- validation and freezing of supported parameters into a `FrozenAction`
- approve/reject checks against the action ID and digest
- local recording of decision events
- one consume in the same trusted local ledger history
- closed contracts that separate an executor Receipt from Verification

Not shipped:

- an automatic UME-HARNESS runtime bridge
- a general executor, verifier producer, credential manager, retry, or daemon
- human identity authentication
- arbitrary operation profiles or autonomous execution

Proposal and evidence are decision context, but they are not mechanically bound to a FrozenAction in v0.4.1.
Mothership receives the supported execution parameters separately and freezes them first.
Human identity is not authenticated.

### Current source main: Core 0.4.3.dev0 + companion 0.2.0.dev0

Public source main contains unreleased Core `0.4.3.dev0`, which preserves the
v0.4.2 boundary, plus an optional GitHub companion `0.2.0.dev0` that requires
that exact Core version.

Core validates the exact `github.merge_pr` parameters, freezes a `FrozenAction`,
checks a caller-attested decision, and permits one consume in a trusted live
ledger. Core does not execute the external operation and does not ship an
executor or independent verifier producer.

The opt-in GitHub companion accepts only a Core-issued `FrozenAction`, exact
ledger paths, an approval event ID, and an explicit transport. After a
read-only preflight it uses Core's consume result to record an attempt and
allows at most one PUT. Recognized client failures project to `failure`; other
failures, timeouts, and contradictory responses remain
`reconciliation_required`. A missing or invalid attempt pair is rejected; there
is no retry or reconsume. Its `github-execution-attempt.v1` rows are distinct
from Core Receipt and Verification records.

The opt-in [receipt adapter](examples/github_receipt_adapter.md) projects a
validated terminal attempt pair into Core's `external-action-receipt.v0`.
It checks the caller-supplied `action_id`, `action_sha256`, and
`consume_event_id` exactly, then uses `github-attempt:<start event ID>` and
`canonical_json_sha256({"started": started, "finished": finished})` as the
observation reference. For a valid terminal pair, strong success projects to
`SUCCESS`, recognized client failure to `FAILED`, and other failure or
`reconciliation_required` to `UNKNOWN`. Missing, ambiguous, or unobserved facts
are never filled into `SUCCESS`; a missing finish or inconsistent closed pair is
rejected. The adapter grants no authority, does not authenticate or store the
records, and does not produce an independent verifier record.

Core and companion remain separate packages; adapter use is opt-in, and there
is no automatic cross-repository runtime bridge. See the [composition guide](docs/composition.md)
for responsibility and connection conditions. Run the offline synthetic example from the source checkout root with
`PYTHONPATH=.:packages/mothership-github python examples/github_receipt_adapter.py`.
Its output demonstrates synthetic binding only; it performs no GitHub
operation, credential use, ledger consume, or independent external observation.

## How the current Mothership Core works

<p align="center">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="assets/readme/en/mothership-flow-poster.png">
    <source media="(max-width: 600px)" srcset="assets/readme/en/mothership-flow-poster.png">
    <img src="assets/readme/en/mothership-flow.gif"
         alt="Proposal and evidence remain unbound decision context; Mothership freezes caller-supplied exact execution fields and binds a human decision to one use."
         width="100%">
  </picture>
</p>

This is an explanatory diagram, not execution evidence.
Reduced-motion settings and screens up to 600px use the equivalent vertical static poster.

Supported parameters are frozen before a caller-attested decision is checked
against the action ID and digest and recorded. The same action ID can be
consumed once within one trusted local ledger history.

### Consuming authority is not completing the work

<p align="center">
  <img src="assets/readme/en/record-boundaries.svg"
       alt="Three separate cards for authority consumption, executor report, and independent result check; no automatic integration is shown." width="840">
</p>

Mothership validates execution reports and independent verification as separate records. The executor and verifier processes are configured separately.

## Current reference profile

The first current reference profile is `github.merge_pr`.
It is not the identity or full intended use of Mothership. It is the first
concrete example that closes the five execution parameters, decision check,
ledger record, and one-use consume boundary.

The current profile fixes:

- repository
- pull request number
- expected head SHA
- expected base branch name
- merge method

The base commit SHA is not bound. `expires_at` is not included in the action digest.
Integrations must issue a fresh `action_id` for every freeze. They must correlate the response to the exact live issuance and displayed expiry,
and reject delayed or reused responses.

## One public result

The [bounded public result for PR #18](docs/evidence/github-merge-pr-e2e-20260903/README.md)
records one `github.merge_pr` against an isolated canary base. Public GitHub
read-back shows the target head SHA, merge commit, parents, and bounded diff size.

<p align="center">
  <img src="assets/readme/en/pr18-public-result.svg"
       alt="Public result for merging PR 18 into an isolated canary branch, showing the source commit, merge commit, one file with five added lines, and that public main was not targeted."
       width="720">
</p>

This is one public result for PR #18. It does not claim that the private
lifecycle is reproducible from public material, generic safety, or production suitability.

**Changes in v0.4.2**

The README image-generation dependency changes from Pillow 11.3.0 to 12.3.0.
The Japanese and English GIFs and static posters are regenerated, with matching
`SHA256SUMS` entries. Diagram meaning, Authority Core behavior, and authority
boundaries are unchanged. Pillow is needed only for image generation and is not
added as a Mothership runtime dependency. An offline Authority Core walkthrough
(below) is added. Runtime Authority Core behavior, approval-acceptance
conditions, and the supported operation profile are unchanged from v0.4.1.

## Quick start

Use Python 3.12 or newer and a source checkout of this repository.
Follow the [clone instructions](docs/installation.md#clone-first-install), then run
these commands from the repository root. The walkthrough was added after v0.4.1;
it is not included in the v0.4.1 tag or wheel, and it is not included in the
v0.4.2 wheel either (it is a source-checkout-only example).

<!-- quickstart:start -->
```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python examples/authority_core_walkthrough.py
mothership verify
```
<!-- quickstart:end -->

`python examples/authority_core_walkthrough.py` runs without network access or credentials. It shows exact action freeze,
derived display, a synthetic approval fixture, one consume, and rejection of a second consume. It is not a human approval
ceremony or identity-authentication flow; it does not change GitHub or start an executor or verifier.

`mothership verify` checks bundled resource inventory, schemas, registry,
fixtures, and digests offline. It does not check the host, external safety,
or every installed byte.

`mothership demo` is the legacy 0.2 synthetic protocol-composition demo.
It is not Authority Core proof, agent execution, human approval, or evidence
that a real task completed. It is not the current Authority Core onboarding path.

## Current limitations

| Area | Implemented in v0.4.2 | Not implemented or certified |
| --- | --- | --- |
| identity | caller-attested decisions | human identity authentication |
| decision events | Multiple decision events may be recorded for the same action | one terminal decision, supersession, or revocation |
| consume | one consume per action ID in one trusted ledger history | global replay prevention across copied or restored ledgers |
| action scope | five exact `github.merge_pr` parameters | base-commit binding or arbitrary operations |
| expiry | a short TTL that is shown and checked | binding `expires_at` into the action digest |
| execution | data returned for a separate executor | a live executor, credentials, retries, or a daemon |
| verification | shape and binding checks for Receipt and Verification | verifier-producer identity or read-only behavior |
| package check | bundled inventory and digest checks | host, all installed code, or external safety |
| public result | one bounded PR #18 result | generic safety, production readiness, or private-trace reproducibility |

This reference implementation is not certified for production or regulated
high-stakes deployment. One-use enforcement is scoped to one trusted local
ledger history.

## Documentation

### Code tour

- [`orchestration/lib/action_authority.py`](orchestration/lib/action_authority.py) — action freeze and decision transport
- [ledger implementation](orchestration/lib/action_authority_ledger.py) — append and one-shot consume
- [external-action contracts](orchestration/lib/external_action.py) — Receipt and Verification records
- [`tests/test_action_authority.py`](tests/test_action_authority.py) — Authority Core boundary tests
- [ledger tests](tests/test_action_authority_ledger.py) — replay and ledger-history tests
- [external-action tests](tests/test_external_action_contracts.py) — external-action contract tests

### Origin and compatibility

This boundary carries lessons from incidents where the reviewed target changed
before execution and where an unchecked tool failure was summarized as success.
Labels are not evidence; unknown results stop.

Frontdoor, WGM, Router, and Secretary protocols remain for legacy 0.2
compatibility and history. They are not the current Authority Core path.

### References

- [Architecture](docs/architecture.md)
- [Installation](docs/installation.md)
- [Protocols](docs/protocols.md)
- [Security model](docs/security.md)
- [Composition guide](docs/composition.md)
- [0.2 compatibility history](docs/legacy/compatibility-0.2.md)
- [日本語README](README.md)

## License

The project code is MIT; see [LICENSE](LICENSE). The bundled Noto Sans JP font
used to generate README assets remains under the
[SIL Open Font License 1.1](assets/readme/source/fonts/OFL-1.1.txt).
