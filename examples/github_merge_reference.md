# GitHub merge reference consumer

This source example demonstrates the first consumer connection for the pinned
Core 0.4.3.dev0 / companion 0.2.0.dev0 pair. It handles one explicitly chosen
PR in one terminal process:

1. The transport performs an initial read-only PR fetch. The existing executor
   performs its own bounded preflight GET again immediately before Core
   consume, so a changed head or base stops the run before the PUT.
2. Core freezes the fetched head, base, repository, PR number, and merge method.
3. The runner prints the retained `FrozenAction`, its digest, and its expiry as
   escaped JSON. It also prints the consume deadline and the limits that the
   base is checked during preflight only and that the PUT has no atomic base
   condition.
4. The trusted local operator must enter exactly the displayed action-bound
   response: `approve <action_id> <action_sha256>` or
   `reject <action_id> <action_sha256>`.
5. Core records that response. Only an approval is passed to the existing
   one-shot executor, which is called once.
6. With `--verify-result`, the same process builds a Receipt from the returned
   terminal records and calls the existing independent read-back producer. It
   keeps execution and verification results separate.

Run it only from a Python 3.12+ source checkout with the companion package
available. The following keeps both source packages on `PYTHONPATH` and uses a
new real path for the dedicated ledgers:

```sh
ledger_dir=$(mktemp -d)
chmod 700 "$ledger_dir"
ledger_dir=$(cd "$ledger_dir" && pwd -P)
read -r PR_NUMBER
PYTHONPATH=.:packages/mothership-github python3 \
  examples/github_merge_reference.py \
  --repo UMEBOSHIISAN/mothership \
  --pr "$PR_NUMBER" \
  --ledger-dir "$ledger_dir" \
  --merge-method merge \
  --verify-result
```

Choose `PR_NUMBER` from the current human-approved task. The historical public
PR #18 is not a prescribed execution target.

The token is requested manually with hidden terminal input. It is passed to an
explicit `GitHubRestTransport` constructor and is neither discovered from the
environment nor written to the output or ledgers. If the terminal cannot hide
input, the runner stops; it never falls back to visible input. Both input and
output must be TTYs. There is no `--yes` option.

The ledger directory must already exist, be an immediate real directory with
mode `0700`, and be supplied as an absolute normalized path. The runner refuses
to start when `authority.jsonl` or `attempts.jsonl` already exists, so it has no
resume, replay, reissue, retry, or renewal flow. This session guard is a local
fresh-session convenience; it does not provide global per-PR deduplication
across directories or copied ledgers.

The Core consume deadline is the action TTL. The expected base is checked by
the executor's preflight GET; the GitHub PUT has no atomic base condition. The
operator is trusted for this local ceremony, and the example does not
authenticate the operator's identity.

Without `--verify-result`, exit status `0` means success, explicit rejection, or a deliberate approval
stop (EOF, interrupt, or mismatch). Exit status `1` means a pre-execution
failure, an executor failure, or `reconciliation_required`; an unresolved
executor or receipt result is never reported as success or as an unmerged PR.
Before displaying a returned outcome, the consumer checks the same fact
invariants as the companion receipt rows: success requires HTTP 200, an
explicit `merged: true`, and a valid merge commit SHA; failure cannot carry
positive merge facts. Contradictory summaries require reconciliation. An
explicit `reconciliation_required` result stays unresolved even if its fields
resemble success. This check is not an independent observation of GitHub and
does not rewrite receipts, restore authority, or retry the action.
An execution result's `mutation_attempted` field means the executor entered its
mutation stage; it does not prove that a request reached GitHub. Executor
exceptions report that field as `unknown`.
Exit status `2` means non-TTY input/output or invalid arguments.
Output write or flush failure returns `1`, including failure to display the
approval request or a cancellation event. A failed approval display stops before
reading a response, recording a decision, or executing. A cancellation returns
`0` only when its stop event was successfully written and flushed.

The acceptance tests use a fake transport and temporary ledgers only. They do
not contact GitHub, use a real token, install packages, or commit/push changes.
This example is a reference consumer, not production approval or identity
authentication, and it does not connect to Harness, MOON, Secretary, or the
observation CLI.

## Read back the result in the same run

`--verify-result` completes the public-PR reference flow: choose one PR, inspect
and approve the exact action, attempt it once, then see the independent result.
The flag is optional; omitting it preserves the execution-only behavior and
makes no verifier calls. This consumer is a source-checkout entry point, not a
new installed mutation CLI or a Harness bridge.

The verification step uses the original live Core-issued action and the real
executor's returned consume/start/finish records. It adds at most two public,
tokenless GETs through a separate verifier. The manually entered mutation token
is not forwarded. Private or inaccessible PRs can therefore remain UNKNOWN.
There is no polling, retry, renewed authority, or reconstructed action.

The JSON output contains the execution result followed by a verification result
with the exact terminal source pair, validated Receipt, and complete read-back
bundle (Verification plus sanitized evidence). Preserve that output if you need
to retain read-back evidence; the authority and attempt ledgers do not store it.
The executor reference is a caller-attested hash of the consumer's source bytes,
fixed before execution. It identifies those bytes, not an authenticated executor.

With the flag, interpret the result as follows:

| Exit | Meaning |
| --- | --- |
| `0` | Execution succeeded and read-back is CONFIRMED; explicit rejection or approval cancellation also retains its existing `0`, identified by the output event. |
| `1` | Execution failed/remains unresolved, or result output failed. |
| `2` | Invalid arguments or non-TTY input/output. |
| `3` | Execution reported success, but read-back is UNKNOWN, MISMATCH, or unavailable. |

A confirmed read-back never rewrites a FAILED/UNKNOWN Receipt into SUCCESS.
Missing terminal records or adapter/verifier errors remain unavailable with a
fixed sanitized reason; they never manufacture a successful Receipt or rerun the
operation. An output failure after execution cannot undo an issued effect.

A fast successful merge may have the same one-second timestamp as the attempt
start. It deliberately remains UNKNOWN (`ambiguous_merge_time`), because the
available timestamps cannot prove their order. Waiting or automatically reading
again would not resolve that ambiguity. Inspect the records and external state;
do not repeat the mutation to obtain a green result.
