# Changelog

## Unreleased

## 0.3.0 - 2026-08-28

- Extended the CI matrix to Python 3.14 and kept the broken-pipe CLI regression
  test compatible with argparse's newer output-stream probing.
- Added the Decision Card / Decision Approval contracts (`evidence/contracts/decision-card.v0.schema.json`,
  `evidence/contracts/decision-approval.v0.schema.json`) and `validate_decision_approval_binding()`, exported from
  `mothership.contracts`. A Decision Approval binds to exactly one Decision Card by canonical-JSON SHA-256 digest and
  `decision_id`; both schemas fix `authority_effect: false` and `execution_effect: false`. This is a distinct primitive
  from the existing `decision` (frontdoor routing recommendation) and `approval-event` (invocation/execution-side
  evidence) schemas. Library-level only; no CLI subcommand yet.
- Added the current Action Authority core through `mothership.action_authority`: core-issued `FrozenAction`, canonical
  action digest, fixed ten-minute TTL, exact action ID/hash decision transport, and the closed `github.merge_pr`
  operation profile. Human display fields are derived from validated execution parameters. The action digest excludes
  expiry, so callers must use a fresh action ID and correlate responses to the exact live issuance.
- Added the dedicated authority-action approval/consume contracts and locked ledger. Caller-attested approve/reject
  decisions bind to one exact action; event writes are file-fsynced, and replay rejection holds within one trusted,
  non-rollbackable live ledger history. Human identity, monotonic ledger history, and crash durability of a new ledger
  directory entry remain integration responsibilities.
- Recorded an operator-observed physical `github.merge_pr` event through a separately bounded executor path. The prose
  record is not independently reproducible; the default CLI does not ship a general consequential executor or GitHub
  mutation command.
- Reclassified Frontdoor/WGM/Router/Secretary as the preserved 0.2 protocol compatibility surface and the earlier
  routing, safety, registry, and invocation ledger as legacy compatibility. No protocol bytes or compatibility APIs
  changed.

## 0.2.1 - 2026-08-11

- Restored the public architecture diagrams and added deliberate, read-only
  diagnostic guidance.
- Added public issue forms and a Code of Conduct.
- Clarified the ecosystem constellation and kept the demo explicitly free of
  authority and execution effects.
- Hardened the public-package scan so staged checks do not traverse `.git`.
- Expanded CI coverage to every push and corrected the workflow syntax.

## 0.2.0 - 2026-08-09

- Made Mothership an installable integration hub while keeping Agent Frontdoor,
  Workflow Governance Model, Mothership Router, and Secretary TUI independently
  adoptable.
- Added an immutable registry and offline validation for four versioned ecosystem
  protocols, plus a deterministic `protocol-composition-only` demo.
- Added public Python APIs and a read-only CLI for resource verification,
  protocol inspection, validation, deliberate diagnostics, and the synthetic demo.
- Rebuilt the English and Japanese product guides with tested installation,
  architecture, lifecycle, compatibility, contribution, and security guidance.
- Added reproducible synthetic conformance measurements and exact claim boundaries.
- Preserved the closed safety boundary: validation grants no authority, executes no
  work, installs no companion, reads no credentials, and starts no background service.

## 0.1.2 - 2026-08-08

- Linked the released Workflow Governance Model as an optional governance layer.
- Clarified that its candidate recommendation remains advisory and non-executing.

## 0.1.1 - 2026-08-08

- Added composition guidance and the planned governance roadmap. Companion
  repositories are independent.
- Added clone-verifiable checksums for the final tracked release tree.
- No runtime integration, automatic setup, or authority was added.

## 0.1.0

- Initial local distribution candidate with staged contracts, local validation,
  and diagnostic-only command surfaces.
