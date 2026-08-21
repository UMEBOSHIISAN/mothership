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

    def test_usage_errors_exit_two_without_running_a_command(self) -> None:
        completed = self._module("protocol", "validate")
        self.assertEqual(2, completed.returncode)
        self.assertEqual(b"", completed.stdout)
        self.assertIn(b"usage:", completed.stderr)

    def _write_decision_inputs(
        self,
        directory: Path,
        *,
        request_id: str,
        human_gate: str,
        risk: str,
        unknowns: list[str] | None = None,
    ) -> tuple[Path, Path, Path]:
        frontdoor = json.loads(
            (PACKAGE_ROOT / "mothership/resources/golden-path/01-frontdoor-task.json").read_text(
                encoding="utf-8"
            )
        )
        handoff = json.loads(
            (PACKAGE_ROOT / "mothership/resources/golden-path/02-governance-handoff.json").read_text(
                encoding="utf-8"
            )
        )
        router = json.loads(
            (PACKAGE_ROOT / "mothership/resources/golden-path/03-router-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        frontdoor.update(
            request_id=request_id,
            human_gate=human_gate,
            unknowns=[] if unknowns is None else unknowns,
        )
        handoff.update(task_id=request_id, risk=risk)
        router.update(task_id=request_id)
        paths = (
            directory / f"{request_id}-frontdoor.json",
            directory / f"{request_id}-handoff.json",
            directory / f"{request_id}-router.json",
        )
        for path, document in zip(paths, (frontdoor, handoff, router), strict=True):
            path.write_text(json.dumps(document), encoding="utf-8")
        return paths

    def test_decision_batch_cli_renders_card_with_optional_router_and_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name).resolve()
            frontdoor, handoff, router = self._write_decision_inputs(
                directory,
                request_id="cli-card-001",
                human_gate="CONFIRM",
                risk="low",
                unknowns=["scope is not yet confirmed"],
            )
            before = set(directory.iterdir())
            completed = self._module(
                "decision-batch",
                "--frontdoor",
                str(frontdoor),
                "--wgm",
                str(handoff),
                "--router",
                str(router),
                "--question",
                "Should the human review this item?",
                "--consequence-if-approved",
                "The separately owned next boundary may be considered.",
            )
            after = set(directory.iterdir())

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(b"", completed.stderr)
        output = completed.stdout.decode("utf-8")
        self.assertIn("EPHEMERAL DECISION BATCH", output)
        self.assertIn("DECISION_CARD (1)", output)
        self.assertIn("router-manifest.recommended_alias", output)
        self.assertIn("scope is not yet confirmed", output)
        self.assertIn("authority_effect: false", output)
        self.assertIn("execution_effect: false", output)
        self.assertEqual(before, after)

    def test_decision_batch_cli_keeps_multiple_outcomes_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name).resolve()
            card = self._write_decision_inputs(
                directory,
                request_id="cli-card-002",
                human_gate="CONFIRM",
                risk="low",
            )
            no_card = self._write_decision_inputs(
                directory,
                request_id="cli-no-card-001",
                human_gate="NONE",
                risk="low",
            )
            fail_closed = self._write_decision_inputs(
                directory,
                request_id="cli-fail-closed-001",
                human_gate="NONE",
                risk="high",
            )
            arguments = ["decision-batch"]
            for paths, question in (
                (card, "Should the card item be reviewed?"),
                (no_card, "Should the ordinary item be reviewed?"),
                (fail_closed, "Should the high-risk item be reviewed?"),
            ):
                frontdoor, handoff, _router = paths
                arguments.extend(
                    (
                        "--frontdoor",
                        str(frontdoor),
                        "--wgm",
                        str(handoff),
                        "--question",
                        question,
                        "--consequence-if-approved",
                        "The separately owned next boundary may be considered.",
                    )
                )
            before = set(directory.iterdir())
            completed = self._module(*arguments)
            after = set(directory.iterdir())

        self.assertEqual(1, completed.returncode)
        self.assertEqual(b"", completed.stderr)
        output = completed.stdout.decode("utf-8")
        self.assertIn("DECISION_CARD (1)", output)
        self.assertIn("NO_CARD (1)", output)
        self.assertIn("FAIL_CLOSED (1)", output)
        self.assertIn("high-risk", output)
        self.assertIn("SUMMARY: inputs=3 cards=1 no_card=1 fail_closed=1", output)
        self.assertEqual(before, after)

    def test_decision_card_cli_emits_the_existing_card_contract_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name).resolve()
            frontdoor, handoff, router = self._write_decision_inputs(
                directory,
                request_id="cli-card-json-001",
                human_gate="CONFIRM",
                risk="medium",
                unknowns=["scope is not yet confirmed"],
            )
            completed = self._module(
                "decision-card",
                "--frontdoor",
                str(frontdoor),
                "--wgm",
                str(handoff),
                "--router",
                str(router),
                "--question",
                "Should the human review this item?",
                "--consequence-if-approved",
                "The separately owned next boundary may be considered.",
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(b"", completed.stderr)
        card = json.loads(completed.stdout)
        self.assertEqual(
            [
                "authority_effect",
                "authority_required",
                "consequence_if_approved",
                "decision_id",
                "evidence_refs",
                "execution_effect",
                "question",
                "reasons",
                "recommendation",
                "risk",
                "schema_version",
                "task_id",
                "unknowns",
            ],
            sorted(card),
        )
        self.assertEqual("decision-card.v0", card["schema_version"])
        self.assertEqual("cli-card-json-001", card["decision_id"])
        self.assertEqual("cli-card-json-001", card["task_id"])
        self.assertEqual("fictional-code-reviewer", card["recommendation"])
        self.assertEqual(["scope is not yet confirmed"], card["unknowns"])
        self.assertIs(False, card["authority_effect"])
        self.assertIs(False, card["execution_effect"])
        self.assertEqual(canonical_json_bytes(card) + b"\n", completed.stdout)

    def test_decision_card_cli_fails_closed_without_fabricating_no_card_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name).resolve()
            frontdoor, handoff, _router = self._write_decision_inputs(
                directory,
                request_id="cli-no-card-json-001",
                human_gate="NONE",
                risk="low",
            )
            completed = self._module(
                "decision-card",
                "--frontdoor",
                str(frontdoor),
                "--wgm",
                str(handoff),
                "--question",
                "Should the ordinary item be reviewed?",
                "--consequence-if-approved",
                "The separately owned next boundary may be considered.",
            )

        self.assertEqual(1, completed.returncode)
        self.assertEqual(b"", completed.stdout)
        self.assertNotEqual(b"", completed.stderr)

    def test_broken_pipe_returns_one_without_traceback(self) -> None:
        from mothership.cli import main

        sink = mock.Mock()
        sink.write.side_effect = BrokenPipeError
        with mock.patch("sys.stdout", sink):
            self.assertEqual(1, main(["demo"]))


if __name__ == "__main__":
    unittest.main()
