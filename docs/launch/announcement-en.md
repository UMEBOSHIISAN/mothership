# Mothership Flight Recorder launch copy

Local draft — not published.

## Short announcement

Mothership is an open-source flight recorder for AI agents.

An agent can say “done” while the evidence says its action exceeded the scope a
human approved. Mothership recomputes the verdict from an explicitly supplied,
linked record of intent, scope, decision, approval, execution, result,
verification, and persistence.

```sh
mothership demo safe   # COMPLETE, exit 0
mothership demo drift  # DRIFTED, exit 21
```

It runs locally, records no ambient state, and does not execute the agent. It
verifies supplied records; it does not grant authority or prove unobserved
real-world actions.

Explore the black box: https://github.com/UMEBOSHIISAN/mothership

## Technical thread

1. A success message is a claim, not a receipt. If we cannot connect the request
   to its approval, execution evidence, verification, and persistence, “done”
   is not a complete operational fact.

2. Mothership models one agent flight as eight required links: Intent → Scope →
   Decision → Approval binding → Execution receipt → Result evidence →
   Verification → Persistence proof.

3. The safe fixture is deliberately boring:

   ```sh
   mothership demo safe
   # verdict: COMPLETE
   # exit: 0
   ```

   Every required supplied record exists and points to the same causal chain.

4. The drift fixture contains a plausible success label, but its execution
   action class does not match the approval:

   ```sh
   mothership demo drift
   # verdict: DRIFTED
   # rule: FLIGHT.DRIFT.ACTION_CLASS
   # exit: 21
   ```

5. The boundary matters as much as the detection. Import, verify, replay, and
   report do not invoke a worker, retry failed work, repair input, discover a
   home directory, or turn a record into permission.

6. Mothership verifies what you explicitly supply. False, omitted, or
   unavailable source records remain outside its proof. A report does not grant
   authority and is not a certification of the underlying agent.
