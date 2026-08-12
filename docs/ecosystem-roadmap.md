# Ecosystem roadmap

## Shipped in the Flight Recorder slice

- Flight Bundle index and event-envelope verification.
- Deterministic safe-run and scope-drift demonstrations.
- Generic JSONL import, explicit verification, replay, and Markdown reporting.
- Retained v0.2 protocol compatibility projection.

Generic JSONL is shipped because focused Flight tests exercise explicit import and verification behavior.

## Next candidates

- OpenAI Agents SDK importer.
- LangGraph importer.
- Claude Code and Codex CLI importers.
- AutoGen importer.

Candidates need stable upstream event surfaces and separate compatibility evidence. They are neither implemented adapters
nor commitments to collect runtime data.

## Not planned in this slice

- Model or agent execution, permission grants, or authority promotion.
- Automatic companion installation.
- Credential management, prompt capture, or ambient environment collection.
- Retry, repair, fallback, scheduler, daemon, deployment, or background capture services.
- Vendor, OWASP, NIST, or model-provider certification claims.
