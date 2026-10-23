# Thin Harness handoff — local synthetic candidate

This opt-in path connects a non-executing Harness preview to one retained
`MergeReviewSession`, injected execution, separate readback, a foreground result
and offline evidence inspection. It is a local candidate, not a released or live
GitHub integration. The normal Harness command and its presentation hooks still
do not execute work. No custom Lease, managed mode or approval token is added.

## What the path means

```text
Explicit request + offline interpretation
  → installed ume-harness --handoff-json (advisory preview)
  → Mothership foreground owner + actual Git observation
  → exact request displayed → one exact terminal response
  → existing Session / Core consume / companion (injected transport)
  → original bundle → separate injected readback
  → result at the same terminal + preserved files → offline inspect
```

The preview hash identifies the provided request and interpretation. It does
**not** prove that natural-language text means the separately supplied operation.
The human must review the full repository, PR, head, base, method, expiry, action
ID/digest and request ID/digest. A preview's classification or “approval required”
label never becomes a Core decision. Host context remains separately provided.

The owner observes a real worktree's origin, path, branch, head, status and
tracked/nonignored file contents. The origin must match the operation repository,
and the clean worktree head must match the expected head. The existing Session
callbacks reobserve before review/preflight/mutation. These are bounded,
best-effort observations, not a lock, sandbox, revocation fence or coverage of
ignored files. Symlinks, submodules and oversized trees are rejected.
The observer invokes the trusted host's `/usr/bin/git` with a fixed
`/usr/bin:/bin` child PATH; caller PATH cannot select its Git binary. Missing
system Git stops observation, without a searched or automatic fallback.

## Local installation and invocation

Use Python 3.12+, Git, and the reviewed candidate changes in both repositories.
This local POSIX candidate requires `/usr/bin/git` and no-follow/nonblocking
regular-file reads. The explicit Harness input rejects symlinked path components
and special files; unsupported platforms stop before producing a handoff.
The Mothership base is `6c37212cbcfbf9f17757157ae502a7c4922e1039`; the thin Harness
base is `62a61ca8c5e03120cda28805de05e8a62e4304d9` in
`ume-harness-engineering`. These base commits alone do not contain this new seam.
Keep the exact candidate file/wheel hashes with the local acceptance record.
No public candidate pin is claimed until these changes are committed and released.

Build the three wheels from the **same Mothership checkout**, using the existing
[wheel recipe](host-adapters.md#try-the-current-candidate) with this reviewed
candidate. Install them into a fresh virtual environment with `--no-index --no-deps`.
Use Harness's standard installer with a **new dedicated prefix**. Do not run
`setup`, connect hooks, replace a daily installation or edit the public mirror.

Inputs are explicit: a prepared clean synthetic worktree, an operation JSON with
exactly `repository`, `pull_request`, `expected_head_sha`, `expected_base` and
`merge_method`, and complete host context. The context example below is synthetic;
it does not authenticate a person or grant permission. The run directory must not
exist and must be outside the observed worktree.

```sh
# Paths below select your reviewed installed candidates and prepared local fixture.
/path/to/venv/bin/mothership-harness-handoff \
  --harness-cli /path/to/new-harness-prefix/bin/ume-harness \
  --request '隔離したPRの対象を確認する' \
  --interpretation-file examples/thin-harness-handoff/interpretation.json \
  --parameters /path/to/prepared-fixture/parameters.json \
  --host-context examples/thin-harness-handoff/context.json \
  --worktree /path/to/prepared-fixture/worktree \
  --run-directory /path/to/new-run
```

Run in a foreground terminal. After checking the full displayed request, type
`approve REQUEST_ID REQUEST_SHA256`, `reject REQUEST_ID REQUEST_SHA256`, or `cancel`.
There is no `--yes`, saved-answer restoration or live transport option. The
command uses an injected synthetic merge and deliberately unavailable synthetic
readback: executor `SUCCESS` and independent `UNKNOWN` remain different. No
token, GitHub request or model call is used. Exit 0 means the local workflow and
its reporting completed, not that a real PR merged or Verification is CONFIRMED.
`--json` returns the same structured outcome saved in `result.json`.

Read the saved records in another process:

```sh
/path/to/venv/bin/mothership-evidence inspect --human \
  --readback-evidence /path/to/new-run/readback-evidence.json \
  < /path/to/new-run/verified.json
```

For rejection, cancellation, missing finish or unavailable readback, inspect
`original.json` without a sidecar if that file was successfully saved. If saving
failed or the ledger is torn, retain the originals and inspect the explicit
authority/attempt paths. Do not repair a prefix, recreate a Receipt, reconsume or
run the operation again. A missing file is not evidence that no write occurred.

## Retained evidence and compatibility

The private run directory contains the request/interpretation inputs, advisory
preview, observed Git snapshot, exact review request, original authority/attempt
ledgers, `original.json`, and, when available, `verified.json` and
`readback-evidence.json`. `result.json` and `RESULT.md` explain the same structured
outcome. `manifest.json` relates artifact hashes to the action and request; it is
correlation evidence, not authenticated provenance or a new authority ledger.
Raw user input is retained only in this explicitly selected private directory.

The existing legacy Lease-based `HarnessMergeBridge` and its historical pin remain
unchanged. They are not required by this thin path. Existing bundle validation,
saved-result v0/v1 readers, expected-digest checks and the six recipient cases keep
their contracts. This path already retains a real portable request before review,
so it exports the existing bundle directly rather than fabricating one afterward.

## Local acceptance limits

Regression checks use real Git/Core/ledger/evidence code with synthetic terminal
responses and injected transport/observations. They cover input bounds, identity
drift, wrong/expired decisions, cancellation, duplicate calls, uncertain attempts,
missing finish, output failure and distinct CONFIRMED/UNKNOWN/MISMATCH records.
They do not count as a human participant, live interpretation, live canary, hosted
CI, a published package, or universal host/tool coverage. Fresh installed candidate
bytes must be checked separately from source tests. A release stage requiring a
clean committed source is not bypassed to stage an uncommitted candidate.

## 日本語での境界

Harnessは依頼整理のままです。Mothership側の明示的な入口で、実Gitの状態と具体的な
操作を確認し、既存Sessionへ渡します。独自Lease・権限管理は追加しません。
依頼文のhash一致は、文章と操作対象の意味が一致する証明ではありません。
この候補は合成入力・模擬通信のローカル確認用です。実canary、公開、人の受入は別です。
結果が不明なら、そのまま不明と表示して既存記録へ案内します。再実行で埋めません。
