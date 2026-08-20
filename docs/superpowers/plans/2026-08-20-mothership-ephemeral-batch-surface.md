# Mothership Ephemeral Decision Batch Surface

**Goal:** Aggregate multiple existing Decision Discovery outcomes in memory
for human inspection without adding a queue, persistence, lifecycle, or new
protocol.

**Existing surface audit:** Mothership currently exposes read-only JSON CLI
commands for verification, protocol inspection, and the synthetic demo. None
accepts Decision Discovery inputs. Secretary/TUI is not a semantic owner for
Decision Cards. The smallest safe surface is therefore a pure Mothership
composition plus deterministic formatter, exposed through the existing
contracts facade; no CLI, TUI, schema, or protocol change is needed.

## Frozen constraints

- Preserve input order within each outcome class.
- Keep `DECISION_CARD`, `NO_CARD`, and `FAIL_CLOSED` separate.
- Do not merge, deduplicate, prioritize, persist, dismiss, expire, retry,
  schedule, approve, or execute.
- Preserve the original task identity and provenance.
- Router recommendation provenance is presentation metadata only.
- Existing single-input `build_decision_card()` behavior remains unchanged.

## Scope

- Modify: `orchestration/lib/decision.py`
- Modify: `mothership/contracts.py`
- Modify: `tests/test_decision_discovery.py`
- Modify: `tests/test_public_facades.py`
- This plan artifact

## Verification

- RED tests before implementation.
- Batch containing Card, no-Card, and fail-closed outcomes.
- Router-present and Router-absent Cards.
- Exact UNKNOWN preservation.
- Near-duplicate Cards remain distinct.
- Deterministic human-readable rendering.
- No persistence or authority/execution effect.
- Focused tests, related regressions, and diff review.
