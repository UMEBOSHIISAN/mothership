# Mothership README Positioning Design

## Goal

Turn the README into an accurate, persuasive OSS entry page for Mothership:
a safety-first control plane for portable Codex CLI, Claude Code, and Ollama
Local environments that can be reviewed and recreated across machines.

## Positioning

The central promise is:

> A safety-first control plane for portable AI coding environments.

Mothership is not a full automated environment copier. It is the reusable
control layer that makes a reviewable, repeatable distribution possible:
closed contracts, fail-closed validation, advisory routing, durable approval
ledger primitives, local diagnostics, configuration templates, and explicit
authority boundaries.

## README narrative

The README will guide a visitor through this sequence:

1. See the whale-mothership banner and concise product promise.
2. Recognize the problem: personal AI CLI setups do not transfer safely or
   predictably to another Mac, teammate, or local machine.
3. Understand the solution and exactly which local adapter aliases are
   represented: `claude-code-agent`, `codex-cli`, and `ollama-local`.
4. See the common use cases: a new machine, a teammate handoff, an isolated
   mini machine, and a reproducible rebuild.
5. Follow clone, diagnostic, and test commands.
6. Learn what carries over (contracts, diagnostics, templates, evidence
   shapes) and what deliberately stays local (credentials, personal paths,
   actual model execution, and approval).
7. Explore architecture, security, installation, Japanese onboarding, FAQ,
   and contribution links.

## Content additions

`README.md` adds:

- A strong English headline and a short Japanese product summary.
- A compatibility table for the three bundled local adapter aliases.
- A capability map for contracts, advisory routing, local diagnostics,
  approval-ledger primitives, and path/configuration safety boundaries.
- Problem-to-solution explanation and four practical use cases.
- A “what travels / what stays local” comparison table.
- A compact three-step quick start plus an expanded configuration workflow.
- An architecture diagram focused on the handoff boundary.
- “What Mothership does now” versus “what it intentionally does not do.”
- FAQ entries about supported CLIs, secrets, diagnostics, changing machines,
  and the difference between an advisory result and execution.
- Contributor and release/checksum navigation.

## Ecosystem composition

The README will introduce a clearly labeled **Composable ecosystem** section.
It documents complementary public repositories without claiming automatic
installation or a runtime dependency:

| Role | Repository | Accurate relationship |
| --- | --- | --- |
| Preflight boundary | `agent-frontdoor` | Prepares and validates bounded task cards before any downstream work. |
| Control plane | `mothership` | Holds the portable contracts, advisory routing, diagnostics, and authority boundary. |
| Read-only observability | `secretary-tui` | Displays local operational state without changing it. |
| Human-friendly rituals | `git-vibes` | Adds non-blocking commit feedback; it is optional and outside the control plane. |
| Agent-system exploration | `toygarden` | Provides terminal-native visual and compositional ideas for agent-facing tools; it is an adjacent creative toolkit, not a dependency. |

The section will use a Mermaid composition map and explicit wording: each
repository can be adopted independently; Mothership does not install, invoke,
or configure any of them automatically.

`docs/ja/README.md` gains a matching Japanese positioning paragraph and a
link back to the expanded English README.

## Accuracy rules

- Say “foundation,” “reviewable,” “local,” and “advisory” where applicable.
- Do not claim automatic environment migration, model execution, hook
  installation, credential management, remote synchronization, or approval.
- Do not claim that ecosystem repositories import one another or have a
  packaged integration unless a repository artifact proves it.
- Do not use vendor logos or imply endorsement by OpenAI, Anthropic, or
  Ollama.
- Preserve the existing safety boundary, requirements, and verification
  commands.

## Verification

- Confirm all internal links and code fences after editing.
- Scan updated content for secrets and machine-specific absolute paths.
- Run the complete unittest suite with Python 3.12 or newer.
- Review the rendered GitHub README after the approved publication step.
