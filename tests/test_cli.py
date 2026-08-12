from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from orchestration.lib.canonical import canonical_json_bytes


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FLIGHT_RESOURCES = PACKAGE_ROOT / "mothership/resources/flight"


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
                "protocol_version": "1.1",
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

    def test_default_doctor_runner_has_a_fixed_timeout_and_fails_closed(self) -> None:
        from mothership import cli

        completed = subprocess.CompletedProcess(("codex", "--version"), 0, b"codex 1\n", b"")
        with mock.patch.object(cli.subprocess, "run", return_value=completed) as run:
            self.assertIs(completed, cli._runner(("codex", "--version")))
        self.assertEqual(5, run.call_args.kwargs["timeout"])

        with mock.patch.object(
            cli.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(("codex", "--version"), 5),
        ):
            exit_code, result = cli.command_doctor(("codex-cli",))
        self.assertEqual(1, exit_code)
        self.assertEqual("unavailable", result["results"][0]["status"])
        self.assertIs(False, result["authority_effect"])
        self.assertIs(False, result["execution_effect"])

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

    def test_usage_errors_exit_sixty_four_without_running_a_command(self) -> None:
        completed = self._module("protocol", "validate")
        self.assertEqual(64, completed.returncode)
        self.assertEqual(b"", completed.stdout)
        self.assertIn(b"usage:", completed.stderr)

    def test_broken_pipe_returns_one_without_traceback(self) -> None:
        from mothership import cli

        sink = mock.Mock()
        sink.write.side_effect = BrokenPipeError
        with mock.patch("sys.stdout", sink):
            self.assertEqual(1, cli.main(["demo"]))
        with mock.patch.object(cli, "command_report", return_value=(0, "# report\n")), mock.patch("sys.stdout", sink):
            self.assertEqual(1, cli.main(["report", "bundle", "--format", "markdown"]))

    def test_flight_process_commands_keep_json_and_markdown_boundaries_closed(self) -> None:
        """Catches a process command that emits a report as JSON or adds stderr to a normal verdict."""

        safe = str((FLIGHT_RESOURCES / "safe-run").resolve())
        drift = str((FLIGHT_RESOURCES / "scope-drift").resolve())
        double_safe = "//" + safe.lstrip("/")
        for arguments, expected_exit, schema in (
            (("verify", "run", double_safe), 0, "mothership.flight-verdict.v1"),
            (("replay", double_safe), 0, "mothership.flight-replay.v1"),
            (("demo", "safe"), 0, "mothership.flight-demo.v1"),
            (("demo", "drift"), 21, "mothership.flight-demo.v1"),
        ):
            with self.subTest(arguments=arguments):
                completed = self._module(*arguments)
                self.assertEqual(expected_exit, completed.returncode, completed.stderr)
                self.assertEqual(b"", completed.stderr)
                self.assertEqual(schema, json.loads(completed.stdout)["schema_version"])

        report = self._module("report", double_safe, "--format", "markdown")
        self.assertEqual(0, report.returncode, report.stderr)
        self.assertEqual(b"", report.stderr)
        self.assertTrue(report.stdout.startswith(b"# Mothership Flight Report\n"))
        drift_report = self._module("report", drift, "--format", "markdown")
        self.assertEqual(21, drift_report.returncode, drift_report.stderr)
        self.assertEqual(b"", drift_report.stderr)
        self.assertTrue(drift_report.stdout.startswith(b"# Mothership Flight Report\n"))

    def test_flight_commands_evaluate_prepared_bundles_without_process_or_network_use(self) -> None:
        """Catches a CLI handler that launches a process or network client instead of reading supplied records."""

        from mothership import cli

        safe = (FLIGHT_RESOURCES / "safe-run").resolve()
        drift = (FLIGHT_RESOURCES / "scope-drift").resolve()
        with mock.patch.object(cli.subprocess, "run", side_effect=AssertionError("process use is forbidden")), mock.patch(
            "socket.socket", side_effect=AssertionError("network use is forbidden")
        ):
            for handler, path, verdict, schema in (
                (cli.command_verify_run, safe, "COMPLETE", "mothership.flight-verdict.v1"),
                (cli.command_replay, safe, "COMPLETE", "mothership.flight-replay.v1"),
                (cli.command_verify_run, drift, "DRIFTED", "mothership.flight-verdict.v1"),
            ):
                with self.subTest(handler=handler.__name__, path=path.name):
                    exit_code, document = handler(path)
                    self.assertEqual({"COMPLETE": 0, "DRIFTED": 21}[verdict], exit_code)
                    self.assertEqual(schema, document["schema_version"])
                    self.assertEqual(verdict, document["verdict"])
                    self.assertIs(False, document["authority_effect"])
                    self.assertIs(False, document["execution_effect"])

            exit_code, report = cli.command_report(safe)
            self.assertEqual(0, exit_code)
            self.assertTrue(report.startswith("# Mothership Flight Report\n"))
            self.assertIn("- Verdict: COMPLETE\n", report)

            exit_code, demo = cli.command_flight_demo("drift")
            self.assertEqual(21, exit_code)
            self.assertEqual("DRIFTED", demo["verdict"])

    def test_verify_run_maps_all_verdicts_and_sanitizes_failures(self) -> None:
        """Catches an incorrect verdict exit or a failure response that reflects a supplied private path."""

        from mothership.cli import command_verify_run
        from mothership.flight_io import bundle_digest, load_flight_bundle

        safe = (FLIGHT_RESOURCES / "safe-run").resolve()
        drift = (FLIGHT_RESOURCES / "scope-drift").resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            incomplete = root / "incomplete"
            shutil.copytree(safe, incomplete)
            events = [json.loads(line) for line in (incomplete / "events.jsonl").read_text("utf-8").splitlines()]
            events.pop()
            event_bytes = b"".join(canonical_json_bytes(event) + b"\n" for event in events)
            index = json.loads((incomplete / "flight.json").read_text("utf-8"))
            index["event_ids"] = [event["event_id"] for event in events]
            index["declared_verdict"] = "INCOMPLETE"
            (incomplete / "artifacts/persistence.json").unlink()
            index["bundle_sha256"] = bundle_digest(
                index,
                event_bytes,
                tuple(
                    row
                    for row in load_flight_bundle(safe).artifacts
                    if row[0] != "artifacts/persistence.json"
                ),
            )
            (incomplete / "events.jsonl").write_bytes(event_bytes)
            (incomplete / "flight.json").write_bytes(canonical_json_bytes(index))

            invalid = root / "private-secret-bundle"
            shutil.copytree(safe, invalid)
            (invalid / "events.jsonl").write_bytes(b'{"secret":"never-print"}\n')

            for path, expected_exit, expected_verdict in (
                (safe, 0, "COMPLETE"),
                (incomplete, 20, "INCOMPLETE"),
                (drift, 21, "DRIFTED"),
                (invalid, 22, "INVALID"),
            ):
                with self.subTest(path=path.name):
                    exit_code, document = command_verify_run(path)
                    self.assertEqual(expected_exit, exit_code)
                    self.assertEqual(expected_verdict, document["verdict"])

        exit_code, document = command_verify_run(Path("/private-secret-bundle"))
        self.assertEqual(22, exit_code)
        self.assertEqual(
            {
                "schema_version": "mothership.flight-error.v1",
                "verdict": "INVALID",
                "rule_id": "FLIGHT.INVALID.FILE",
                "authority_effect": False,
                "execution_effect": False,
            },
            document,
        )
        self.assertNotIn("private-secret-bundle", json.dumps(document))

    def test_import_and_main_normalize_only_explicit_paths(self) -> None:
        """Catches a Flight I/O path passed through relatively or an import response that exposes an absolute output path."""

        from mothership import cli

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "generic.jsonl"
            events = [
                dict(
                    json.loads(line),
                    schema_version="mothership.generic-event.v1",
                    subject=dict(json.loads(line)["subject"], storage="external", location="refs/event.json"),
                )
                for line in (FLIGHT_RESOURCES / "safe-run/events.jsonl").read_text("utf-8").splitlines()
            ]
            source.write_bytes(b"".join(canonical_json_bytes(event) + b"\n" for event in events))
            output = root / "created-bundle"
            exit_code, document = cli.command_flight_import(source, output)
            self.assertEqual(0, exit_code)
            self.assertEqual(
                {
                    "schema_version": "mothership.flight-import.v1",
                    "output": "created-bundle",
                    "run_id": "flight-safe-001",
                    "bundle_sha256": document["bundle_sha256"],
                    "event_count": 8,
                    "authority_effect": False,
                    "execution_effect": False,
                },
                document,
            )
            self.assertNotIn(str(root), json.dumps(document))

            process_output = root / "double-source-bundle"
            completed = self._module(
                "import",
                "generic",
                "//" + str(source).lstrip("/"),
                "--out",
                str(process_output),
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(b"", completed.stderr)
            self.assertEqual("double-source-bundle", json.loads(completed.stdout)["output"])
            self.assertTrue(process_output.is_dir())

            double_output = root / "double-output-bundle"
            completed = self._module(
                "import",
                "generic",
                str(source),
                "--out",
                "//" + str(double_output).lstrip("/"),
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(b"", completed.stderr)
            self.assertEqual("double-output-bundle", json.loads(completed.stdout)["output"])
            self.assertTrue(double_output.is_dir())

        received: list[Path] = []
        with mock.patch.object(cli, "command_verify_run", side_effect=lambda path: (received.append(path), (0, {}))[1]), mock.patch.object(
            cli, "_emit", return_value=True
        ):
            self.assertEqual(0, cli.main(["verify", "run", "relative-bundle"]))
        self.assertEqual([(Path.cwd() / "relative-bundle").resolve()], received)


if __name__ == "__main__":
    unittest.main()
