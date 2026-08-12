"""Command-line entry point for the read-only Mothership hub."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
from collections.abc import Sequence
from collections.abc import Callable
import sys

from orchestration.lib.adapters import _ALIASES, _diagnostic_environment, doctor_adapter
from orchestration.lib.canonical import canonical_json_bytes

from .demo import DemoError, run_demo
from .flight_contracts import FlightError
from .flight_demo import run_flight_demo
from .flight_io import import_generic_jsonl, load_flight_bundle
from .flight_render import render_markdown_report, replay_document
from .flight_verify import evaluate_flight, evaluation_document
from .protocols import ProtocolError, list_protocols, validate_protocol_file
from .verify import verify_installation


_DIAGNOSTIC_TIMEOUT_SECONDS = 5
_PROTOCOL_KINDS = frozenset(
    {
        "frontdoor-task",
        "governance-handoff",
        "router-manifest",
        "observation-snapshot",
    }
)
FLIGHT_EXIT_CODES = {
    "COMPLETE": 0,
    "INCOMPLETE": 20,
    "DRIFTED": 21,
    "INVALID": 22,
}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="mothership",
        description="Verify and inspect a portable AI coding control plane.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="verify installed package resources")
    verify_commands = verify.add_subparsers(dest="verify_command")
    verify_run = verify_commands.add_parser("run", help="evaluate one explicit Flight bundle")
    verify_run.add_argument("bundle")

    doctor = commands.add_parser("doctor", help="run fixed local diagnostics")
    doctor.add_argument("aliases", nargs="*")

    protocol = commands.add_parser("protocol", help="inspect suite protocols")
    protocol_commands = protocol.add_subparsers(
        dest="protocol_command",
        required=True,
    )
    protocol_commands.add_parser("list", help="list bundled protocols")
    validate = protocol_commands.add_parser(
        "validate",
        help="validate one explicit local JSON file",
    )
    validate.add_argument("kind")
    validate.add_argument("file")

    flight_import = commands.add_parser("import", help="import a Generic JSONL Flight record")
    import_commands = flight_import.add_subparsers(dest="import_command", required=True)
    generic_import = import_commands.add_parser("generic", help="import Generic JSONL")
    generic_import.add_argument("source")
    generic_import.add_argument("--out", required=True)

    replay = commands.add_parser("replay", help="project one explicit Flight bundle")
    replay.add_argument("bundle")

    report = commands.add_parser("report", help="render one explicit Flight bundle")
    report.add_argument("bundle")
    report.add_argument("--format", choices=("markdown",), required=True)

    demo = commands.add_parser("demo", help="validate the synthetic golden path")
    demo_commands = demo.add_subparsers(dest="demo_command")
    demo_commands.add_parser("safe", help="evaluate the supplied safe Flight record")
    demo_commands.add_parser("drift", help="evaluate the supplied drift Flight record")
    return parser


def _runner(argv: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        shell=False,
        cwd="/",
        env=_diagnostic_environment(os.environ),
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=_DIAGNOSTIC_TIMEOUT_SECONDS,
    )


def command_verify() -> tuple[int, dict[str, object]]:
    result = verify_installation()
    return (0 if result["status"] == "passed" else 1), result


def command_doctor(
    aliases: tuple[str, ...],
    *,
    runner: Callable[[tuple[str, ...]], object] = _runner,
) -> tuple[int, dict[str, object]]:
    requested = aliases if aliases else _ALIASES
    if (
        any(type(alias) is not str or alias not in _ALIASES for alias in requested)
        or len(set(requested)) != len(requested)
    ):
        return 1, {
            "schema_version": "mothership.doctor.v1",
            "status": "failed",
            "error": "invalid_alias_selection",
            "results": [],
            "authority_effect": False,
            "execution_effect": False,
        }
    results = [doctor_adapter(alias, runner) for alias in requested]
    passed = all(result["status"] == "available" for result in results)
    return (0 if passed else 1), {
        "schema_version": "mothership.doctor.v1",
        "status": "passed" if passed else "failed",
        "results": results,
        "authority_effect": False,
        "execution_effect": False,
    }


def command_protocol_list() -> tuple[int, dict[str, object]]:
    try:
        protocols = list(list_protocols())
    except ProtocolError:
        return 1, {
            "schema_version": "mothership.protocol-list.v1",
            "status": "failed",
            "error": "protocol_registry_invalid",
            "protocols": [],
            "authority_effect": False,
            "execution_effect": False,
        }
    return 0, {
        "schema_version": "mothership.protocol-list.v1",
        "status": "passed",
        "protocols": protocols,
        "authority_effect": False,
        "execution_effect": False,
    }


def command_protocol_validate(
    kind: str,
    path: Path,
) -> tuple[int, dict[str, object]]:
    try:
        document = validate_protocol_file(kind, path)
    except ProtocolError:
        return 1, {
            "schema_version": "mothership.protocol-validation.v1",
            "status": "failed",
            "kind": kind if type(kind) is str and kind in _PROTOCOL_KINDS else "unknown",
            "error": "protocol_validation_failed",
            "authority_effect": False,
            "execution_effect": False,
        }
    return 0, {
        "schema_version": "mothership.protocol-validation.v1",
        "status": "passed",
        "kind": kind,
        "protocol_version": document["schema_version"],
        "authority_effect": False,
        "execution_effect": False,
    }


def command_demo() -> tuple[int, dict[str, object]]:
    try:
        return 0, run_demo()
    except (DemoError, ProtocolError):
        return 1, {
            "schema_version": "mothership.demo.v1",
            "status": "failed",
            "error": "golden_path_invalid",
            "authority_effect": False,
            "execution_effect": False,
            "claim": "protocol-composition-only",
        }


def _flight_error_document(verdict: str, rule_id: str) -> dict[str, object]:
    return {
        "schema_version": "mothership.flight-error.v1",
        "verdict": verdict,
        "rule_id": rule_id,
        "authority_effect": False,
        "execution_effect": False,
    }


def _flight_failure(error: FlightError) -> tuple[int, dict[str, object]]:
    return (
        FLIGHT_EXIT_CODES[error.verdict],
        _flight_error_document(error.verdict, error.rule_id),
    )


def _flight_internal_failure() -> tuple[int, dict[str, object]]:
    return 70, _flight_error_document("INVALID", "FLIGHT.INTERNAL")


def command_flight_import(source: Path, output: Path) -> tuple[int, dict[str, object]]:
    try:
        bundle = import_generic_jsonl(source, output)
    except FlightError as error:
        return _flight_failure(error)
    except (OSError, UnicodeError):
        return _flight_internal_failure()
    return 0, {
        "schema_version": "mothership.flight-import.v1",
        "output": output.name,
        "run_id": bundle.index["run_id"],
        "bundle_sha256": bundle.index["bundle_sha256"],
        "event_count": len(bundle.events),
        "authority_effect": False,
        "execution_effect": False,
    }


def command_verify_run(path: Path) -> tuple[int, dict[str, object]]:
    try:
        evaluation = evaluate_flight(load_flight_bundle(path))
    except FlightError as error:
        return _flight_failure(error)
    except (OSError, UnicodeError):
        return _flight_internal_failure()
    return FLIGHT_EXIT_CODES[evaluation.verdict], evaluation_document(evaluation)


def command_replay(path: Path) -> tuple[int, dict[str, object]]:
    try:
        bundle = load_flight_bundle(path)
        evaluation = evaluate_flight(bundle)
        document = replay_document(bundle, evaluation)
    except FlightError as error:
        return _flight_failure(error)
    except (OSError, UnicodeError):
        return _flight_internal_failure()
    return FLIGHT_EXIT_CODES[evaluation.verdict], document


def command_report(path: Path) -> tuple[int, str | dict[str, object]]:
    try:
        bundle = load_flight_bundle(path)
        evaluation = evaluate_flight(bundle)
        report = render_markdown_report(bundle, evaluation)
    except FlightError as error:
        return _flight_failure(error)
    except (OSError, UnicodeError):
        return _flight_internal_failure()
    return FLIGHT_EXIT_CODES[evaluation.verdict], report


def command_flight_demo(name: str) -> tuple[int, dict[str, object]]:
    try:
        document = run_flight_demo(name)
    except FlightError as error:
        return _flight_failure(error)
    except (OSError, UnicodeError):
        return _flight_internal_failure()
    return FLIGHT_EXIT_CODES[document["verdict"]], document


def _flight_path(value: str) -> Path:
    absolute = os.path.abspath(value)
    if absolute.startswith("//"):
        absolute = "/" + absolute.lstrip("/")
    return Path(absolute)


def _emit(document: object) -> bool:
    try:
        sys.stdout.write(canonical_json_bytes(document).decode("utf-8") + "\n")
        return True
    except (BrokenPipeError, OSError, UnicodeError, ValueError):
        return False


def _emit_text(document: str) -> bool:
    try:
        sys.stdout.write(document)
        return True
    except (BrokenPipeError, OSError, UnicodeError):
        return False


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    text_output = False
    if arguments.command == "verify" and arguments.verify_command is None:
        exit_code, document = command_verify()
    elif arguments.command == "verify":
        exit_code, document = command_verify_run(_flight_path(arguments.bundle))
    elif arguments.command == "doctor":
        exit_code, document = command_doctor(tuple(arguments.aliases))
    elif arguments.command == "import":
        exit_code, document = command_flight_import(
            _flight_path(arguments.source),
            _flight_path(arguments.out),
        )
    elif arguments.command == "replay":
        exit_code, document = command_replay(_flight_path(arguments.bundle))
    elif arguments.command == "report":
        exit_code, document = command_report(_flight_path(arguments.bundle))
        text_output = isinstance(document, str)
    elif arguments.command == "demo" and arguments.demo_command is None:
        exit_code, document = command_demo()
    elif arguments.command == "demo":
        exit_code, document = command_flight_demo(arguments.demo_command)
    elif arguments.protocol_command == "list":
        exit_code, document = command_protocol_list()
    else:
        exit_code, document = command_protocol_validate(
            arguments.kind,
            Path(arguments.file),
        )
    emitted = _emit_text(document) if text_output else _emit(document)
    if not emitted:
        return 1
    return exit_code


__all__ = (
    "build_parser",
    "command_flight_demo",
    "command_flight_import",
    "command_demo",
    "command_doctor",
    "command_protocol_list",
    "command_protocol_validate",
    "command_replay",
    "command_report",
    "command_verify",
    "command_verify_run",
    "main",
)
