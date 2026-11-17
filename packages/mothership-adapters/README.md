# mothership-adapters

Optional Python adapters and evidence inspection for Mothership. This package
requires the exact Core and GitHub companion versions declared in
`pyproject.toml`; install all three wheels from the same release candidate.

The wheel supplies `mothership-evidence`, `mothership-evidence-mcp`, and
`mothership-harness-handoff`. Reading saved evidence grants no action authority.
The optional Agents SDK, LangGraph, and MCP dependencies are selected through
their named extras. Node host wrappers and the Dots skill live in the repository
source tree and are not included in this Python wheel.

See the repository's [host adapter guide](../../docs/host-adapters.md) for
installation, bounded routes, and the difference between synthetic tests and
live host acceptance.
