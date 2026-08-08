# Ecosystem roadmap

This roadmap distinguishes released public software from future exploration.
It does not promise a bundled product, automatic setup, shared credentials, or
authority between repositories.

| Item | Status | Scope |
| --- | --- | --- |
| [Mothership](../README.md) | Released | A portable, safety-first control plane with public contracts, local diagnostics, and reviewable configuration templates. |
| [Workflow Governance Model](https://github.com/UMEBOSHIISAN/workflow-governance-model) | Released | A clean-room, fail-closed library for validating workflow evidence and authority trails, with non-executing candidate recommendation. |

## Released: Workflow Governance Model

The Workflow Governance Model is a clean-room public component. It remains
independently installable and has no runtime integration with Mothership. It
provides portable validation and reference patterns for:

- **Decision Record Gate**: a reviewable template for recording a decision,
  its evidence, and its required human approval.
- **Authority Boundary Framework**: a template for making scope, permissions,
  and escalation limits explicit before work proceeds.
- **Context & Memory Trust Patterns**: templates for describing what context
  may be relied on, what must be re-verified, and how uncertainty is surfaced.

Future additions must be anonymized before publication and independently
verified for accuracy, safety, and portability. They must contain no private
operational material, business data, credentials, machine-specific details, or
claims of authority over another repository.
