"""Pinned MCP v2 read-only in-process and stdio qualification tests."""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile
import unittest

from test_evidence import EvidenceFixture


try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mothership_adapters.mcp_server import build_server
except ImportError:  # The base Core/companion environment has no optional MCP SDK.
    Client = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
    build_server = None  # type: ignore[assignment,misc]


@unittest.skipUnless(Client is not None, "MCP optional environment is not provisioned")
class MCPServerTests(EvidenceFixture):
    def test_inprocess_server_lists_only_readonly_tools_and_inspects(self) -> None:
        async def run() -> None:
            server = build_server()
            async with Client(server) as client:
                listed = await client.list_tools()
                self.assertEqual(
                    {
                        "receipt_validate",
                        "receipt_verification_validate",
                        "evidence_inspect",
                    },
                    {tool.name for tool in listed.tools},
                )
                bundle = self.full()
                result = await client.call_tool("evidence_inspect", {"bundle": bundle})
                self.assertFalse(result.is_error)
                self.assertEqual("caller-attested", result.structured_content["provenance"])
                self.assertFalse(result.structured_content["authority"])
                validated = await client.call_tool("receipt_validate", {"receipt": bundle["receipt"]})
                self.assertFalse(validated.is_error)
                self.assertEqual(bundle["receipt"], validated.structured_content["receipt"])
                self.assertEqual("caller-attested", validated.structured_content["provenance"])
                self.assertFalse(validated.structured_content["source_authenticated"])
                self.assertFalse(validated.structured_content["authority"])
                self.assertFalse(validated.structured_content["external_effect_verified"])
                verification = {
                    "schema_version": "external-action-verification.v0",
                    "action_id": self.action.action["action_id"],
                    "action_sha256": self.action.action_sha256,
                    "verification_method": "read_only_external_observation",
                    "observed_state": {"summary": "synthetic mismatch", "state_sha256": "d" * 64},
                    "evidence_refs": [{"ref_id": "observation:synthetic", "sha256": "e" * 64}],
                    "observed_at": self.finished["recorded_at"], "status": "MISMATCH",
                    "receipt_ref": {"ref_id": "receipt:" + self.action.action["action_id"],
                                    "sha256": bundle["source_sha256"]["request"]},
                }
                from mothership.contracts import canonical_json_sha256
                verification["receipt_ref"]["sha256"] = canonical_json_sha256(bundle["receipt"])
                binding = await client.call_tool("receipt_verification_validate", {
                    "receipt": bundle["receipt"], "verification": verification,
                    "action_id": verification["action_id"], "action_sha256": verification["action_sha256"],
                })
                self.assertFalse(binding.is_error)
                self.assertEqual("SUCCESS", binding.structured_content["receipt"]["status"])
                self.assertEqual("MISMATCH", binding.structured_content["verification"]["status"])
                self.assertFalse(binding.structured_content["source_authenticated"])
                self.assertFalse(binding.structured_content["authority"])
                self.assertFalse(binding.structured_content["external_effect_verified"])
                invalid = await client.call_tool("receipt_validate", {"receipt": {"path": "/tmp/x"}})
                self.assertTrue(invalid.is_error)
                unknown = await client.call_tool("execute", {})
                self.assertTrue(unknown.is_error)

        asyncio.run(run())

    def test_stdio_server_roundtrip_is_local_and_readonly(self) -> None:
        async def run() -> None:
            package_root = pathlib.Path(__file__).resolve().parents[3]
            env = {
                "PYTHONPATH": os.pathsep.join(
                    [
                        str(package_root),
                        str(package_root / "packages" / "mothership-github"),
                        str(package_root / "packages" / "mothership-adapters"),
                    ]
                )
            }
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "mothership_adapters.mcp_server"],
                env=env,
                cwd=str(package_root),
            )
            async with Client(params) as client:
                result = await client.call_tool(
                    "evidence_inspect", {"bundle": self.full()}
                )
                self.assertFalse(result.is_error)
                self.assertEqual("source-unverified", result.structured_content["source_status"])

        asyncio.run(run())

    def test_all_invalid_stdio_tools_return_finite_errors_without_tracebacks(self) -> None:
        async def run() -> None:
            root = pathlib.Path(__file__).resolve().parents[3]
            params = StdioServerParameters(command=sys.executable,
                args=["-m", "mothership_adapters.mcp_server"], cwd=str(root),
                env={"PYTHONPATH": os.pathsep.join([str(root), str(root / "packages/mothership-github"),
                                                  str(root / "packages/mothership-adapters")])})
            with tempfile.TemporaryFile(mode="w+") as errors:
                async with Client(stdio_client(params, errlog=errors)) as client:
                    cases = [("receipt_validate", {"receipt": {}}),
                        ("receipt_verification_validate", {"receipt": {}, "verification": {},
                         "action_id": "x", "action_sha256": "a" * 64}),
                        ("evidence_inspect", {"bundle": {}}),
                        ("evidence_inspect", {"bundle": {"oversized": "x" * 262145}})]
                    for name, arguments in cases:
                        result = await client.call_tool(name, arguments)
                        self.assertTrue(result.is_error)
                        text = " ".join(row.text for row in result.content if hasattr(row, "text"))
                        self.assertIn("invalid bounded evidence input", text)
                        self.assertNotIn("/Users/", text)
                errors.seek(0)
                diagnostic = errors.read()
                self.assertNotIn("Traceback", diagnostic)
                self.assertNotIn(".py", diagnostic)
                self.assertNotIn("/Users/", diagnostic)
        asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
