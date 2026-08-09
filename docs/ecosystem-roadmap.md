# Ecosystem roadmap

This roadmap separates shipped behavior from candidates. It does not promise dates, adoption, publication, or automatic
integration.

## Shipped in 0.2.0

- Installable `mothership-control-plane` package with zero runtime dependencies.
- Public `verify`, `doctor`, `protocol`, and `demo` commands.
- Compatibility facades for scope, approval evidence, adapters, and contracts.
- Frozen four-stage protocol registry and schema digests.
- Deterministic `protocol-composition-only` golden path.
- Synthetic evaluation corpus and machine-readable result.
- English product page, research claim boundaries, and verification evidence.

## Next candidates

- Companion-owned conformance manifests tied to exact public releases.
- A standardized sanitized observation export in Secretary TUI.
- Cross-platform replication for declared Python and operating-system combinations.
- An independently authored or blinded request corpus for external evaluation.
- Artifact-paper materials, baselines, ablations, and third-party reproduction.

Candidates remain unshipped until implemented and verified. Companion projects stay independently adoptable; Mothership
remains the installable hub.

## Not planned

- automatic companion installation;
- model or agent execution;
- retry or fallback engine;
- credential management;
- background service, daemon, scheduler, or hook manager;
- automatic approval, executor selection, deployment, or external publishing;
- inference that `authority_effect` or `execution_effect` became true from validation.

Changing these exclusions requires a new design and explicit human decision. They are not TODO items hidden behind the
current roadmap.
