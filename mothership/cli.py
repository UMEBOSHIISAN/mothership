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
from .protocols import ProtocolError, list_protocols, validate_protocol_file
from .verify import verify_installation


_PROTOCOL_KINDS = frozenset(
    {
        "frontdoor-task",
        "governance-handoff",
        "router-manifest",
        "observation-snapshot",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mothership",
        description="Verify and inspect a portable AI coding control plane.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="verify installed package resources")

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

    commands.add_parser("demo", help="validate the synthetic golden path")
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


def _emit(document: object) -> bool:
    try:
        sys.stdout.write(canonical_json_bytes(document).decode("utf-8") + "\n")
        return True
    except (BrokenPipeError, OSError, UnicodeError, ValueError):
        return False


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "verify":
        exit_code, document = command_verify()
    elif arguments.command == "doctor":
        exit_code, document = command_doctor(tuple(arguments.aliases))
    elif arguments.command == "demo":
        exit_code, document = command_demo()
    elif arguments.protocol_command == "list":
        exit_code, document = command_protocol_list()
    else:
        exit_code, document = command_protocol_validate(
            arguments.kind,
            Path(arguments.file),
        )
    if not _emit(document):
        return 1
    return exit_code


__all__ = (
    "build_parser",
    "command_demo",
    "command_doctor",
    "command_protocol_list",
    "command_protocol_validate",
    "command_verify",
    "main",
)
