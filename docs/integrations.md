# Integration catalog

**Status: bounded source-candidate catalog for Core `0.5.0.dev0`, companion
`0.3.0.dev0`, and optional adapters `0.1.0.dev0`.** The catalog records eight
finite routes around one exact action profile. A local check demonstrates the
selected seam and its retained state; it does not certify a provider, gateway,
credential, live GitHub effect, or a host's complete coverage.

Execution routes retain the original `FrozenAction`, review request, and caller-owned
host context. Read-only routes inspect detached evidence and never restore a live action. The host owns identity, leases, revocation, delegation,
suspension, credentials, transport, and its effect boundary. The retained
`MergeReviewSession` is the owner of the live action and uses the same
authority and attempt ledgers for the Core/companion path. Receipt is separate
from Verification; missing or uncertain completion stays visible as UNKNOWN.

## Eight bounded routes

| Route and entry point | Implemented source | Local evidence recorded | Qualification limit |
| --- | --- | --- | --- |
| **OpenAI Agents SDK** — one typed function tool with approval interruption | `mothership_adapters.agents_sdk.AgentsMergeAdapter`; optional `openai-agents==0.23.1` | 11 pinned local checks with a public synthetic Model, including caller-hook rejection and fixed-tool mutation gates | Only hook-free caller agents and the adapter-owned fixed tool are qualified; provider calls, credentials, tracing, deployed runners, private SDK mutation, and live effects were not exercised |
| **LangGraph** — one `interrupt()` and resume | `mothership_adapters.langgraph_adapter.LangGraphMergeAdapter`; optional `langgraph==1.2.12` | 5 checks with the same-process `InMemorySaver` | Cross-process durability, a restarted production graph, and a live effect path were not exercised |
| **OpenClaw selected plugin/tool hook** — selected hook and wrapped tool seam | `integrations/openclaw/adapter.mjs` plus the fixed Python owner client | 6 actual selected source-contract/owner checks; snapshot `6cc8bb1a4b9e97b4461c5cbd9006adf4630b9ccc`; combined wrapper qualification is 12 with Lobster | Independent selected-wrapper review passed; full gateway, client/native tool, MCP delegation, credentials, and live GitHub coverage remain outside the selected seam |
| **Lobster embedded step** — one retained approval checkpoint and resume | `integrations/lobster/adapter.mjs` with the private fixed owner registry | 6 actual cases on the pinned embedded runtime, commit `74db2679fe34c6b04b067eebea943eaabd8b789f`; the selected OpenClaw/Lobster wrapper qualification totals 12 | Independent embedded-wrapper review passed; a crash or uncertain post-consume outcome is stopped without resume, reconsume, or retry |
| **MCP read-only evidence** — inherited stdio server | `mothership_adapters.mcp_server`; MCP `2.3.0`; exactly `receipt_validate`, `receipt_verification_validate`, and `evidence_inspect` | 3 local in-process/stdio checks, including the ToolError boundary fix | Independent error-fix review passed; no mutation tool, identity proof, credential access, gateway permission, or external effect is exposed |
| **Dots local evidence** — repository-local skill | `integrations/dots/SKILL.md` and its example bundle, inspected through `mothership-evidence inspect` | Repository-local SKILL/example bundle and synthetic CLI inspection recorded | Dots local/cloud runtime, installation, activation, connected-computer permissions, and effects remain unperformed |
| **UME-HARNESS supplemental bridge** — local lease observation | `mothership_adapters.harness.HarnessMergeBridge` | 19 checks with the pinned real `LeaseStateStore` fixture (`v0.1.7`, commit `d7640a03b4b823d960f6e382607ad04aa8678c84`) plus synthetic transport | A lease observation is not external permission. No automatic runtime bridge or `begin_operation` for GitHub is provided |
| **Evidence export and inspection** — detached bounded bundle | `mothership_adapters.evidence` and `mothership-evidence` CLI | 10 deterministic evidence checks and 2 offline CLI checks recorded | Bundles are caller-attested and source-unverified; export never authenticates a source, grants authority, reads a ledger, or proves an effect |

The eight rows share the same exact operation: `github.merge_pr` with
`repository`, `pull_request`, `expected_head_sha`, `expected_base`, and
`merge_method`. A route may prepare or inspect a review, but no route turns a
generic `execute` call into authority. Future operations need a new reviewed
profile, exact parameter schema, executor, transport owner, and independent
observation path.

## How to use the catalog

The practical same-checkout setup and method examples are in the
[host adapter guide](host-adapters.md). The guide shows synthetic transport
and caller-provided context only; it does not ask for API keys or account login.

The route-specific entry-point links describe the selected seam, not universal
interception of the product. An SDK approval, graph checkpoint, Lobster token,
OpenClaw hook, Harness lease, MCP scope, or Dots permission does not become a
Mothership decision event or human identity proof. Each host must recheck its
own context immediately before transport, including after suspension or
resume.

For the OpenClaw and Lobster routes, the selected source pins are part of the
qualification record. The checks cover a bounded hook/embedded-runtime seam
with a Python owner; they do not establish full gateway, client, native-tool,
MCP-delegation, or credential coverage. For Dots, the repository-local skill is
an evidence-inspection entry point only and has not activated a local or cloud
Dots runtime.

The UME-HARNESS bridge observes a local lease and passes that observation into
the host context. It does not convert a lease into external permission. The
evidence route validates detached lineage and status relationships but leaves
source ownership and retention with the caller.

## Qualification record

For any future host path or exact-operation profile, record:

1. the exact entry point, version, source pin, and configuration;
2. the retained live action, expected request, and caller-owned identity/context;
3. the effect boundary and the check immediately before it;
4. pause, resume, revocation, delegation, stale-source, missing-finish, and
   uncertain-outcome cases;
5. attempted effects, with proof that no retry or reconsume occurred;
6. separate Receipt and Verification records, including UNKNOWN handling; and
7. the local evidence and its limits, without a release or live-operation claim.

Already-issued effects cannot be undone by later revocation. An uncertain
effect stops the current lineage; it never silently reissues the action. See
[composition](composition.md), [portable action review](action-review.md), and
the [host adapter guide](host-adapters.md) for the responsibility boundaries.
