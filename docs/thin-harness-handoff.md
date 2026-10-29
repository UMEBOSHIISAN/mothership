# Thin Harness handoff — explicit source candidate

This opt-in path connects a non-executing Harness preview to one retained
`MergeReviewSession`, injected execution, separate readback, a foreground result
and offline evidence inspection. The default route is local and synthetic. This
updated, unreleased source also has the explicitly selected live route described
below; the older fixed source pins do not include it. The normal Harness command and its presentation hooks still
do not execute work. No custom Lease, managed mode or approval token is added.

## Explicit live GitHub entry

Build Core, companion and adapters from the same reviewed revision containing
`--live-github`. The older `e787206` setup and the historical pins below support
the synthetic route only. Record the actual source and installed wheel identity;
do not add the new flag to an old installation and call it qualified.

The entry still uses an explicit offline interpretation. It does not invoke a
model, choose a PR from prose, install hooks or connect a normal chat implicitly.
The operator supplies the exact approved parameters and current host-context
file. The context is caller supplied; its fields are not host or human identity
authentication. Use a clean matching worktree and a new private run directory:

```sh
/path/to/reviewed-venv/bin/mothership-harness-handoff \
  --harness-cli /path/to/installed-prefix/bin/ume-harness \
  --request 'Inspect the explicitly selected canary PR' \
  --interpretation-file /path/to/interpretation.json \
  --parameters /path/to/approved-parameters.json \
  --worktree /path/to/clean-canary-worktree \
  --run-directory /path/to/new-private-run \
  --host-context /path/to/current-host-context.json \
  --live-github --expected-login YOUR_REVIEWED_ACCOUNT --json
```

Input and stderr must be foreground terminals; stdout may be saved separately.
The token is entered with hidden terminal input and passed to the existing
transport in memory. If hidden input is unavailable, the command stops. It does
not read credentials from environment/settings/clipboard, create a token, select
another account or save the token. Never paste a token into a chat or command
argument.

Using that same credential, the transport performs at most one authenticated
`GET /user` and one `GET /repos/{repository}` to require the selected account,
exact repository and boolean write permission. It keeps only that small
projection. Write permission does not guarantee that branch rules allow a merge.
The terminal then displays `LIVE GITHUB RUN`, the account observation and the
retained request. Respond only to that exact request/digest. There is no `--yes`,
automatic answer, saved approval restoration or retry.

After approval, the existing executor rechecks the PR and attempts at most one
merge PUT with the expected head. The expected base is a preflight observation,
not an atomic base-SHA condition on the GitHub PUT. Qualify on an explicitly
approved, dedicated canary base before considering a business PR or main.
Independent tokenless readback performs at most the existing two public GETs;
the repository must be publicly observable for this verifier.

Live mode saves `thin-harness-handoff-result.v1` and
`thin-harness-handoff-manifest.v1`, identifying the selected mode and account
observation. Synthetic mode retains its v0 formats and never reads a credential
or reaches GitHub. Mode selection is not verification: inspect the Receipt,
independent Verification and readback provenance separately. Source authentication
and structural inspection limits stay unchanged. Feed `original.json` or
`verified.json` to the existing evidence reader, not the result/manifest summary.

| Live outcome | Exit | Meaning |
| --- | --- | --- |
| Receipt SUCCESS and independent CONFIRMED | 0 | Both corresponding reports are retained; this is not generic production certification. |
| Explicit reject or cancel | 0 | Deliberate stop, with no execution attempt. |
| UNKNOWN, MISMATCH, failed/incomplete execution or persistence/display failure | 2 | Retain the evidence and reconcile; do not replay, reconsume or renew. |

A PUT response may be lost after GitHub commits. An UNKNOWN Receipt and a later
CONFIRMED observation can therefore coexist; the command still returns 2 and
does not rewrite the execution report. Same-second ambiguity remains UNKNOWN.
Do not adjust clocks, wait for a desired status or issue another PUT for green
output. Existing files are kept on failure, including partial artifacts.

This source change is not evidence that a live canary, normal-host hook migration,
human usability acceptance or release/public-mirror promotion has occurred. Those
operations require their concrete target approvals and measured evidence.

## What the default synthetic path means

![Explicit local handoff and separate result return; synthetic path, not live acceptance](../assets/readme/en/ume-stack-responsibility.svg)

The diagram is an explanation of the local candidate. Its return path means the
foreground result and retained evidence, not a successful live GitHub operation.

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
In the updated local source candidate, finite limits are 1,024 names,
16 MiB per regular file and 64 MiB of accepted file content per tree pass.
Content is hashed incrementally with reads of at most 64 KiB; the file bytes
are not accumulated in memory. Both tree passes and the existing no-follow,
metadata, identity and status checks remain. A rejecting pass can read one
additional bounded file before the aggregate-size rejection. These are not
whole-observation I/O or elapsed-time limits. Older fixed pins, including the
installed `ad733ca` runtime, retain the previous 1 MiB/file and 16 MiB/tree limits.
Source observation of a larger worktree does not qualify that old installation
or establish a live operation, Receipt, independent Verification or human acceptance.
The observer invokes the trusted host's `/usr/bin/git` with a fixed
`/usr/bin:/bin` child PATH; caller PATH cannot select its Git binary. Missing
system Git stops observation, without a searched or automatic fallback.

## Local installation and invocation

Use Python 3.12+, Git, and the reviewed candidate changes in both repositories.
This local POSIX candidate requires `/usr/bin/git` and no-follow/nonblocking
regular-file reads. The explicit Harness input rejects symlinked path components
and special files; unsupported platforms stop before producing a handoff.
Use this fixed source pair for the current installed/offline check:

- Mothership runtime:
  [`4b2b7a2b07aab3ac38f6745153a33ee54e013697`](https://github.com/UMEBOSHIISAN/mothership/commit/4b2b7a2b07aab3ac38f6745153a33ee54e013697).
  Build all three packages from this one checkout. This unreleased candidate
  includes the input-read fixes and the bounded streaming observer; it is the
  runtime of the 2026-10-26 installed/offline check below.
- Canonical `ume-harness-engineering`:
  [`3edf71408ba4dc6f001fb3a1dec36e766dfafb6c`](https://github.com/UMEBOSHIISAN/ume-harness-engineering/commit/3edf71408ba4dc6f001fb3a1dec36e766dfafb6c).
  The 28 declared payload files in the tested installed UME v0.2.0 prefix match
  this commit's Git blobs. Its generated launcher is recorded separately.

These pins identify source revisions, not released package versions. Use the
canonical Harness pin rather than assuming public-mirror parity; this check does
not perform or qualify mirror promotion. These runtime pins identify the tested code separately from
later documentation commits. Keep the installed file/wheel hashes with the local
acceptance record.

Historical reproduction pins remain available: Mothership's input-read fix at
[`ccf53f50b9ad5e4f58cfdb97ec4d356bb86cb1cc`](https://github.com/UMEBOSHIISAN/mothership/commit/ccf53f50b9ad5e4f58cfdb97ec4d356bb86cb1cc)
and Harness
[`2da9a0afeaf937ba95d6f8526888ffc926aaf10b`](https://github.com/UMEBOSHIISAN/ume-harness-engineering/commit/2da9a0afeaf937ba95d6f8526888ffc926aaf10b).
The 2026-10-24 installed check used Mothership
[`e787206979b24de2df06f45caa2610c52c5b5753`](https://github.com/UMEBOSHIISAN/mothership/commit/e787206979b24de2df06f45caa2610c52c5b5753)
and Harness
[`c0b036e091c189435564387427bf04e3930893f7`](https://github.com/UMEBOSHIISAN/ume-harness-engineering/commit/c0b036e091c189435564387427bf04e3930893f7),
with Harness installed root identity
`76a8a54332f8b50face686cd5e8ebef45da17bcf3e493d8602697f1f5aa5425e`.
The earlier installed four-case evidence used Mothership `5812c253`; it does not
verify the later input-read fix. Do not substitute one dated check for another.

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
The default synthetic route has no `--yes`, saved-answer restoration or live transport. The
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

| Retained file | What the next person or AI can read |
| --- | --- |
| `result.json` / `RESULT.md` | The same foreground outcome, with unknowns kept separate |
| `original.json` | Supplied request, decision, consume and execution records; inspect only if saved |
| `verified.json` + `readback-evidence.json` | Recorded independent observation and its structural binding |
| Explicit authority / attempt ledgers | Existing records to inspect when result saving or a terminal pair is incomplete |

Use `inspect --human` for these bundles. The reference consumer's `result.jsonl`
uses the separate `inspect-result --human` reader shown in the
[saved-result examples](../examples/saved-results/README.en.md). A filename or
manifest entry does not prove that a write completed; keep the original files
and do not reconstruct missing records or run the operation again.

## Installed offline check (2026-10-26)

The current pair above was measured on macOS arm64 / Python 3.12.15. Three
already-built wheels from the fixed Mothership runtime were independently
rehashed and installed once into a fresh task-local venv with
`--no-index --no-deps --no-compile`. No duplicate build or dependency download
was needed. Imports resolved inside that venv, not the development checkout.
The existing installed UME v0.2.0 prefix supplied the real advisory CLI; no
`setup`, hook connection or daily-prefix replacement was performed.

| Check | Observed result |
| --- | --- |
| Source → wheel → installed bytes | 84 runtime/data files match the committed blobs; 97 wheel RECORD hashes checked |
| Harness identity | 28 payload files match canonical `3edf714`; all 29 payload/launcher hashes unchanged before/after |
| Existing installed handoff tests | 21 passed, 0 skipped; the three input-read regressions are included in 21 |
| Existing four synthetic CLI cases | Approve: one consume and one started/finished pair, Receipt SUCCESS, Verification UNKNOWN; reject/cancel/wrong-request: no attempts |
| Separate-process inspection | All four retained bundles re-read offline; saved artifacts/ledgers unchanged and manifest hashes match |
| Larger real worktree | One installed-observer read at retained head `39a4e0e`; HEAD, status and index hash unchanged |

The three local wheel artifacts were:

| Package | Wheel SHA-256 |
| --- | --- |
| Core `0.5.0.dev0` | `4a834a6be935889f533ff0104410e6d0c09968d46d4b164d950e2eb5f27b1067` |
| companion `0.3.0.dev0` | `9154acf8da26e40c5696f1ec980be835b9ce387d756cdc6ae81e54477fccf088` |
| adapters `0.1.0.dev0` | `fe1d4dc2b64ec23291070e3c6c24089e76eb8c3d3429f8fd2b906a7add5a0de5` |

These hashes identify these retained builds, not a released distribution or a
promise of byte-identical wheels from a later build. A different Codex actor
directly checked the immutable Mothership blobs, wheel bytes and installed
payloads, and read the behavioral logs without rerunning the tests. The Harness
source/payload comparison and test executions were performed by the producer.

The larger-worktree check only exercised the installed observer. It did not
start the real GitHub CLI path, request credentials or perform a merge. The
old `ad733ca` installation and its preflight HOLD remain separate; these results
do not upgrade its approval or establish a live Receipt or Verification. Human
acceptance, Linux/mini, normal host setup, public-mirror promotion and real
canary acceptance remain unverified here. The earlier six recipient cases and
all historical pins remain unchanged. These runtime hashes precede the later
documentation revision that records this measurement.

## Installed offline check (2026-10-24)

The historical `e787206` / `c0b036e` pair was checked on macOS arm64 with Python 3.12.14. The build
frontend used pip 26.2.2, setuptools 84.1.0 and wheel 0.48.0; the fresh venv used
its bundled pip 25.0.1. Exact-commit source-only archives were checked
against all tracked blob IDs and executable modes: 288 Mothership files and 73
Harness files. Three wheels were built offline from that one Mothership snapshot,
installed into a fresh venv, and Harness's standard installer used a fresh prefix
with the same Python selected on PATH. No development checkout supplied imports.

| Check | Observed result |
| --- | --- |
| Source → wheel → installed bytes | 84 runtime/data files match; all 28 Harness payload files match |
| Standard new-prefix installer | All 9 default health checks passed; no setup or host activation |
| Existing synthetic approve case | One consume and one started/finished attempt pair; Receipt SUCCESS, Verification UNKNOWN |
| Existing reject / cancel / wrong-request cases | No execution attempts; wrong-request exits 2 |
| Existing three input-read regressions | 3 passed, 0 skipped: parent replacement, held parent descriptor, unsupported safety flag |
| Separate-process inspection | All four bundles re-read offline; saved artifacts and ledgers unchanged; manifest hashes match |

The unchanged four-case checker used synthetic terminal answers and injected
transport/readback. Its success report does not establish an actual merge or a
CONFIRMED external result. The original six saved-result cases and old pins are
preserved. The wheel/source/installed hashes belong to the runtime pins, before
these later documentation changes.

This measures installed-runtime behavior from verified source snapshots. It does
not perform canonical `stage_release` / `verify_staged_release`: their clean Git
checkout and committed-byte gates remain required for release work. No substitute
Git metadata or public-mirror promotion was used. Linux/mini execution, human
acceptance, live interpretation and real canary remain outside this measurement.

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
既定経路は合成入力・模擬通信のローカル確認用です。上記の固定commitを組み合わせます。
実接続は明示的な別経路で、導入版の読取確認だけではその実行や承認を認定しません。
実canary、公開mirrorへの反映、パッケージrelease、人の受入は別です。
結果が不明なら、そのまま不明と表示して既存記録へ案内します。再実行で埋めません。
