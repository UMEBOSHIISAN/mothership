# Integration catalog

**Status: design catalog for the `0.5.0.dev0` source candidate.** Every host
adapter listed here is unimplemented and unverified in this repository. Listing
an entry point does not activate a plugin, configure credentials, add a runtime
dependency, or establish an effect boundary.

The shared seam is the pure [portable action review API](action-review.md): a
host retains the live `FrozenAction` and expected request, obtains its own
review response, and validates action, expiry, and host context before its own
effect path. Core still owns issuance, its clock, and trusted live-ledger
consume. The host still owns identity, leases, revocation, delegation,
suspension, credentials, transport, and the actual effect boundary.

The observable completion criteria below are deliberately host-specific. A
passing pure predicate, a schema-valid response, a plugin label, or a synthetic
Receipt does not satisfy them.

## Nine integration families

| Family and entry point | Reused capability | Added adapter work | Observable completion criteria | Status |
| --- | --- | --- | --- | --- |
| **Dots** — a dot using a connected computer, enabled supported plugin, or local skill ([official computer and app guidance](https://learn.chatgpt.com/docs/dots/computers-and-apps)) | Host-owned approval/UI context plus the shared request/response binding | Map the selected local/cloud task and plugin/tool call to one exact action; retain the original request; recheck the selected path's permission, availability, actor, session, generation, and scope immediately before the effect | Exercise local and cloud entry paths separately; for a local path, revoke/disconnect during a pause and show the local effect is blocked; for a cloud path, change its own permission/context and show that path is blocked; no action is reissued | **Unimplemented / unverified** |
| **OpenAI Agents SDK** — function tool with `needs_approval`, `interruptions`, and the same `RunState`/state resume ([official guardrails and approvals](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals)) | Tool-level approval interruption and application-owned state/decision | Build the request from the exact function-tool arguments; correlate approval to the same state and action; revalidate host context at the tool's effect boundary after resume | Approve and reject the same request; mutate state, arguments, actor, or generation while paused; show changed or timed-out review stops before the tool effect and that nested tools are covered where claimed | **Unimplemented / unverified** |
| **OpenClaw exact plugin tools** — typed plugin `before_tool_call` plus a wrapped tool path ([hook source](https://raw.githubusercontent.com/openclaw/openclaw/main/src/agents/agent-tool-definition-adapter.ts#L315-L417), [wrapper source](https://raw.githubusercontent.com/openclaw/openclaw/main/src/agents/agent-tools.before-tool-call.wrapper.ts#L386-L505)) | Plugin hook approval over reviewed parameters and the normal tool result path | Adapt only the selected wrapped plugin/dynamic-tool path; prove plugin enabled state, wrapper coverage, nested/client/MCP delegation, abort/runtime/source guards, and fail-open/fail-closed policy; preserve separate Core consume | Run the exact tool with changed params, disabled wrapping, nested fanout, remote/client delegation, timeout, and failed hook runner; record which paths were actually blocked | **Unimplemented / unverified** |
| **Lobster** — typed pipeline step with approval checkpoint and resume token ([OpenClaw Lobster documentation](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/tools/lobster.md#L8-L29)) | Deterministic workflow checkpoint and human-facing approval transport | Put Core consume and one bounded effect in a single qualified step; use resume only before consume or for non-effect work; correlate a fresh action after uncertainty | Pause before consume, resume once, and show one effect; crash or become uncertain after consume, then stop without resume/reconsume/retry; validate script allowlists and sandbox policy | **Unimplemented / unverified** |
| **LangGraph** — `interrupt()` with a checkpointer and `Command(resume=...)` ([official interrupts guide](https://docs.langchain.com/oss/python/langgraph/interrupts)) | JSON-serializable interrupt payload, persistent thread/checkpoint, and explicit resume | Put the request in the interrupt payload; retain thread and action lineage; revalidate action, expiry, and host context after node restart before the effect; isolate non-idempotent work after approval | Resume with the same and a changed thread/context; restart the node; show side effects before an interrupt are idempotent or absent, and a spent/uncertain action is never resumed | **Unimplemented / unverified** |
| **MCP, read-only first** — `tools/call` validation and evidence binding, including input-required round trips ([2026-07-28 tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)) | Closed schema validation, Receipt/Verification binding, and explicit evidence export without mutation | Expose only read-only validation/binding tools first; carry request IDs and explicit state handles; distinguish gateway-hosted MCP from client-owned and native tool execution; defer mutation until an effect path is qualified | Read-only calls return closed evidence; unknown/malformed input stays unknown; client and server paths are measured separately; no MCP scope or tool approval is treated as human identity or mutation authority | **Unimplemented / unverified** |
| **UME-HARNESS** — local-work preview, lease, and host effect boundary | Existing local intent preview and host-owned lease/session/generation/scope checks | Build an explicit bridge or exporter; map only reviewed exact operations; recheck lease, actor, generation, delegated scope, and revocation after suspension; preserve Core's external-action boundary | Suspend, revoke, change delegated scope, resume, and show no external effect; test empty scope, stale evidence, changed digest, missing finish, and uncertainty without automatic retry | **Unimplemented / unverified** |
| **Evidence exporters** — explicit `external-action-receipt.v0` and Verification binding | Existing Core/companion receipt adapter, canonical hashes, and UNKNOWN-preserving contracts | Export bounded source rows with provenance, schema, action identity, evidence digests, and status; keep source ownership and retention with the caller; never infer success from labels | Export the same terminal pair twice deterministically; reject missing finish, wrong identity, digest substitution, and ambiguous status; show Receipt and Verification remain separate | **Planned; unimplemented / unverified** |
| **Future exact-operation profiles** — a reviewed profile such as a storage or device action, never generic `execute` | `FrozenAction`, portable review request/response, consume, Receipt, and separate Verification | Define one exact parameter schema, issuance/freshness rules, transport/credential owner, executor boundary, and independent observation path; test profile-specific races and uncertainty | Positive/negative shape, changed action/context/expiry, suspended resume, uncertain outcome, missing finish, bounded retry policy, and independent result observation all have explicit evidence | **Future; unimplemented / unverified** |

## How to read the catalog

The entry-point links describe capabilities owned by those projects. They are
not claims that Mothership currently invokes, intercepts, configures, or
authenticates those products.

The Dots documentation describes connected computers, enabled supported plugins,
and local skills. A connected-computer grant can be unavailable or revoked, so a
candidate adapter would have to measure the selected local task and effect path;
the cloud computer has its own access and must be qualified separately.

The Agents SDK documentation describes an application-owned approval lifecycle:
the run pauses, the application resolves interruptions, and the same state is
resumed. Tool guardrails are attached to the tools they protect. A Mothership
adapter would still need a host-specific check at the effect boundary; an SDK
approval is not a Mothership decision event or human identity proof.

OpenClaw's documented plugin hook and wrapped tool path provide a concrete place
to investigate parameter-bound review. The source also has client-owned and
native tool paths, so a hook or plugin label alone cannot establish universal
coverage. Failure policy and delegation must be measured in the selected host.
An unmerged proposal is not an implementation result.

Lobster's resume token belongs to its runner. LangGraph's checkpoint and resume
value belong to its graph runtime. Neither token or checkpoint renews, restores,
or reissues a spent Mothership action. A qualified adapter must stop on an
uncertain effect and create a fresh review lineage only through a new explicit
action.

MCP's `tools/call` and input-required round trip provide a useful read-only
evidence seam. The 2026-07-28 specification does not give Mothership ownership
of client execution or implicit session state; state that spans calls must be
explicitly carried. Start with validation and evidence binding, then qualify a
separate mutation path if one is ever selected.

UME-HARNESS remains a separate local-work governance plane. Its preview or lease
does not grant external Mothership authority, and Mothership's review helper
does not enforce Harness leases. Evidence exporters translate records; they do
not authenticate their source or create authority.

## Qualification record for any future adapter

Before an adapter can be described as implemented, its owner must record:

1. the exact entry point and version/configuration used;
2. the action profile, retained live action, retained expected request, and
   host-owned identity/context inputs;
3. the effect boundary and the check performed immediately before the effect;
4. pause, resume, revocation, delegation, stale-source, missing-finish, and
   uncertain-outcome cases;
5. the number of attempted effects and whether any retry or reconsume occurred;
6. the Receipt and separate Verification records, including UNKNOWN handling;
7. local test evidence and its limits, with no release or live-operation claim.

Until those observations exist, the status remains **unimplemented /
unverified**. See [composition](composition.md) for the current responsibility
map and [action review](action-review.md) for the shared Core API.
