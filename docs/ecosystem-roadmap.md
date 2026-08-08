# Ecosystem roadmap

This roadmap distinguishes released public software from future exploration.
It does not promise a bundled product, automatic setup, shared credentials, or
authority between repositories.

| Item | Status | Scope |
| --- | --- | --- |
| [Mothership](../README.md) | Released | A portable, safety-first control plane with public contracts, local diagnostics, and reviewable configuration templates. |
| Workflow Governance Model | Planned | A clean-room set of generic governance templates, to be developed only after careful anonymization and independent verification. |

## Planned: Workflow Governance Model

The Workflow Governance Model is a future clean-room extraction target, not a
released component or an integration with Mothership. It may offer generic
templates for the following patterns:

- **Decision Record Gate**: a reviewable template for recording a decision,
  its evidence, and its required human approval.
- **Authority Boundary Framework**: a template for making scope, permissions,
  and escalation limits explicit before work proceeds.
- **Context & Memory Trust Patterns**: templates for describing what context
  may be relied on, what must be re-verified, and how uncertainty is surfaced.

Any future template must be anonymized before publication and independently
verified for accuracy, safety, and portability. It must contain no private
operational material, business data, credentials, machine-specific details, or
claims of authority over another repository.
