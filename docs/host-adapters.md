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

The following is a documentation example for a qualification run. Use the
candidate ref selected by the project owner, record both revisions, and keep
the checkout detached. This does not claim that the commands were run for this
source snapshot or that they select a release tag.

```sh
git fetch origin <candidate-ref>
git rev-parse --verify FETCH_HEAD
git checkout --detach FETCH_HEAD
git rev-parse --verify HEAD

python3 -m venv .venv
. .venv/bin/activate
python -m pip install \
  -e . \
  -e packages/mothership-github \
  -e 'packages/mothership-adapters[agents,langgraph,mcp]'
```

The three editable installs are from the same checkout. The optional extras
pin `openai-agents==0.23.1`, `langgraph==1.2.12`, and `mcp==2.3.0`. Record the
`FETCH_HEAD` and detached `HEAD` values alongside the test evidence; do not
reconstruct a live session from an exported JSON request.

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
The owner checks callback parameters against the retained action and uses a
30-second bounded command deadline. A child failure after consume is
unresolved; the caller must not restart or replay it.

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
`UNKNOWN`: timestamp syntax is checked, but ordering and external semantics are
not re-evaluated. Unknown well-formed reason codes receive generic guidance.

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
