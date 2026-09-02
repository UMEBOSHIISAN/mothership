# GitHub merge PR E2E evidence — 2026-09-01

This note separates facts visible in the public repository from lifecycle claims supported only by privately retained,
hash-committed evidence. Neither evidence class broadens the claim beyond the one tested `github.merge_pr` operation.

## Public evidence

The public repository records this bounded result:

- Operation: `github.merge_pr` for PR #17.
- Canary base: `e2e/mothership-merge-canary-base-20260901a`.
- Approved head: `3761aa359af5465c22e57482e71f85c574b35a07`.
- Merge commit: `027584f479da087fa660f875cd1afa8230bc0f9b`.
- Merge parents: `543dda851113fd62467469823465c8f93fe541da` and
  `3761aa359af5465c22e57482e71f85c574b35a07`.
- Diff: 2 files, +3/-0.
- Public `main` remained unchanged at `880e514382b1a9594a9d4a6f06f5939283e57c60`.
- Canary head branch preserved.
- Marker SHA-256: `ee8d960ee64d83593bccea5e87893668e3ed6e19008029502d47c6bdc42f1a9c`.
- post-merge CI: success.

These public facts establish the resulting Git objects, bounded canary target, retained head branch, unchanged public
`main`, diff size, marker content, and subsequent CI result. They do not expose the private approval or execution
lifecycle.

## Privately retained lifecycle trace

The following claims depend on a privately retained lifecycle trace and are not publicly reproducible from the GitHub
objects alone:

- The approval bound one human decision and exact action digest with a 10-minute TTL.
- The authority ledger recorded one-shot consume semantics.
- In the earlier run, executor preflight stopped after consume, and replay was rejected.
- The successful run used a fresh human decision and fresh authority.
- The successful run recorded one mutation request, followed by a separate read-only verification.
- A local reviewer independently checked the retained lifecycle evidence and its claim ceilings.

The retained private evidence commitments are:

- `37edac6551074ac1223606fdb0cf35df639d968eb50f31862438359a80115941`
- `091d886302e3bc9328f9cd004de5ba29764e578ba63c5bad846bd3a3d5b0c17f`

These commitments identify the retained evidence without publishing storage locations or raw lifecycle records.

**CLOSED-BUNDLE PROOF OF RUN1 REMOTE MUTATION ZERO = UNKNOWN.** The earlier trace records that preflight stopped before
the mutation request path, but the closed retained evidence does not independently prove the absence of every possible
remote mutation.

## Claim ceiling

- `E2E_GREEN_SCOPE = github.merge_pr only`
- `HARNESS_VERTICAL_INTEGRATION = NOT_CLAIMED`
- `SECURITY_CLEAN = NOT_CLAIMED`
- `GENERAL_EXECUTOR_SAFETY = NOT_CLAIMED`
- `MULTI_OPERATION_GENERALITY = NOT_CLAIMED`
- `PUBLIC_PACKAGE_SHIPS_EXECUTOR = FALSE`
- `HUMAN_IDENTITY_AUTHENTICATION = NOT_CLAIMED`
- `PRIVATE_TRACE_PUBLICLY_REPRODUCIBLE = FALSE`

Receipt success is executor-local evidence; it is not verification. The separate verifier result applies only to this
bounded canary action. No authenticated human identity, complete Harness vertical, or public executor implementation is
established by this evidence.
