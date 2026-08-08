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

## Exact companion conformance audit

The development audit passed against the following exact local commits. Every row is **local-only / publication
pending**: the commit was tested in an isolated worktree but is not yet claimed reachable from a public tag or remote
branch.

| Repository | Owner version | Protocol | Tested commit | Schema SHA-256 | Result |
| --- | --- | --- | --- | --- | --- |
| `agent-frontdoor` | `0.1.0` | `frontdoor-task` `intake.v0` | `296c49be801b6573abf54daa81b828df95e8e84f` | `6d6ed4aea9d3f5612c5292a2f46c72634776dc27998b61cdcdbdba3f35e7ca7e` | passed; local-only / publication pending |
| `workflow-governance-model` | `0.2.1` | `governance-handoff` `1.0` | `b31784d9b2d81c770d1b71d241dcb80bbb8bab17` | `e59784d4da3368e97fcf7dd104d713169057bbad59047ad9d61f4bba572305d0` | passed; local-only / publication pending |
| `mothership-router` | `0.3.0` | `router-manifest` `1.0` | `b740a24f664adca2bdf8144fb99053bd2d3daf64` | `2f1c244ca62ef68d2bcb5ea8531002991be812c5d7b31e101990500d5df8ffa5` | passed; local-only / publication pending |
| `secretary-tui` | `1.2.0` | `observation-snapshot` `1.0` | `95b5af84ab3485097d96739f2ed17f63427acf50` | `f86e5ec5ccd407752557e9930def9ab8096449d330df1b2707e1d11ef41b4a3a` | passed; local-only / publication pending |

The report verified four owner manifests, four schema digests, byte identity with all four bundled schemas, four public
examples, the Secretary copy of the Router input, shared task ID/capability/status fields, and false authority/execution
effects. This is conformance evidence for those commits, not a claim about newer commits or remote publication.

## Evidence

- [Wave 1 verification](verification/2026-08-09-hub-wave1.md)
- [Machine-readable evaluation](../evaluation/results/mothership-0.2.0.json)
- [Paper evidence and limits](research/paper-evidence.md)
