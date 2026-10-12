"""Read-only MCP v2.3.0 surface for bounded evidence inspection."""

from __future__ import annotations

from typing import Any

from mothership.contracts import (
    ContractError,
    validate_external_action_receipt,
    validate_receipt_verification_binding,
)

from .evidence import EvidenceError, _bounded_plain, inspect_evidence


class MCPUnavailableError(RuntimeError):
    """Raised when the optional pinned MCP SDK is not installed."""


try:  # The base Core/companion environment intentionally has no MCP SDK.
    from mcp.server import MCPServer as _MCPServer
    from mcp.server.mcpserver.exceptions import ToolError as _ToolError
except ImportError:  # pragma: no cover - exercised by the base environment
    _MCPServer = None  # type: ignore[assignment,misc]
    _ToolError = MCPUnavailableError


def _invalid() -> Exception:
    return _ToolError("invalid bounded evidence input")


def _qualified(**rows) -> dict[str, Any]:
    return {**rows, "provenance": "caller-attested", "source_authenticated": False,
            "authority": False, "external_effect_verified": False}


def build_server() -> Any:
    """Build one MCP server with only the three read-only evidence tools."""

    if _MCPServer is None:
        raise MCPUnavailableError("the pinned MCP SDK is unavailable")

    server = _MCPServer("mothership-evidence", version="0.1.0.dev0")

    @server.tool(
        description="Validate one detached external-action Receipt without granting authority."
    )
    def receipt_validate(receipt: dict[str, Any]) -> dict[str, Any]:
        try:
            _bounded_plain(receipt)
            return _qualified(receipt=validate_external_action_receipt(receipt))
        except (ContractError, TypeError, ValueError, RecursionError):
            raise _invalid() from None

    @server.tool(
        description="Validate a detached Receipt/Verification binding without external I/O."
    )
    def receipt_verification_validate(
        receipt: dict[str, Any],
        verification: dict[str, Any],
        action_id: str,
        action_sha256: str,
    ) -> dict[str, Any]:
        try:
            _bounded_plain(
                {
                    "receipt": receipt,
                    "verification": verification,
                    "action_id": action_id,
                    "action_sha256": action_sha256,
                }
            )
            checked_receipt, checked_verification = validate_receipt_verification_binding(
                receipt,
                verification,
                expected_action_id=action_id,
                expected_action_sha256=action_sha256,
            )
            return _qualified(receipt=checked_receipt, verification=checked_verification)
        except (ContractError, TypeError, ValueError, RecursionError):
            raise _invalid() from None

    @server.tool(
        description=(
            "Inspect a host-evidence-bundle.v0 projection. Results remain "
            "caller-attested and source-unverified."
        )
    )
    def evidence_inspect(bundle: dict[str, Any]) -> dict[str, Any]:
        try:
            return inspect_evidence(bundle)
        except (EvidenceError, ContractError, TypeError, ValueError, RecursionError):
            raise _invalid() from None

    return server


def main() -> int:
    """Run the MCP server over inherited stdio only."""

    try:
        server = build_server()
        server.run("stdio")
        return 0
    except MCPUnavailableError:
        return 2
    except (OSError, RuntimeError, TypeError, ValueError):
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by stdio qualification
    raise SystemExit(main())


__all__ = ["MCPUnavailableError", "build_server", "main"]
