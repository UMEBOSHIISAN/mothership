# Host adapter guide

This guide is a practical map of the eight bounded routes in the
[integration catalog](integrations.md). Execution routes carry one exact
`github.merge_pr` action through a retained review boundary. Read-only routes
inspect detached evidence without restoring an action or granting authority. A host supplies
its own identity, context, credentials, transport, and effect decision. The
examples use synthetic transport and caller-provided context; they do not use
API keys, account login, or a live GitHub endpoint.

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

The CLI is stdin-only. Pass bytes through the host's supported local command
interface, for example the repository-local Dots fixture:

```sh
mothership-evidence inspect < integrations/dots/example-bundle.json
```

`mothership-evidence export` accepts a bounded request/envelope on stdin and
produces a deterministic `host-evidence-bundle.v0`. Both CLI and MCP routes
preserve `caller-attested`, `source_authenticated=false`,
`authority=false`, and `external_effect_verified=false`. A self-consistent
bundle is still not authenticated external evidence.

Dots uses the repository-local `mothership-evidence-inspect` skill and the same
stdin-only CLI. The skill is not installed or activated by this repository;
local and cloud Dots runtime qualification remains unperformed.

## Qualification boundaries

These routes are bounded adapters around the current `github.merge_pr` profile.
They are not a generic executor, socket service, daemon, retry mechanism,
credential manager, identity authenticator, or automatic UME-HARNESS bridge.
They do not add a new operation profile. Keep Receipt and independent
Verification separate, preserve missing finish and UNKNOWN, and stop on
context/action/expiry drift before transport. A future storage, device, or
other operation needs its own exact profile and independent review evidence.
