# Compatibility

**Status: 0.2 compatibility surface; preserved for interoperability and history. Not the current three-product
architecture.**

The companion repositories remain independently adoptable. This page preserves exact measured commits, schema hashes,
and declared compatibility surfaces without treating the old constellation as the current Mothership architecture.

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
`frontdoor`, `safety`, `orchestration`, and `evidence` package paths remain included for legacy compatibility in 0.4.0.

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
| `governance-handoff` | `1.1` | not capable | not capable |
| `router-manifest` | `1.0` | false | false |
| `observation-snapshot` | `1.0` | false | false |

The four-stage `protocol-composition-only` demo is the installed compatibility smoke test. Mothership freezes owner
snapshots; it does not auto-upgrade them.

## Exact companion conformance audit

The development audit passed against the following exact commits. Each tested commit is reachable from its repository's public `main` branch through the measured conformance merge commit below.

| Repository | Owner version | Protocol | Tested commit | Conformance merge commit | Schema SHA-256 | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `agent-frontdoor` | `0.1.0` | `frontdoor-task` `intake.v0` | `4bcfcb6c1868a87076502999a38127e28e275e70` | `c76a516477241eef7509855ebf22af0821168df3` | `6d6ed4aea9d3f5612c5292a2f46c72634776dc27998b61cdcdbdba3f35e7ca7e` | passed; reachable from public `main` |
| `workflow-governance-model` | `0.2.1` | `governance-handoff` `1.1` | `98576b4f3f755aceccc657bc83df7c94260d4fc0` | `452210d520721a4616dc72646b96dd28d587a197` | `75f96909fa31a8bcf65d74d243aeea0e8b43185b13974f19f60f47cf769125c7` | passed; reachable from public `main` |
| `mothership-router` | `0.3.0` | `router-manifest` `1.0` | `a23f4b651e1a8baf39a1266a66188bec21c3265c` | `22db307e169f919d2d5855ca7b6bf17b6973b71f` | `273b1def57ec35957750c4979c737480c4cbb7f4db2294993dd5475b54fc673b` | passed; reachable from public `main` |
| `secretary-tui` | `1.2.0` | `observation-snapshot` `1.0` | `f3cb61e61bc88e7c4cfd09efe93006c812258fe9` | `8cbdb5f0f0960441e9986468641e431e4441b026` | `587ef29c693a834ffada7789b28b2b76cbefbad819386b91507a510def3facb2` | passed; reachable from public `main` |

The report verified four owner manifests, four schema digests, byte identity with all four bundled schemas, four public
examples, the Secretary copy of the Router input, shared task ID/capability/status fields, and false authority/execution
effects. This is conformance evidence for those commits, not a claim about newer commits, tags, or releases.

## Evidence

- [Wave 1 verification](verification/2026-08-09-hub-wave1.md)
- [Machine-readable evaluation](../evaluation/results/mothership-0.4.0.json)
- [Paper evidence and limits](research/paper-evidence.md)
