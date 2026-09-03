# GitHub merge PR live E2E evidence — 2026-09-03

This bundle records one bounded live `github.merge_pr` trial. It separates public GitHub facts, sanitized lifecycle
records, and claims that still depend on privately retained hash-committed evidence. Nothing here broadens the result
beyond PR #18 and its isolated canary base.

## Public evidence

The public repository records this exact consequence:

- Operation: `github.merge_pr` for [PR #18](https://github.com/UMEBOSHIISAN/mothership/pull/18).
- Canary base: `e2e/mothership-merge-canary-base-20260902b`.
- Pre-merge base: `880e514382b1a9594a9d4a6f06f5939283e57c60`.
- Approved head: `0874166551f11d580168e8b4d0f354e742d39fe6`.
- Merge commit: `1cfbbf646b8ac227c8c411f08a961c4396cc69ca`.
- Merge parents, in order: `880e514382b1a9594a9d4a6f06f5939283e57c60` and
  `0874166551f11d580168e8b4d0f354e742d39fe6`.
- Diff: 1 file, +5/-0, adding `docs/e2e-fixtures/github-merge-pr-v1.txt`.
- Marker SHA-256: `3edb7363aa14a868313ece2e2eda57ef6643147cd27f54a7199e22c39dc642be`.
- Public `main` remained unchanged at `a5fc0d5997199dea2db5800b561e9a972765d27d`.
- Source fork head remained at the approved head after the merge.

These facts are captured in [`public-github-readback.json`](public-github-readback.json). They establish the resulting
Git objects, isolated target, exact head ancestry, bounded diff, preserved source head, and unchanged public `main`.

## Sanitized lifecycle records

The bundle publishes closed, non-secret projections of the exact action, human decision, consume event, executor
Receipt, and separate Verification:

- [`frozen-action.json`](frozen-action.json)
- [`human-decision.json`](human-decision.json)
- [`consume-event.json`](consume-event.json)
- [`executor-receipt.json`](executor-receipt.json)
- [`verification.json`](verification.json)
- [`manifest.json`](manifest.json)
- [`SHA256SUMS`](SHA256SUMS)

The records bind the trial to Mothership source commit
`71880ce7bef066bf4ce2380b4e4960b3932d0e56` and show:

- one caller-attested human approval inside the core-issued validity window;
- `max_uses=1`, one authority consumption, one merge request, and retry 0;
- an External Action Receipt with status `SUCCESS`;
- a separate tokenless read-only External Action Verification with status `CONFIRMED`.

Receipt `SUCCESS` is executor-local evidence. It did not establish the result by itself; the separate verifier classified
the external consequence as `CONFIRMED`.

These files are sanitized projections, not a published credential or runnable live controller. They do not let a third
party reproduce credential acquisition, the mutation, or the complete retained trace from public bytes alone.

## Privately retained lifecycle trace

The raw trace remains private. It contains the full evidence index, two-event authority ledger, dependency and readiness
records, controller result, and execution observations. Independent review recomputed the index, exact action digest,
ledger relationships, request cardinality, Receipt and Verification bindings, GitHub read-back, file permissions, and
persisted-secret scan.

### Private evidence commitments

The following SHA-256 commitments use logical filenames. Raw storage paths are not published.

| Artifact | SHA-256 |
| --- | --- |
| `001-baseline.json` | `c405a95ad778f17c8b81bb1cba64ed83366f240ea36ccfe8288443c9594a4fa4` |
| `002-target.json` | `7e2cbbb8c0eb4c2fc8ff61239bc570c1c845360af7de28db5408072a7b9fcd33` |
| `003-actor-policy.json` | `301c98a44e2b6f9ab58eeff228122a9d89e5a85bc0be3627030addd06c440107` |
| `004-proposal.json` | `442ebc75f703a04520128dfc529c4ccc9e6225d86467dfd409922c3817a304e8` |
| `005-dependency-evidence.json` | `680ff5cb04f20bf52589cff6cefc9b42b56222b1229c14066d6fba34860a06eb` |
| `006-readiness.json` | `033f06c9cf0231c246c5b91494881d2bc84acf3ffc9c8188ab97122fd67df797` |
| `007-decision-card.json` | `724af7f752cdbe3de1ad934a79ef7cbbcd21a275040a0a9ac1cb71cfc2dd5f51` |
| `008-executor-identity.json` | `59d3d85dcdf4c9d72df66f061d4b2d7245e44f9b512930d79d52b681e759607e` |
| `009-executor-observation.json` | `f2fdbd9edd501d064507131be6ce869c93eee6abcd69c666763ec1180bf075f6` |
| `010-receipt.json` | `9c25aad757303bbb2f93f70a8107873ca90691a82caafd7d593622cab869ee58` |
| `011-verification.json` | `c46aa245be5e3d2be422b62dee8b5916764f4bbfbec8edfd561c2c280a2e05bc` |
| `authority-ledger.jsonl` | `6ddb7cdc658116561f624b2c91cd36a8cfa3d1408088ab10533f48e47ca8fe3f` |
| `012-result.json` | `bf96a3d19288a1be61c30dbd07a2d4d8d5bc68e18347497756259ff8054c886a` |
| `013-evidence-index.json` | `bff5433cdec9cf4ede5f1b5b005a532b9cd230145bc8e4cad331850b8d6d9a31` |

The one-shot controller and its offline test suite are identified by these reviewed byte commitments:

- `orchestrator.py`: `ce7c9b8a46f3f715c4b759eecc468757b17a16e225431d5a22d8bb7cc24be638`.
- `test_orchestrator.py`: `08cf6b3ffa5f45071393eba5f25a2ae6464ddf353ddffd61005bfa275db3182b`.

## Operator-transport observation

During the human-to-controller handoff, multiple visually near-valid responses arrived with inserted indentation or a
truncated value. They were not submitted to the Authority Core. Only the exact four-line response was accepted for the
live issuance. No malformed response created a ledger event, consumed authority, or reached the executor.

This is both a successful fail-closed boundary and an open operator-friction defect:

```text
DECISION_B_CARD_COPY_TRANSPORT_FRICTION = OPEN
```

A future presentation surface should make exact-byte transfer easier without trimming, joining, repairing, or otherwise
changing human-approved input. This evidence-freeze change records the defect; it does not alter transport semantics.

## Residual risk

The preflight base SHA was observed but was not part of the FrozenAction digest. The base could therefore move during
the residual GET-to-PUT window. This trial contained that risk on an isolated canary and verified the actual merge
parents after execution; it does not claim that the general race is eliminated.

## Claim ceiling

- `LIVE_EXTERNAL_VERTICAL_GREEN = github.merge_pr PR #18 only`
- `SANITIZED_LIFECYCLE_RECORDS_PUBLIC = TRUE`
- `PRIVATE_TRACE_PUBLICLY_REPRODUCIBLE = FALSE`
- `HARNESS_TO_MOTHERSHIP_VERTICAL = NOT_CLAIMED`
- `GENERAL_EXECUTOR_SAFETY = NOT_CLAIMED`
- `PRODUCTION_READY = NOT_CLAIMED`
- `SECURITY_CLEAN = NOT_CLAIMED`
- `HUMAN_IDENTITY_AUTHENTICATION = NOT_CLAIMED`
- `BASE_SHA_DIGEST_BINDING = FALSE`
- `THIRD_PARTY_REPRODUCIBILITY = NOT_YET`
- `PUBLIC_RELEASE_SHIPS_LIVE_ORCHESTRATOR = FALSE`
- `CREDENTIAL_SCOPE_OR_ZEROIZATION_PROOF = NOT_CLAIMED`
- `GLOBAL_ABSENCE_OF_UNRELATED_REMOTE_MUTATION = NOT_CLAIMED`

The strongest supported statement is: one exact Mothership `github.merge_pr` canary action was bound to one
caller-attested human decision, consumed once, attempted with one merge request and no retry, emitted a `SUCCESS`
Receipt, and was separately confirmed by a tokenless read-only verifier. This is not a complete Harness vertical,
multi-operation platform, production-readiness result, or third-party reproduction.
