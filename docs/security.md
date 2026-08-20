# Security model

Mothership reduces accidental authority and packaging drift by making boundaries inspectable. It is not a sandbox,
secret manager, formal proof, or security certification.

## Assets and trust zones

| Zone | Treatment |
| --- | --- |
| immutable package resources | accept only after inventory and digest verification |
| explicit local protocol input | untrusted; cross strict file, JSON, schema, and metadata checks |
| diagnostic process output | untrusted observation; sanitize and reduce to closed fields |
| operator credentials and commands | outside Mothership; never package or infer them |
| companion output | untrusted until its frozen protocol snapshot validates |

## Local JSON threats

The protocol loader rejects duplicate keys, non-finite numbers, malformed UTF-8, unsupported versions, unknown fields,
and oversized input above 1 MiB. It rejects secret-like keys and private absolute paths. A terminal control character is
also rejected where the schema permits displayed text.

Validation errors use static reasons and JSON paths. They do not echo the input value or explicit source path.

## File-system threats

Explicit protocol paths must be absolute and normalized. Mothership opens each path component without following
symbolic links, accepts regular files only, and rejects directories, FIFOs, sockets, and other special files. It checks
file identity and size before and after reading to detect relevant substitution or growth.

These checks depend on POSIX descriptor features. See [Compatibility](compatibility.md).

## Packaged-resource threats

`mothership verify` rejects missing, extra, duplicate, unsafe, resized, or digest-mismatched inventory entries. The
registry separately binds each protocol schema to a SHA-256. A stale protocol snapshot remains possible when an owner
releases a change that Mothership has not frozen; the compatibility table makes that lag visible.

## Diagnostic subprocess threats

`doctor` resolves fixed aliases and runs only documented version, help, or list probes under a sanitized environment.
It does not pass credentials or endpoint overrides. An installed Ollama CLI may contact its default loopback daemon for
`ollama list`; the guarantee is no Mothership-directed external network target, not zero local IPC.

Diagnostics report availability only. A discovered command is not approval to use it.

## Authority boundary

Protocol validation never grants authority. The initial protocol registry declares no authority-capable or
execution-capable entry. Router and observation fixtures require `authority_effect: false` and
`execution_effect: false`.

The default CLI is read-only. Explicit library calls for staging or ledger evidence can write only to a caller-supplied
target. Those APIs cannot make an external action approved merely by recording data.

Decision Cards and Decision Approvals (`evidence/contracts/decision-card.v0.schema.json`,
`evidence/contracts/decision-approval.v0.schema.json`) fix `authority_effect: false` and `execution_effect: false` at
the schema level — the constants cannot be set to `true` and still validate. `validate_decision_approval_binding()`
(`mothership.contracts`) only proves that a human's Approval was recorded for one exact Card content, by exact
canonical-JSON SHA-256 digest and `decision_id` match. A successful binding is evidence of *review*, not a grant of
execution authority: nothing in the schemas or the pure binding function connects a Decision Approval to
`approval-event.schema.json` (the separate invocation/execution-side evidence) or to any worker invocation. Treating a
valid binding as execution authorization would be a caller error outside what this contract asserts.

## Installation boundary

Pip and Git are external tools with their own side effects and supply-chain risks. Review the source or wheel, verify
its digest, use an isolated environment, and run `mothership verify` after installation. Verification cannot prove the
interpreter, operating system, installer, or host is uncompromised.

## Residual risks

- A compromised interpreter or operating system can bypass application checks.
- A malicious dependency used only during build can affect an artifact; prefer reviewed, pinned build tooling.
- A valid document can contain misleading but schema-conforming statements.
- A diagnostic executable found on `PATH` may not be the program the operator intended.
- Time-of-check/time-of-use risk exists after Mothership returns data to another process.
- Synthetic conformance results do not estimate real-world attack prevalence or protection rates.

## Vulnerability reporting

Follow [SECURITY.md](../SECURITY.md). Do not include credentials, personal data, private paths, or live exploit details
in a public issue.
