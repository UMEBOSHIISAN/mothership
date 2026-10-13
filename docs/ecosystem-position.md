# Mothership in the agent tooling ecosystem

Source review: **2026-10-13**. This compares the linked official documentation
and selected public code, not deployed products or every upstream feature.
Links to moving branches may change. An unobserved capability is unknown,
not proof of absence. This source candidate is unreleased.

## What already exists

| Existing project or standard | Relevant upstream capability | Mothership's composition boundary |
| --- | --- | --- |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/human_in_the_loop/) | Tool approval interruptions and resumable run state. | Reuse host interaction; keep exact action/context checks and the live owner of authority. A restored host run is not restored Mothership authority. |
| [OpenClaw](https://docs.openclaw.ai/tools/exec-approvals) | Host execution approval policy and allowlists. | Keep the selected adapter path explicit. Its qualification does not establish interception of all host tools. |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/interrupts) | Interrupts, checkpoints and resume; an interrupted node starts again when resumed. | Keep host persistence in the host. A graph replay must not replay consumed authority or an ambiguous external operation. |
| [Delego](https://github.com/Delego-Dev/delego) | Intent-bound per-action approval and a signed audit trail. | Exact-action approval alone is not unique to Mothership. Keep our action binding, execution report and external observation separately inspectable. |
| [Signet](https://github.com/Prismer-AI/signet) | Cryptographic authorization evidence, bilateral receipts and portable audit bundles. | Portable receipts alone are not unique either. Mothership's current detached evidence does not provide equivalent signature or source-identity authentication. |
| [Agent Receipts](https://github.com/inchwormz/agent-receipts) | Runtime evidence for coding claims, signed journals, and separate integrity/outcome/applicability/claim dimensions. | Reuse task-completion evidence upstream. Do not recreate its test runner or collapse its claim validation into external-action authority. |
| [GitHub Agentic Workflows](https://github.github.com/gh-aw/reference/safe-outputs/) | Read-only agent jobs request structured writes executed by separate permission-controlled jobs. | Reuse workflow permissions and output controls. Workflow completion and target-state confirmation remain distinct evidence. This comparison does not add a gh-aw adapter. |
| [in-toto](https://github.com/in-toto/attestation/blob/main/spec/v1/README.md), [DSSE](https://github.com/secure-systems-lab/dsse/blob/master/envelope.md), [Sigstore](https://docs.sigstore.dev/about/bundle/) | Typed attestations, signed payload envelopes and packaged verification material. | If authenticated provenance becomes a requirement, evaluate existing implementations and an explicit trust policy. Hash equality alone does not supply that policy or authenticate a source. No signature integration is implemented here. |

## The useful seam to strengthen

Mothership's focus is the handoff between **what a human entrusted**, **which
authority was used**, **what an executor reported**, and **what a separate
observer recorded about the target**. The same narrow action can enter through
different supported hosts without merging those meanings.

This is a product focus, not a world-first or superiority claim. The current
reference profile is `github.merge_pr`; identity authentication, universal host
control and medical production qualification are outside its verified scope.
The current read-back checks a public PR and merge-commit topology. It cannot
identify the actor that caused the result. Detached evidence remains
`caller-attested` / `source-unverified` even when every binding matches.

The immediate usability test is concrete: another person receives a bundle and
its retained read-back evidence and can determine the recorded outcome, the
limits and the next read-only check without asking the author to explain it.
The [evidence inspection guide](host-adapters.md#read-only-evidence-routes)
describes the available commands and their exact boundaries.

| Received records | Required interpretation |
| --- | --- |
| Receipt `SUCCESS`, Verification missing | Executor-reported success; independent confirmation not established by this bundle. |
| Verification `CONFIRMED` and matching retained evidence | A reported external observation with matching bindings; source identity and causation remain unproven. |
| Verification `UNKNOWN` | Preserve the reason and uncertainty; identify a read-only check, never rerun the operation automatically. |
| A sidecar from another action, or a changed sidecar | Refuse the explanation rather than attach that evidence to this result. |
| Missing approval/consume records | Missing evidence does not prove that approval, authority use or an external effect never occurred. |

## What to measure next

For a separately authorized user acceptance trial, measure time to understand a
result, questions requiring the author's help, mistaken success interpretations,
and repeated investigation. These effects have not yet been measured across
users or hosts. Passing local tests is not evidence of user comprehension.

More adapter names, a new orchestrator and custom cryptography are not the next
acceptance criterion. Keep host capabilities upstream and make the existing
action-to-evidence handoff demonstrably easier to inspect.
