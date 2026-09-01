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
| exact action input | untrusted until the closed `github.merge_pr` profile validates |
| authority-action ledger | file-fsynced local state; consume-once requires one trusted, non-rollbackable live history |
| separately configured bounded executor | external execution plane; untrusted receipt source until verified |

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

## GitHub observation threats

`github-decision-card` and `github-candidate-window` issue one explicit read-only request to `api.github.com`. They do
not accept a GitHub credential or add a GitHub `Authorization` header. The standard-library opener inherits configured
system proxy settings, however, and an authenticated proxy can add `Proxy-Authorization`. Proxy configuration is part
of the caller's network boundary. Responses are size-bounded, strictly decoded, and reduced to closed fields.

## Decision Plane

Decision Cards and Decision Approvals (`evidence/contracts/decision-card.v0.schema.json`,
`evidence/contracts/decision-approval.v0.schema.json`) fix `authority_effect: false` and `execution_effect: false`.
`validate_decision_approval_binding()` proves only that a caller-attested review is bound to one exact Card by
canonical-JSON SHA-256 and `decision_id`. It does not authenticate the reviewer, freeze an action, write action
authority, select a worker, or invoke anything.

The 0.2 compatibility protocols are also non-authorizing. Protocol validation never grants approval or authority;
Router and observation fixtures keep `authority_effect: false` and `execution_effect: false`.

## Boundary record contracts

The current source contains three strict, closed contracts for a future
external-action workflow. Their implementation is limited to pure schema
validation and exact receipt/verification binding:

- `consequence-proposal.v0` is non-authorizing and non-executing. It is limited
  to the current `github.merge_pr` action shape, including its exact target,
  `expected_head_sha`, and `expected_base`. Its `state_sha256` is a
  proposal-only state snapshot/reference. The current `FrozenAction` binds
  exactly `repository`, `pull_request`, `expected_head_sha`, `expected_base`,
  and `merge_method`; there is no v0 path that binds a consequence proposal to
  a `FrozenAction` or Action Authority. Its policy disposition is preserved as
  `ELIGIBLE`, `DENY`, or `UNKNOWN`; validation does not implement a domain
  policy engine or convert either `DENY` or `UNKNOWN` into eligibility.
- `external-action-receipt.v0` is an executor-local report with `SUCCESS`,
  `FAILED`, or `UNKNOWN`. `SUCCESS` is not external truth and cannot satisfy
  independent verification.
- `external-action-verification.v0` is a separate read-only observation bound
  to the same `action_id` and `action_sha256`. `CONFIRMED`, `MISMATCH`, and
  `UNKNOWN` are preserved; missing or unreadable read-back remains `UNKNOWN`.

`validate_receipt_verification_binding()` requires the exact action identity
and the canonical digest of the referenced receipt. It does not
promote a receipt into verification, authorize a retry, or create authority.
Schema validation proves only closed record shape and the declared
action/receipt binding. It does not authenticate an executor or verifier,
operationally isolate an executor, or enforce a verifier's read-only behavior.
The package ships no executor, verifier producer, network mutation, or live
external-action end-to-end path. A future executor must re-check mutable
external preconditions immediately before mutation; the current package does
not perform that check.

Policy eligibility, identity, role, and human-ceremony data are evidence
references only. Mothership does not authenticate human identity, implement
RBAC, or own a domain policy engine. External authority delegation is forbidden
by default, and no delegation or obligation/follow-up engine is implemented.

The Source Health, Evidence Spine, Run Lineage, and Agent Decision components
remain separate semantic owners. Their validation or advisory output is not
promoted to truth or authority by this package. UME Presence is documented as
`authority = NONE`; a machine-enforced prohibition on it producing verified
execution state remains `UNKNOWN` here.

## Action Authority Plane

The current consequential-authority path begins only when a caller separately supplies an exact supported action to
`freeze_action()`. The core accepts one closed operation profile, `github.merge_pr`, validates its execution parameters,
derives its display, computes the canonical action digest, and issues a core-owned `FrozenAction` with a short fixed
TTL. The digest excludes `expires_at`, so the library does not enforce single-issuance freshness. The integration must
generate a fresh action_id for every freeze, correlate the response to the exact live issuance and expiry shown to the
human, and reject delayed or reused responses. Human-readable display fields such as `consequence_if_approved` are
derived from execution parameters and cannot be supplied as executable input.

`validate_decision_transport()` requires `approve` or `reject` bound to the exact `action_id` and action SHA.
`record_action_decision()` records that caller-attested decision in a dedicated authority-action ledger. The public API
does not authenticate human identity or accept an identity credential; the integration must establish and audit the
human ceremony before calling it. FrozenAction issuance relies on interpreter-local state, but a POSIX child forked
after issuance inherits a copy of the object and registry. The API does not enforce process identity; freeze through
decision recording must remain in that issuance lineage. `consume_action()` appends and file-fsyncs one consume event
before returning the exact action.

The ledger is an explicit normalized local file with strict owner-only modes. Its immediate parent must be a real 0700
directory and its leaf a non-symlink regular 0600 file; higher ancestor resolution remains a caller trust boundary.
Reads and appends occur under a lock; append, flush, file `fsync`, rollback, and quarantine paths fail closed. The
complete JSONL state is revalidated before use. Mismatch, expiry, malformed state, action tamper, approval replay, and
action replay reject authority without appending a success event. Create-on-first-use does not fsync the parent directory,
so the new directory entry is not claimed crash-durable.

Replay state is ledger-local and has no monotonic external anchor.
The one-shot consume guarantee requires one trusted, non-rollbackable live ledger history. Approval state copied to
another path, or
rolled back or restored at the same path before consumption, creates an independent replay opportunity and must not be
used as another authority source.

The legacy `mothership.approval` / `orchestration.lib.ledger` path remains invocation-evidence compatibility. Its
`approval_granted`, `attempt_started`, and `attempt_finished` lifecycle is not the canonical Action Authority Plane.

## Execution Plane

Consumption is permission for one exact action; it is not execution. The default CLI remains read-only and exposes no
action-authority or executor command. The package does not ship a generic production executor.

Actual external effects require a separately configured bounded executor. That executor must validate its own external
preconditions, use only the consumed exact action, and produce receipt and verification evidence. Authority consumption
does not authorize retries: a failed or ambiguous execution requires a newly attested exact action rather than
automatic retry or fallback.

## Installation boundary

Pip and Git are external tools with their own side effects and supply-chain risks. Review the source or wheel, verify
its digest, use an isolated environment, and run `mothership verify` after installation. Verification cannot prove the
interpreter, operating system, installer, or host is uncompromised.

## Residual risks

- A compromised interpreter or operating system can bypass application checks.
- A malicious dependency used only during build can affect an artifact; prefer reviewed, pinned build tooling.
- A valid document can contain misleading but schema-conforming statements.
- A schema-valid Decision Card or derived action display can still mislead a human about surrounding context.
- Human provenance is supplied by the integration; the public API verifies binding but not a person's identity.
- Re-freezing the same action ID and parameters reproduces the digest; without fresh IDs and live-issuance response
  correlation, an older matching decision can be recorded against the new TTL.
- FrozenAction cannot be reconstructed after restart or in a fresh interpreter, but a post-issuance POSIX fork inherits
  a usable copy of issuance state; this is not process-identity isolation.
- Replay prevention assumes one trusted, non-rollbackable live ledger; copied or restored history can replay authority.
- A new ledger's file data is fsynced, but creation does not fsync the parent directory entry.
- Ancestor components above the immediate ledger parent are caller-trusted path state.
- A diagnostic executable found on `PATH` may not be the program the operator intended.
- A separately configured bounded executor can contain implementation, receipt, or secret-handling defects.
- External service state can race or invalidate preconditions after Mothership returns the exact action.
- Synthetic conformance results do not estimate real-world attack prevalence or protection rates.
- The physical `github.merge_pr` record is operator-observed prose, not independently reproducible proof of the
  operation profile or generic execution safety.

## Vulnerability reporting

Follow [SECURITY.md](../SECURITY.md). Do not include credentials, personal data, private paths, or live exploit details
in a public issue.
