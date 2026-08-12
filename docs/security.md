# Security model

Mothership verifies supplied records and reduces accidental authority expansion. It is not a sandbox, secret manager,
formal proof, enforcement system, or security certification.

## Explicit path I/O

Flight commands accept explicit paths only. Import reads one named source and writes one named output directory; verify,
replay, and report read one named bundle. They do not discover repositories, search a home directory, watch processes, or
capture ambient state.

File access uses normalized paths, regular files, strict UTF-8 decoding, closed schemas, and digest verification. The
loader rejects symbolic links, special files, duplicate keys, malformed UTF-8, non-finite numbers, oversized input,
terminal control, and unsupported versions. Errors use safe relative references and do not echo secret values or private
absolute paths.

## Privacy profiles and secret rejection

`metadata-only` is the default: identifiers, digests, types, timestamps, scope/action classifications, and verification
results. `portable-evidence` includes only explicitly selected artifacts after privacy checks. There is no
capture-everything profile.

Secret-like keys, credentials, tokens, environment dumps, raw prompt bodies, private paths, and unsupported binary
content are rejected or require explicit redaction. Import, verification, replay, and reporting do not read an
environment file, credential store, or model transcript.

## Non-execution boundary

Import, verify, replay, and report do not invoke models, spawn workers, re-execute actions, fetch missing material,
repair input, retry failures, or choose fallbacks. A valid approval record is evidence of a stated binding, not a
permission grant from Mothership.

## Residual risks

Source records can be false, incomplete, stale, or omitted before bundling. A valid digest binds supplied bytes, not
every real-world action. A complete verdict verifies the supplied graph, not unobserved reality; users still review
execution systems, authority grants, and external side effects outside Mothership.
