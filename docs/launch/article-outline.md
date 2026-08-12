# The black box for AI agents — article outline

Local draft — not published. Every factual claim below must resolve to a local
artifact or executable command before publication.

## Why AI agents need a flight recorder

- Open with the operational gap: agents emit messages, while operators need a
  causal record.
- Define “flight” using the eight stages in
  [`README.md`](../../README.md) and the frozen contract in
  [`docs/protocols.md`](../protocols.md).
- Explain why metadata-only, explicit input is a privacy boundary.

## A success message is not evidence

- Walk through [`assets/flight-incident.svg`](../../assets/flight-incident.svg).
- Separate declared success, observed records, and the recomputed verdict.
- Use `FLIGHT.DRIFT.ACTION_CLASS` as a measured example, not a universal claim.

## Authority as data

- Show Intent → Scope → Decision → Approval binding before execution evidence.
- Explain identity, digest, and causal linkage using
  [`docs/architecture.md`](../architecture.md).
- State the core invariant: a valid record describes authority; it does not
  create authority.

## Safe flight

- Run `mothership demo safe` and show the exact checked-in bytes from
  [`docs/generated/flight-safe-output.json`](../generated/flight-safe-output.json).
- Explain why `COMPLETE` is scoped to the supplied chain.
- Link the generated safe report and its disclaimer.

## Drifted flight

- Run `mothership demo drift` and show the exact checked-in bytes from
  [`docs/generated/flight-drift-output.json`](../generated/flight-drift-output.json).
- Explain exit 21 and the approval/execution action-class mismatch.
- Contrast drift with `INCOMPLETE` and `INVALID` without collapsing verdicts.

## What Mothership does not do

- Does not launch, schedule, route, repair, retry, deploy, or grant permission.
- Does not collect ambient prompts, credentials, environment dumps, or home
  directories.
- Cannot prove omitted, false, or unobserved source events.
- Close with the independently adoptable constellation shown in
  [`assets/constellation.svg`](../../assets/constellation.svg).
