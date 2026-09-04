# Mothership public truth closure plan — 2026-09-04

## Goal

Make the public onboarding path describe and exercise the current v0.4.1
Authority Core without changing runtime authority semantics or rewriting the
historical v0.4.1 release.

## Scope

1. Add a local, non-mutating Authority Core walkthrough covering freeze,
   derived display, human decision recording, one consume, and replay
   rejection.
2. Add a subprocess regression test proving the walkthrough is offline,
   credential-free, and does not invoke an executor or external mutation.
3. Make the README quick start lead with the walkthrough; keep
   `mothership demo` explicitly labeled as the legacy 0.2 compatibility demo.
4. State that the current main documentation is unreleased follow-up to the
   historical v0.4.1 release and record PR #21 under the next docs-only
   release candidate in the changelog.
5. Keep the responsibility bridge and all current claim ceilings explicit.

## Out of scope

- No new operation profile, executor, verifier producer, bridge, or CLI
  authority command.
- No changes to Authority Core or ledger contracts.
- No tag, push, GitHub Release edit, or remote settings change.

## Verification

- Python 3.12 full unittest suite.
- Walkthrough subprocess test in a temporary directory.
- README/link/asset and checksum checks.
- Local light/dark/mobile render review; no public GitHub state is claimed.
