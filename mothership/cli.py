"""Command-line entry point for the read-only Mothership hub."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence


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


def _placeholder(command: str) -> tuple[int, dict[str, str]]:
    return 1, {"command": command, "status": "not_implemented"}


def _emit(document: object) -> None:
    print(
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    command = arguments.command
    if command == "protocol":
        command = f"protocol {arguments.protocol_command}"
    exit_code, document = _placeholder(command)
    _emit(document)
    return exit_code


__all__ = ["build_parser", "main"]
