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
to start when `authority.jsonl`, `attempts.jsonl`, or `result.jsonl` already exists,
even without `--save-result`, so it has no
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
After argument and TTY checks pass, output write or flush failure returns `1`,
including an incomplete write, an invalid character count, or failure to display
the approval request or a cancellation event. Each event is written once,
without an output retry. The
output must be a text stream whose `write(str)` returns an integer equal to the
full line length; binary streams and bytes-valued counts fail closed.
A failed approval display stops before reading a response, recording a decision,
or executing. A cancellation returns `0` only when its stop event was successfully
written and flushed.

The acceptance tests use a fake transport and temporary ledgers only. They do
not contact GitHub, use a real token, install packages, or commit/push changes.
This example is a reference consumer, not production approval or identity
authentication, and it does not connect to Harness, MOON, Secretary, or the
observation CLI.

## Diagnose an initial preflight stop

An initial GET or snapshot validation failure keeps `reason: preflight_unavailable`,
exit `1`, and `mutation_attempted: false`. Its terminal event also includes a
bounded `diagnostic` object, for example:

```json
{"reason_code":"http_error","http_status":401}
```

| `reason_code` | Observed failure |
| --- | --- |
| `http_error` | A non-success HTTP status; the observed status is retained. `403` alone cannot distinguish permissions, rate limiting, or SSO requirements. |
| `redirect_rejected` | A redirect was rejected without a follow-up request. |
| `timeout` | The request timed out. |
| `tls_error` | TLS failed. |
| `network_error` | Another network failure. |
| `response_invalid` | The bounded response could not be parsed or lacked the required field shapes. |
| `snapshot_invalid` | The fetched snapshot was ineligible, such as an already merged PR or an invalid head/base. |
| `unexpected_error` / `unknown` | No more specific safe classification is available. |
| `interrupted` | Initial fetch or snapshot validation was interrupted. |

The category is an observation, not proof of the root cause. Unknown HTTP status
is `null`; no message, response body, credential, header, or exception text is
included. Only the exact transport exception type with validated metadata is
projected; other exceptions retain `unknown`. Initial failure stops before
approval, ledger events, consume, or mutation and does not trigger a retry.
Keep this sanitized terminal event when diagnosing a stop. `--save-result` still
saves only the three result event types below; a preflight stop leaves its
reserved `result.jsonl` empty.

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
bundle (Verification plus sanitized evidence). Add `--save-result` to retain
those events in a separate evidence file, or preserve the terminal output yourself;
the authority and attempt ledgers do not store the read-back bundle.
The executor reference is a caller-attested hash of the consumer's source bytes,
fixed before execution. It identifies those bytes, not an authenticated executor.

With the flag, interpret the result as follows:

| Exit | Meaning |
| --- | --- |
| `0` | Execution succeeded and read-back is CONFIRMED; explicit rejection or approval cancellation also retains its existing `0`, identified by the output event. |
| `1` | Execution failed/remains unresolved, result output failed, or requested evidence saving failed. |
| `2` | Invalid arguments or non-TTY input/output. |
| `3` | Execution reported success, but read-back is UNKNOWN, MISMATCH, or unavailable. |

A confirmed read-back never rewrites a FAILED/UNKNOWN Receipt into SUCCESS.
Missing terminal records or adapter/verifier errors remain unavailable with a
fixed sanitized reason; they never manufacture a successful Receipt or rerun the
operation. An output failure after execution cannot undo an issued effect.
Complete events already saved to `result.jsonl` remain intact; exit `1` reports
the display failure without changing the recorded execution or verification
outcome.

A fast successful merge may have the same one-second timestamp as the attempt
start. It deliberately remains UNKNOWN (`ambiguous_merge_time`), because the
available timestamps cannot prove their order. Waiting or automatically reading
again would not resolve that ambiguity. Inspect the records and external state;
do not repeat the mutation to obtain a green result.

## Save evidence from the same run

Use `--verify-result --save-result` to save the existing `frozen_action`,
`execution_result`, and `verification_result` JSON events in `result.jsonl`
inside the dedicated ledger directory. Each line is one JSON object. The
verification event includes the validated source pair, Receipt, Verification,
and sanitized evidence already produced by the consumer. Their statuses and
bindings are preserved; saving does not perform another observation or operation.

`--save-result` requires `--verify-result`. Without the save flag, no evidence
file is created. The consumer exclusively creates a regular file with mode
`0600` before requesting a token or calling the transport. An existing file,
directory, or symlink at that name stops the run without overwriting anything.
It flushes saved events to disk before displaying them. Token prompts, tokens,
approval input, headers, and raw exception text are not captured.

A creation or initial persistence failure stops before external I/O. A write,
sync, or close failure returns `1`; it cannot undo an operation that already
occurred. The partial file remains for inspection and blocks another session
in that directory. Never delete it to repeat an uncertain operation. Rejection,
cancellation, or a failure may leave an empty file or only a frozen action.
A missing or incomplete verification event is not proof of completion or proof
that no effect occurred. Inspect the attempt ledger and external state without
repeating the mutation.

This is a local copy of consumer output, not a new authority ledger, resume
format, authenticated audit store, or proof against alteration by the trusted
OS user. Both terminal streams are still required; saving does not replace the
manual approval ceremony or certify production suitability.
