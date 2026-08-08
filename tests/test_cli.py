from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from orchestration.lib.canonical import canonical_json_bytes


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class _Result:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CliTests(unittest.TestCase):
    def _module(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "mothership", *arguments],
            cwd=PACKAGE_ROOT,
            env=environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_verify_and_demo_commands_emit_exact_canonical_results(self) -> None:
        from mothership.demo import run_demo
        from mothership.verify import verify_installation

        cases = (
            (("verify",), verify_installation()),
            (("demo",), run_demo()),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                completed = self._module(*arguments)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(b"", completed.stderr)
                self.assertEqual(canonical_json_bytes(expected) + b"\n", completed.stdout)

    def test_protocol_list_and_validate_are_closed(self) -> None:
        from mothership.cli import command_protocol_list, command_protocol_validate

        exit_code, listing = command_protocol_list()
        self.assertEqual(0, exit_code)
        self.assertEqual("passed", listing["status"])
        self.assertEqual(
            [
                "frontdoor-task",
                "governance-handoff",
                "router-manifest",
                "observation-snapshot",
            ],
            [entry["kind"] for entry in listing["protocols"]],
        )

        source = PACKAGE_ROOT / "mothership/resources/golden-path/02-governance-handoff.json"
        exit_code, result = command_protocol_validate("governance-handoff", source)
        self.assertEqual(0, exit_code)
        self.assertEqual(
            {
                "schema_version": "mothership.protocol-validation.v1",
                "status": "passed",
                "kind": "governance-handoff",
                "protocol_version": "1.0",
                "authority_effect": False,
                "execution_effect": False,
            },
            result,
        )

    def test_protocol_failure_is_static_and_does_not_echo_path_or_value(self) -> None:
        from mothership.cli import command_protocol_validate

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-project-name.json"
            path.write_text('{"schema_version":"0","api_key":"never-print"}', encoding="utf-8")
            exit_code, result = command_protocol_validate("governance-handoff", path)
        self.assertEqual(1, exit_code)
        self.assertEqual("failed", result["status"])
        serialized = json.dumps(result)
        self.assertNotIn("private-project-name", serialized)
        self.assertNotIn("never-print", serialized)
        self.assertNotIn(str(path), serialized)

        hostile_kind = "/" + "private/never-reflect"
        exit_code, result = command_protocol_validate(hostile_kind, path)
        self.assertEqual(1, exit_code)
        self.assertEqual("unknown", result["kind"])
        self.assertNotIn("never-reflect", json.dumps(result))

    def test_doctor_uses_only_fixed_probes_and_closed_results(self) -> None:
        from mothership.cli import command_doctor

        transcript: list[tuple[str, ...]] = []
        codex_flags = b"-a --cd --color --ephemeral --ignore-rules --ignore-user-config --sandbox --skip-git-repo-check --strict-config -c"
        claude_flags = b"--disable-slash-commands --mcp-config --no-chrome --no-session-persistence --output-format --permission-mode --print --safe-mode --strict-mcp-config --tools"

        def runner(argv: tuple[str, ...]) -> _Result:
            transcript.append(argv)
            outputs = {
                ("claude", "--version"): b"claude 1\n",
                ("claude", "--help"): claude_flags,
                ("codex", "--version"): b"codex 1\n",
                ("codex", "exec", "--help"): codex_flags,
                ("ollama", "--version"): b"ollama 1\n",
                ("ollama", "list"): b"NAME ID SIZE\nfriend-core-advisory abc 1GB\n",
            }
            return _Result(stdout=outputs[argv])

        exit_code, result = command_doctor((), runner=runner)
        self.assertEqual(0, exit_code)
        self.assertEqual("passed", result["status"])
        self.assertEqual(
            [
                ("claude", "--version"),
                ("claude", "--help"),
                ("codex", "--version"),
                ("codex", "exec", "--help"),
                ("ollama", "--version"),
                ("ollama", "list"),
            ],
            transcript,
        )
        self.assertEqual(3, len(result["results"]))
        self.assertIs(False, result["authority_effect"])
        self.assertIs(False, result["execution_effect"])

    def test_invalid_and_duplicate_aliases_fail_before_runner(self) -> None:
        from mothership.cli import command_doctor

        for aliases in (("invalid",), ("codex-cli", "codex-cli")):
            runner = mock.Mock()
            with self.subTest(aliases=aliases):
                exit_code, result = command_doctor(aliases, runner=runner)
                self.assertEqual(1, exit_code)
                self.assertEqual("invalid_alias_selection", result["error"])
                runner.assert_not_called()

    def test_unavailable_diagnostic_is_exit_one_not_authority(self) -> None:
        from mothership.cli import command_doctor

        exit_code, result = command_doctor(
            ("codex-cli",),
            runner=lambda _argv: _Result(returncode=1, stderr=b"missing"),
        )
        self.assertEqual(1, exit_code)
        self.assertEqual("failed", result["status"])
        self.assertEqual("unavailable", result["results"][0]["status"])
        self.assertIs(False, result["authority_effect"])
        self.assertIs(False, result["execution_effect"])

    def test_usage_errors_exit_two_without_running_a_command(self) -> None:
        completed = self._module("protocol", "validate")
        self.assertEqual(2, completed.returncode)
        self.assertEqual(b"", completed.stdout)
        self.assertIn(b"usage:", completed.stderr)

    def test_broken_pipe_returns_one_without_traceback(self) -> None:
        from mothership.cli import main

        sink = mock.Mock()
        sink.write.side_effect = BrokenPipeError
        with mock.patch("sys.stdout", sink):
            self.assertEqual(1, main(["demo"]))


if __name__ == "__main__":
    unittest.main()
