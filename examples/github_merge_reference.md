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
  --merge-method merge
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

Exit status `0` means success, explicit rejection, or a deliberate approval
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

The acceptance tests use a fake transport and temporary ledgers only. They do
not contact GitHub, use a real token, install packages, or commit/push changes.
This example is a reference consumer, not production approval or identity
authentication, and it does not connect to Harness, MOON, Secretary, or the
observation CLI.
