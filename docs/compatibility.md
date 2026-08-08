# Compatibility

Mothership is the **installable hub**; its companion repositories remain **independently adoptable**. This page records
measured and declared surfaces separately.

## Measured, not universal

The Wave 1 release candidate was measured on macOS with Python 3.14.6, build 1.5.0, and setuptools 83.0.0. The wheel,
source distribution, clean and editable installs, CLI parity, compatibility APIs, and the 182-test Wave 1 suite passed
in that environment. Later product-document and evaluation tests are recorded in their own evidence.

This is not a claim that every supported Python or POSIX combination has been exercised.

## Python and operating-system assumptions

- Declared Python support: **Python 3.12+**.
- Runtime requirements: none outside the standard library.
- Strict file boundaries require POSIX descriptor operations, no-follow flags, regular-file checks, and file locking.
- Windows is not currently claimed as supported by the complete path and ledger boundary.
- Linux is expected to provide the required primitives but needs an attended replication record before a support claim.

## Entry-point compatibility

The `mothership` console script and `python -m mothership` are byte-equivalent for read-only commands. Existing
`frontdoor`, `safety`, `orchestration`, and `evidence` package paths remain included for legacy compatibility in 0.2.0.

## Diagnostic compatibility

| Alias | Fixed surface | Network note |
| --- | --- | --- |
| `claude-code-agent` | version and help probes | no Mothership-directed network target |
| `codex-cli` | version and help probes | no Mothership-directed network target |
| `ollama-local` | version, help, and list probes | list may query default loopback daemon |

Availability is observational. It is not execution permission or a promise that every CLI version behaves identically.

## Protocol compatibility in 0.2.0

| Kind | Version | `authority_effect` | `execution_effect` |
| --- | --- | --- | --- |
| `frontdoor-task` | `intake.v0` | not capable | not capable |
| `governance-handoff` | `1.0` | not capable | not capable |
| `router-manifest` | `1.0` | false | false |
| `observation-snapshot` | `1.0` | false | false |

The four-stage `protocol-composition-only` demo is the installed compatibility smoke test. Mothership freezes owner
snapshots; it does not auto-upgrade them.

## Evidence

- [Wave 1 verification](verification/2026-08-09-hub-wave1.md)
- [Machine-readable evaluation](../evaluation/results/mothership-0.2.0.json)
- [Paper evidence and limits](research/paper-evidence.md)
