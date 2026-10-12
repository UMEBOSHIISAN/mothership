---
name: mothership-evidence-inspect
description: Inspect a supplied Mothership host-evidence-bundle.v0 with the installed read-only evidence CLI. Report missing records and separate Receipt/Verification results.
---

Use this local skill when the user supplies a Mothership evidence bundle to
inspect. It requires the optional `mothership-adapters` package already installed
on the selected connected computer. This repository does not install or activate
the skill, connect a computer or configure a plugin.

Feed the supplied JSON bytes to `mothership-evidence inspect` on stdin using the
host's supported local command interface. Do not interpolate supplied JSON into
shell code. The command takes no file path, URL, ledger or executable selector.
If the installed command or supported stdin interface is unavailable, report
that dependency; do not fetch, install, authenticate, retry or substitute a
mutation tool. A bounded synthetic fixture is [example-bundle.json](example-bundle.json).

Report `missing`, `receipt_status`, and `verification_status` separately. A null
Receipt means no complete terminal attempt pair was supplied. Receipt SUCCESS
does not mean independent Verification MATCH. Invalid input is an error, never
completion evidence.

All supplied rows are caller-attested and source-unverified. Hash and schema
validation establish internal consistency only. Preserve `authority=false`,
`source_authenticated=false`, and `external_effect_verified=false` in the
explanation, including for self-consistent synthetic bundles. Inspection never
issues, approves, consumes, restores or executes an action.

Local and cloud Dots runtime qualification are both unperformed. An offline CLI
test does not establish either host's permissions, identity or effect boundary.
