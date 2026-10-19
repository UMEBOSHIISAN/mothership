# Host adapter guide

This guide is a practical map of the eight bounded routes in the
[integration catalog](integrations.md). Execution routes carry one exact
`github.merge_pr` action through a retained review boundary. Read-only routes
inspect detached evidence without restoring an action or granting authority;
the separately named `readback` command may perform one bounded public
observation. A host supplies
its own identity, context, credentials, transport, and effect decision. The
examples below use synthetic transport and caller-provided context; they do not
use API keys, account login, or a live GitHub endpoint. The explicit `readback`
route is documented separately below.

## Install the source candidate in one checkout

### Try the current candidate

For the features documented in this guide, use the unreleased source candidate
at `bd6a2e83da9ae75ee38cf1914e4017971063a90d` (PR #49 merged on 2026-10-15).
This revision includes readback/inspect-sidecar, explicit JavaScript callback
modes, and Python `SessionError.diagnostic`. It is a fixed snapshot, not a
promise to include later main changes. Review the source before use and record
the exact revision. Start in a new directory:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git mothership-candidate
cd mothership-candidate
git fetch origin bd6a2e83da9ae75ee38cf1914e4017971063a90d
git rev-parse --verify FETCH_HEAD
git checkout --detach bd6a2e83da9ae75ee38cf1914e4017971063a90d
git rev-parse --verify HEAD

python3 -m venv .venv
. .venv/bin/activate
python -m pip install \
  -e . \
  -e packages/mothership-github \
  -e packages/mothership-adapters
```

Check that both printed revisions equal the selected full SHA. This recipe does
not claim that a package release or live host has been qualified. Python 3.12 or
later is required; all three packages must come from this same checkout.

### Reproduce the PR #45 runtime

To reproduce the historical readback/inspect-sidecar runtime reviewed for
[PR #45](https://github.com/UMEBOSHIISAN/mothership/pull/45), keep its original pin
`91f474ed9ba96f5c00925d44f3dd84739d41cdc7`. It excludes the later callback-mode
change and Session diagnostics. Use the documentation at that revision when
reproducing historical behavior; do not apply later API examples to it.
Start in a separate new directory:

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git mothership-readback
cd mothership-readback
git fetch origin 91f474ed9ba96f5c00925d44f3dd84739d41cdc7
git rev-parse --verify FETCH_HEAD
git checkout --detach 91f474ed9ba96f5c00925d44f3dd84739d41cdc7
git rev-parse --verify HEAD
```

Check that both printed revisions equal the historical full SHA, then run the
same venv and three-package install commands above in this historical checkout.
Keep historical test evidence separate from current-candidate evidence.

The three editable installs are from the same checkout. Optional SDK extras are
opt-in; select only the extras required by the routes you use. The following
additional command selects all three SDK extras:

```sh
python -m pip install -e 'packages/mothership-adapters[agents,langgraph,mcp]'
```

These extras pin `openai-agents==0.23.1`, `langgraph==1.2.12`, and
`mcp==2.3.0`. Record the `FETCH_HEAD` and detached `HEAD` values alongside the
test evidence; do not reconstruct a live session from an exported JSON request.

## One retained session and synthetic transport

Every execution route wraps the same `MergeReviewSession`. It retains the live
`FrozenAction`, the original request, the caller-attested response, and the
same separate authority and attempt ledger paths. The context provider is
called again at review and effect boundaries. A transport callback must check
the parameters it receives against the retained action.

The smallest synthetic shape is:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from mothership_adapters.session import MergeReviewSession

parameters = {
    "repository": "example/repo",
    "pull_request": 7,
    "expected_head_sha": "a" * 40,
    "expected_base": "main",
    "merge_method": "merge",
}
context = {
    "host_id": "synthetic-host",
    "session_id": "session-1",
    "actor_id": "caller-1",
    "runtime_generation": "generation-1",
    "scope": ["github.merge_pr"],
}

class SyntheticTransport:
    def get_pull_request(self, repository, pull_request):
        assert (repository, pull_request) == ("example/repo", 7)
        return {
            "http_status": 200, "state": "open", "merged": False,
            "head_sha": "a" * 40, "base_ref": "main",
        }

    def merge_pull_request(self, **received):
        assert received == {
            "repository": "example/repo", "pull_request": 7,
            "expected_head_sha": "a" * 40, "merge_method": "merge",
        }
        return {"http_status": 200, "merged": True,
                "merge_commit_sha": "b" * 40}

scratch = TemporaryDirectory(prefix="mothership-example-")
ledger_dir = Path(scratch.name)  # A fresh private mode0700 parent.
session = MergeReviewSession(
    parameters,
    context_provider=lambda: dict(context),
    authority_path=ledger_dir / "authority.jsonl",
    attempts_path=ledger_dir / "attempts.jsonl",
    transport=SyntheticTransport(),
    executor_ref={"ref_id": "executor:synthetic", "sha256": "c" * 64},
)
request = session.request
response = {
    "schema_version": "authority-action-review-response.v0",
    "decision": "approve",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "action_id": request["action"]["action_id"],
    "action_sha256": request["action_sha256"],
}
assert session.review(response) == "approve"
result = session.execute(parameters)
assert result["receipt"]["status"] == "SUCCESS"
scratch.cleanup()
```

The example uses a fresh private temporary directory and removes its synthetic
ledgers. A real host retains its ledgers in a private mode0700 parent directory;
`authority_path` and `attempts_path` must be different. The companion owns one bounded effect attempt, and a missing finish
or uncertain transport result is preserved as rejection or UNKNOWN according
to the existing contract. There is no retry, restart, or reconsume path.

## Session failures and existing evidence

The Python diagnostic API is included in the [current candidate](#try-the-current-candidate)
pinned above. The historical PR #45 revision does not contain it. Record the
selected revision; this is not a released-package or live-host qualification.

Python callers can read `SessionError.diagnostic` without exposing callback or
ledger exception text. It is a detached mapping: changing the returned mapping
does not change the error or session. Existing exception messages, terminal
states and execution results remain unchanged.

```python
import json
from mothership_adapters.session import SessionError

retained_request = session.request  # Keep the request before this invocation.
try:
    result = session.execute(parameters)  # The host's one approved invocation.
except SessionError as error:
    print("same-call diagnostic (caller observation):",
          retained_request["request_id"],
          retained_request["request_sha256"],
          retained_request["action"]["action_id"],
          retained_request["action_sha256"])
    print(json.dumps(error.diagnostic, sort_keys=True))
    print("Diagnostic unknown fields describe this call's observation; "
          "they do not override retained source records.")
    print("A failed phase code does not establish the remote outcome.")
    # Keep the existing records for inspection; do not execute again here.
```

The caller knows this relationship because it retained the request and caught
the error from that invocation in the same handler. The diagnostic mapping has
no action or request ID of its own. Printing the identifiers does not create a
durable binding or authenticate the observation. Do not attach a saved
diagnostic to a bundle by matching filenames, dates or phases. If that same-call
context or diagnostic was not retained, report it as unavailable.

The mapping contains `code`, `phase`, `authority_use`, `external_effect`,
`next_check`, and `retry_allowed` (always false). Codes and phases come from a
fixed vocabulary, never from raw exceptions, paths or host input. The phase is
the last local boundary observed, not a certified exact failure location.

| Observed phase | What to inspect |
| --- | --- |
| `review_validation` | Retained request and response; their action, expiry and context binding |
| `decision_record` | Existing authority records; the decision write may have persisted before raising |
| `execution_validation` | Retained request and supplied parameters/context, plus existing records |
| `companion_execution`, `preflight_transport`, `preflight_returned` | Existing authority and attempt records; the last phase does not prove whether consume/start persisted |
| `mutation_guard`, `mutation_transport`, `mutation_returned` | Existing authority and attempt records; transport return does not prove external success or finish persistence |
| `receipt_build`, `result_export` | Existing evidence and source records; do not manufacture a Receipt or missing record |
| `unknown` | Existing evidence and source records; this includes owner/phase errors and unclassified errors |

`authority_use` means one-shot consume, not writing an approval/rejection.
`not_attempted BY THIS CALL` is limited to the current call before companion
entry; it says nothing about earlier calls, other tools or host callback effects.
Once the companion is entered, authority use and external effect are both
`unknown`. This intentionally does not infer a durable consume or remote outcome
from an exception or from the absence of a record.

The fixed `next_check` values select these read-only categories:
`review_request`, `authority_records`, `review_request_and_existing_records`,
`authority_and_attempt_records`, or `existing_evidence_bundle`. They are guidance,
not executable commands or permission to create replacement evidence. The
owner/JavaScript protocol defaults to its existing generic error. The updated
paired client/owner can explicitly forward this mapping as described under
[Node Session diagnostics](#node-session-diagnostics). This is not automatic
forwarding through every host adapter.

If an evidence bundle has already been retained or exported through the existing
validated exporter, inspect it offline:

```sh
mothership-evidence inspect --human < existing-bundle.json
```

This command requires that existing file. Diagnostics do not save or assemble a
bundle and do not read a ledger themselves. Preserve original records and bind
any exported bundle using the existing [evidence route](#read-only-evidence-routes).
The host may supply records it retained, or read its explicitly retained source
paths, to `export_evidence(retained_request, ...)`. Supply only available rows
for that request; the exporter validates their relationships. It does not locate
records, choose a newest file, restore the session, or bind an arbitrary
diagnostic to the bundle. Keep the same-call diagnostic display separate from
the provided-record summary and structural inspection limits. A decision or
consume write can persist before an exception: use the actual source records
rather than treating the exception as proof that nothing was saved.
If export or inspection rejects the supplied records or sidecar, produce no
operation summary. A caller can still display its separately retained expected
request as caller context, clearly stating that the rejected input has not been
bound to it. Next, compare the explicitly supplied record/sidecar IDs and hashes
with that retained request. If the caller context is unavailable too, leave the
operation identity unknown; do not infer it from rejected input or repair records.
A missing finish remains missing: inspection can explain the missing Receipt and
Verification, but `readback` still accepts only complete execution evidence with
`missing == ["verification"]`. Do not insert a finish, mint a Receipt, retry a
mutation or consume again to make the bundle eligible. Inspecting records is not
proof of their origin or the current external state.

## Python host routes

The optional SDK adapters do not replace the retained session or serialize it
for later restoration.

| Host | Exact calls | What is retained |
| --- | --- | --- |
| Agents SDK | `adapter = AgentsMergeAdapter(session)`; `prepared = await adapter.prepare(agent, input)`; `result = await adapter.resume(response)` | The typed `mothership_github_merge_pr` tool, its call identity, raw arguments, cloned agent, and SDK approval state |
| LangGraph | `adapter = LangGraphMergeAdapter(session)`; `prepared = adapter.prepare(thread_id)`; `result = adapter.resume(response, thread_id=prepared["thread_id"], interrupt_id=prepared["interrupt_id"])` | The original thread and interrupt IDs; the internal `InMemorySaver` carries review data, never the live session |
| UME-HARNESS | `bridge = HarnessMergeBridge(...)`; `bridge.review(response)`; `bridge.execute(parameters)`; `bridge.suspend()` / `bridge.resume()` | The local lease observation and the same host context; the lease does not become external permission |

The Agents SDK route accepts only an `Agent` with `hooks=None`; caller-supplied
`AgentHooks` are rejected before the runner starts. The adapter clones that agent
and owns the fixed function tool and its run hooks. Changing the tool callback,
schema, guardrails, approval policy, or dispatch identity stops the route before
review or execution. This qualification does not cover private SDK mutation or
arbitrary Python monkeypatching.

For a real Harness fixture qualification, set the test-only source root to the
pinned fixture before running the focused test. The recorded fixture is
`v0.1.7` at commit
`d7640a03b4b823d960f6e382607ad04aa8678c84`; without the variable, the fixture
qualification is explicitly skipped:

```sh
MOTHERSHIP_HARNESS_ROOT=/path/to/pinned-harness \
python -m unittest packages/mothership-adapters/tests/test_harness.py
```

This command is a qualification recipe, not evidence that a Harness runtime
was activated by this package.

## JavaScript owner, OpenClaw, and Lobster

`MergeOwnerClient` owns one Python child process and exposes only the fixed
sequence `prepare(parameters, executorRef)`, `review(response)`,
`execute(parameters)`, `cancel()`, and `close()`. The host passes callbacks for
context and the exact two transport operations:
`getPullRequest(repository, pullRequest)` and
`mergePullRequest(repository, pullRequest, expectedHeadSha, mergeMethod)`.
These positional signatures are the default, including callbacks with default
or rest parameters. `transport.getPullRequestMode` and
`transport.mergePullRequestMode` select each callback's contract independently:
omitting a mode or passing `undefined` selects `"positional"`; `"object"` passes
one detached payload object. Only these two strings are accepted. Other values,
including `null`, raise `OwnerClientError("parameters")` before child creation.
The constructor retains each selected mode; later transport-property changes do
not change it. Both constructor forms accept these transport options, and the
`get_pull_request` / `merge_pull_request` aliases use the same camel-case mode
keys. Existing callbacks that expect one payload object must opt in explicitly:

```js
transport: {
  getPullRequestMode: "object",
  mergePullRequestMode: "object",
  getPullRequest: objectGetPullRequest,
  mergePullRequest: objectMergePullRequest,
}
```

Callbacks that ignore all arguments need no change. Callback arity is not used
to infer a contract, and callback exceptions do not trigger a second call.
The owner checks callback parameters against the retained action and uses a
30-second bounded command deadline. A child failure after consume is
unresolved; the caller must not restart or replay it.

Owner `result` and `error` frames correlate a reply with one command through
`seq`, `reply_to`, and the retained owner/request/action IDs. The payload still
has the meaning of that command: `prepare` returns a review request, `review`
returns a caller-attested decision, and `execute` returns an execution report
with its Receipt. Receiving a reply is not a separate grant of authority or
independent Verification. There is no standalone ACK message or durable owner
resume protocol.

If the final execution reply is lost, do not resend `execute`, including with
the same IDs or changed parameters. Inspect records already retained by the
caller; an absent reply does not establish whether an effect occurred. Repeated
offline export/inspection of retained records neither recreates the live owner
nor spends authority. Missing Verification remains missing. The
[bounded delivery traces](composition.md#delivery-replies-and-one-use-authority)
exercise this connection with synthetic callbacks and temporary fixture records.

### Node Session diagnostics

This unreleased addition requires the updated `owner-client.mjs` and Python
owner from this same checkout. The fixed setup revisions earlier in this guide
predate this opt-in; they do not gain it by installing their pinned packages.

The object constructor accepts `sessionDiagnostics: true`. Omitting it, passing
`undefined`/`false`, or using the positional constructor retains
`mothership-owner.v0` and its strict code-only errors. Other values, including
`null`, fail before child creation. The opt-in launches the same single owner
with the fixed `--session-diagnostics` flag and uses `mothership-owner.v1` for
every frame. There is no version negotiation, restart, downgrade or fallback.
An old client with the updated owner continues using v0. An opt-in client with
an old owner fails at launch/protocol handling; do not retry with another mode.

Only an actual Python `SessionError` adds the six-field diagnostic to a v1
`{code: "session", diagnostic: ...}` reply. Other owner errors remain code-only.
Parent callback errors must remain code-only in either version. A malformed
callback rejected inside Session can become Session's own sanitized UNKNOWN
diagnostic; a diagnostic supplied by the parent is never adopted. The client
validates the closed diagnostic tuples and existing schema/owner/seq/reply/
request/action correspondence before exposing the matched error.

```js
const owner = new MergeOwnerClient({
  pythonExecutable, authorityPath, attemptsPath, contextProvider, transport,
  sessionDiagnostics: true,
});
try {
  // Use this retained owner's normal prepare/review/execute flow.
} catch (error) {
  // OwnerClientError.diagnostic is a detached mapping or null.
  // Retain it with this call's context; never use it to authorize a retry.
} finally {
  await owner.close();
}
```

`OwnerClientError.diagnostic` returns a detached mapping on every read, or
`null` when no Session diagnostic was received. Native EOF/EPIPE, child loss,
timeouts, parameter errors and invalid wire diagnostics do not acquire an
invented Python phase. Both `null` and a valid UNKNOWN diagnostic leave the
external result unconfirmed. Correlation is not source authentication or durable
evidence binding. Keep this same-call observation separate from any supplied
bundle's `inspect --human` output; it does not create a Receipt or Verification.

Run the real-child terminal example from this updated checkout with Python
3.12+ and Node 22+:

```sh
PYTHONPATH=.:packages/mothership-github:packages/mothership-adapters \
  PYTHON_EXECUTABLE=python3 node examples/owner_diagnostic_terminal.mjs finish
```

Use `review` for context drift before approval recording, `preflight` for a
synthetic GET failure after companion entry, or `finish` (the default) for a
synthetic finish-save refusal after one merge callback. All callbacks are
synthetic, with no credentials, network or live GitHub operation. The example
does create synthetic review/consume records in temporary fixture ledgers. In
`finish`, it changes only that temporary attempts file's mode from 0600 to 0400,
so the existing writer refuses to append; it never fills in a missing finish.
The child is closed and temporary files removed in `finally`.

The display separates the last observed phase, unknown effects, next existing
records to inspect and no re-execution/reconsume. A returned synthetic transport
value is not confirmation of a remote result. OpenClaw/Lobster wrappers still
map their errors to generic messages: this example accepts the direct Node
client/terminal path only, not deployed wrappers or a selected daily host.
They do not qualify a Hermes delivery path or an actual host deployment.

The selected OpenClaw route registers one typed `mothership_merge_pr` tool and
one `beforeToolCall` seam. The hook retains the exact tool-call ID and
parameters, returns an allow-once/deny review checkpoint, and closes the owner
on timeout, cancellation, mismatch, or failure. It deliberately excludes
nested, delegated, client/native, and unwrapped tool paths.

The selected registration seam is:

```js
const selected = createSelectedMergeTool({ owner, parameters, executorRef });
const checkpoint = await selected.beforeToolCall(
  { toolName: selected.tool.name, toolCallId, params: parameters },
  { toolCallId, delegated: false, nested: false },
);
```

The host resolves `checkpoint.requireApproval` and later invokes the same
selected tool with the retained call ID and parameters. It does not register a
global hook or claim coverage for other OpenClaw tool paths.

The Lobster route uses an embedded runtime with a private fixed registry for
`mothership.preview`, `mothership.approve`, and `mothership.merge`. A resume
token only resumes the embedded checkpoint; it never selects or restores the
owner. Use the retained owner and the same `parameters`/`executorRef`:

```js
const owner = new MergeOwnerClient({
  pythonExecutable,
  authorityPath,
  attemptsPath,
  contextProvider,
  transport: { getPullRequest, mergePullRequest },
});
const adapter = new LobsterMergeAdapter({
  owner, runtime, stateDir, parameters, executorRef,
});
const pending = await adapter.prepare();
const result = await adapter.resume(reviewResponse, {
  token: pending.resumeToken,
});
```

The OpenClaw and Lobster source pins are part of the qualification record:
OpenClaw snapshot
`6cc8bb1a4b9e97b4461c5cbd9006adf4630b9ccc`, and Lobster embedded runtime
commit `74db2679fe34c6b04b067eebea943eaabd8b789f`. The selected checks do not
qualify a full gateway, production wrapper, credentials, or live GitHub merge;
independent selected-wrapper review passed.

## Read-only evidence routes

The MCP server is launched by `mothership-evidence-mcp` over inherited stdio.
It exposes exactly three read-only tools:

* `receipt_validate`
* `receipt_verification_validate`
* `evidence_inspect`

Export and default inspection are stdin-only and offline. Pass bytes
through the host's supported local command interface, for example the
repository-local Dots fixture:

```sh
mothership-evidence inspect < integrations/dots/example-bundle.json
mothership-evidence inspect --human < integrations/dots/example-bundle.json
```

The explicit `readback` command is the only CLI route that may perform the
companion's public observation. It accepts one complete
`host-evidence-bundle.v0` whose derived Receipt is present and whose
`missing` list is exactly `["verification"]`. It validates the bundle, action
digest, Receipt lineage, and absence of an existing Verification before any
network call; malformed, foreign, incomplete, or already-verified input is
rejected without a GET. It writes a new bundle and leaves the input untouched:

```sh
mothership-evidence readback < original.json > verified.json 2> readback-evidence.json
```

Require exit status `0` and retain `readback-evidence.json`. The Python helper
`mothership_adapters.readback.readback_evidence(bundle, *, opener=None)` returns
`{"bundle": ..., "evidence": ...}`; the stderr file is that complete sanitized
`evidence` sidecar. Its canonical SHA-256 must equal the `sha256` in `verified.json`'s
`verification.evidence_refs`; this sidecar is caller-retained and is not a
source-authentication record. A single invocation makes at most two public
tokenless GETs, sends no credentials or `Authorization` header, and never
retries, polls, consumes authority, calls an executor, or writes a ledger.
The command emits the sidecar to stderr before attempting the new bundle on
stdout. Successful stderr is data, not an error log; do not merge the streams
with `2>&1`. Input and setup failures report a fixed sanitized diagnostic on
stderr with a nonzero exit status. Stream failures stop with a nonzero exit;
when the error sink is still writable, the fixed diagnostic may be reported,
but a failed stderr write is not retried. Discard both redirected files,
including any partial stream, unless the exit status is `0` and the canonical
hash check passes. A valid observation that is `UNKNOWN` or `MISMATCH` remains
a successful read-back bundle with its status preserved.

JSON export and inspection emit one complete newline-terminated value and require
a successful flush before exit `0`. A short write, invalid write count, or stream
failure returns nonzero without retry; discard partial output. Successful JSON
bytes and the inspection schema are unchanged.

The default command retains its JSON inspection contract. `--human` selects a
bounded text explanation for the local Terminal: recorded approval, recorded
authority use, Receipt, independent Verification, missing records, the supplied
observation summary, and a next read-only check. A missing
Verification record means independent confirmation has not been established by
this bundle; it does not prove verification never occurred. Missing decision or
consume records do not prove cancellation or absence of an effect. The current
Bundles produced by this read-back producer carry its allowlisted fixed reason
code and bounded explanation inside `observed_state.summary`; existing or
caller-supplied Verification summaries remain arbitrary caller-reported text.
The producer's structured sibling `evidence.reason` remains in the
caller-retained sidecar. Without an explicit sidecar, the formatter displays the supplied summary after
escaping it and does not parse prose into a trusted reason or authenticate the
source. The displayed text is not a diagnosis or instruction. The separate
`structured reason: unavailable in bundle` label refers to the absent structured
field, even when the caller-reported summary includes a reason string. The
next read-only check compares the referenced evidence’s canonical hash with
`verification.evidence_refs`; it does not require another readback.
The explanation keeps source-unverified visible and never suggests re-execution
or reconsume as recovery. It performs no read-back or other network request.

To inspect the retained sidecar as well, use the optional local-file input:

```sh
mothership-evidence inspect --human --readback-evidence readback-evidence.json < verified.json
```

`--readback-evidence` requires `--human`; it does not change the default JSON
inspection or MCP contract. The bundle still comes from stdin. Only the explicit
sidecar path is opened, with no-follow/nonblocking access and a regular-file
check. Final-component symlinks, FIFOs, devices and directories are rejected. Each input has the
existing 262,144-byte limit and strict JSON/type/depth/node bounds. Unsupported
file-access safeguards fail closed. No URL or path inside evidence is opened.

The offline reader validates the current `github-merge-readback.v0` shape and
matches the sidecar's canonical SHA-256 to the single `github-readback:` evidence
reference, its action ID/digest to the bundle, and its state hash to Verification.
It then displays the structured reason as **caller-reported**, with the recorded
observation time and conservative guidance. `clock_rollback` remains readable as
`UNKNOWN`: timestamps must use the zero-padded, uppercase UTC form
`YYYY-MM-DDTHH:MM:SSZ`, but ordering and external semantics are not re-evaluated.
Unknown well-formed reason codes receive generic guidance.

Bad input or a binding mismatch returns exit status 2 with a fixed diagnostic
and no human explanation. A complete explanation requires a complete write and
successful flush; discard partial output on failure. Exit 0 means inspection
completed, including for `UNKNOWN` and `MISMATCH`, not that the action succeeded.
This check proves internal binding only; it does not authenticate the source,
transport, actor, timing or causation, and it does not establish current remote
state. No network, retry, re-execution, reconsume or ledger write occurs.

The Python equivalent is `summarize_evidence(bundle, readback_evidence=sidecar)`
from `mothership_adapters.evidence`. Omitting the keyword preserves the existing
human output. Retain both original inputs for later inspection.

`mothership-evidence export` accepts a bounded request/envelope on stdin and
produces a deterministic `host-evidence-bundle.v0`. Export, inspect, inspect
`--human`, and MCP routes
preserve `caller-attested`, `source_authenticated=false`,
`authority=false`, and `external_effect_verified=false`. A self-consistent
bundle is still not authenticated external evidence.

Dots uses the repository-local `mothership-evidence-inspect` skill and the
default stdin-only inspection route. The skill is not installed or activated by this repository;
local and cloud Dots runtime qualification remains unperformed.

## Qualification boundaries

These routes are bounded adapters around the current `github.merge_pr` profile.
They are not a generic executor, socket service, daemon, retry mechanism,
credential manager, identity authenticator, or automatic UME-HARNESS bridge.
They do not add a new operation profile. Keep Receipt and independent
Verification separate, preserve missing finish and UNKNOWN, and stop on
context/action/expiry drift before transport. A future storage, device, or
other operation needs its own exact profile and independent review evidence.
