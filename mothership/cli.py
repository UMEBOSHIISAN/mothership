"""Command-line entry point for the read-only Mothership hub."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from collections.abc import Sequence
from collections.abc import Callable
import sys

from orchestration.lib.adapters import _ALIASES, _diagnostic_environment, doctor_adapter
from orchestration.lib.canonical import canonical_json_bytes
from orchestration.lib.decision import (
    DecisionCardProductionError,
    build_decision_batch,
    build_decision_card,
    format_decision_batch,
)

from .demo import DemoError, run_demo
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

    decision_card = commands.add_parser(
        "decision-card",
        help="emit one validated decision-card.v0 JSON object",
    )
    decision_card.add_argument(
        "--frontdoor",
        type=Path,
        required=True,
        help="absolute Frontdoor intake JSON path",
    )
    decision_card.add_argument(
        "--wgm",
        type=Path,
        required=True,
        help="absolute WGM handoff JSON path",
    )
    decision_card.add_argument(
        "--router",
        type=Path,
        help="optional absolute Router manifest JSON path",
    )
    decision_card.add_argument(
        "--question",
        required=True,
        help="explicit human-facing question",
    )
    decision_card.add_argument(
        "--recommendation",
        help="optional explicit human-facing recommendation",
    )
    decision_card.add_argument(
        "--reason",
        dest="reasons",
        action="append",
        default=[],
        help="explicit human-facing reason; repeat as needed",
    )
    decision_card.add_argument(
        "--consequence-if-approved",
        required=True,
        help="explicit presentation-only consequence",
    )

    decision_batch = commands.add_parser(
        "decision-batch",
        help="render an ephemeral human decision batch",
    )
    decision_batch.add_argument(
        "--frontdoor",
        dest="frontdoor_paths",
        action="append",
        type=Path,
        required=True,
        help="absolute Frontdoor intake JSON path; repeat for more inputs",
    )
    decision_batch.add_argument(
        "--wgm",
        dest="wgm_paths",
        action="append",
        type=Path,
        required=True,
        help="absolute WGM handoff JSON path; repeat for more inputs",
    )
    decision_batch.add_argument(
        "--router",
        dest="router_paths",
        action="append",
        type=Path,
        help="optional absolute Router manifest JSON path",
    )
    decision_batch.add_argument(
        "--question",
        dest="questions",
        action="append",
        required=True,
        help="explicit human-facing question; repeat per input",
    )
    decision_batch.add_argument(
        "--recommendation",
        dest="recommendations",
        action="append",
        help="explicit human-facing recommendation; repeat once per input",
    )
    decision_batch.add_argument(
        "--reasons-json",
        dest="reasons_json",
        action="append",
        help="JSON array of explicit reasons; repeat once per input",
    )
    decision_batch.add_argument(
        "--consequence-if-approved",
        dest="consequences",
        action="append",
        required=True,
        help="explicit presentation-only consequence; repeat per input",
    )
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


def _load_decision_protocol(kind: str, path: Path) -> tuple[object, bool]:
    try:
        return validate_protocol_file(kind, path), True
    except ProtocolError:
        return None, False


def command_decision_batch(
    frontdoor_paths: Sequence[Path],
    wgm_paths: Sequence[Path],
    *,
    questions: Sequence[str],
    consequences: Sequence[str],
    router_paths: Sequence[Path] = (),
    recommendations: Sequence[object] = (),
    reasons: Sequence[object] = (),
) -> tuple[int, str]:
    """Render explicit Decision Discovery inputs in memory."""

    count = len(frontdoor_paths)
    if not (
        count == len(wgm_paths) == len(questions) == len(consequences)
        and len(router_paths) in (0, count)
        and len(recommendations) in (0, count)
        and len(reasons) in (0, count)
    ):
        raise ValueError("decision-batch arguments must have matching counts")

    recommendation_values = (
        list(recommendations) if recommendations else [None for _ in range(count)]
    )
    reason_values = list(reasons) if reasons else [[] for _ in range(count)]

    entries: list[dict[str, object]] = []
    for index in range(count):
        frontdoor, frontdoor_valid = _load_decision_protocol(
            "frontdoor-task", frontdoor_paths[index]
        )
        handoff, handoff_valid = _load_decision_protocol(
            "governance-handoff", wgm_paths[index]
        )
        entry: dict[str, object] = {
            "frontdoor_task": frontdoor if frontdoor_valid else {},
            "governance_handoff": handoff if handoff_valid else {},
            "question": questions[index],
            "recommendation": recommendation_values[index],
            "reasons": reason_values[index],
            "consequence_if_approved": consequences[index],
        }
        if router_paths:
            router, router_valid = _load_decision_protocol(
                "router-manifest", router_paths[index]
            )
            entry["router_manifest"] = router if router_valid else {}
        entries.append(entry)

    batch = build_decision_batch(entries)
    exit_code = 1 if batch["fail_closed"] else 0
    return exit_code, format_decision_batch(batch)


def command_decision_card(
    frontdoor_path: Path,
    wgm_path: Path,
    *,
    question: str,
    consequence_if_approved: str,
    recommendation: object = None,
    reasons: Sequence[object] = (),
    router_path: Path | None = None,
) -> dict[str, object]:
    """Emit one existing Decision Card contract without adding semantics."""

    frontdoor, frontdoor_valid = _load_decision_protocol(
        "frontdoor-task", frontdoor_path
    )
    handoff, handoff_valid = _load_decision_protocol(
        "governance-handoff", wgm_path
    )
    router = None
    if router_path is not None:
        router, router_valid = _load_decision_protocol("router-manifest", router_path)
        if not router_valid:
            router = {}

    frontdoor_input = frontdoor if frontdoor_valid else {}
    handoff_input = handoff if handoff_valid else {}
    decision_id = (
        frontdoor_input.get("request_id")
        if type(frontdoor_input) is dict
        else None
    )
    try:
        card = build_decision_card(
            frontdoor_input,
            handoff_input,
            decision_id=decision_id,
            question=question,
            recommendation=recommendation,
            reasons=reasons,
            consequence_if_approved=consequence_if_approved,
            router_manifest=router,
        )
    except (AttributeError, DecisionCardProductionError) as exc:
        raise DecisionCardProductionError("decision card production failed") from exc
    if card is None:
        raise DecisionCardProductionError("human decision card was not produced")
    return card


def _emit(document: object) -> bool:
    try:
        sys.stdout.write(canonical_json_bytes(document).decode("utf-8") + "\n")
        return True
    except (BrokenPipeError, OSError, UnicodeError, ValueError):
        return False


def _emit_text(document: str) -> bool:
    try:
        sys.stdout.write(document + "\n")
        return True
    except (BrokenPipeError, OSError, UnicodeError):
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "verify":
        exit_code, document = command_verify()
    elif arguments.command == "doctor":
        exit_code, document = command_doctor(tuple(arguments.aliases))
    elif arguments.command == "demo":
        exit_code, document = command_demo()
    elif arguments.command == "decision-card":
        try:
            document = command_decision_card(
                arguments.frontdoor,
                arguments.wgm,
                router_path=arguments.router,
                question=arguments.question,
                recommendation=arguments.recommendation,
                reasons=arguments.reasons,
                consequence_if_approved=arguments.consequence_if_approved,
            )
        except DecisionCardProductionError:
            try:
                sys.stderr.write("decision-card: unable to produce card\n")
            except (BrokenPipeError, OSError, UnicodeError):
                pass
            return 1
        if not _emit(document):
            return 1
        return 0
    elif arguments.command == "decision-batch":
        if len(arguments.router_paths or ()) not in (0, len(arguments.frontdoor_paths)):
            parser.error("--router must be omitted or repeated once per input")
        if len(arguments.frontdoor_paths) != len(arguments.wgm_paths):
            parser.error("--frontdoor and --wgm must be repeated equally")
        if len(arguments.frontdoor_paths) != len(arguments.questions):
            parser.error("--question must be repeated once per input")
        if len(arguments.frontdoor_paths) != len(arguments.consequences):
            parser.error("--consequence-if-approved must be repeated once per input")
        count = len(arguments.frontdoor_paths)
        recommendations = arguments.recommendations or [None for _ in range(count)]
        if len(recommendations) != count:
            parser.error("--recommendation must be omitted or repeated once per input")
        raw_reasons = arguments.reasons_json or []
        if len(raw_reasons) not in (0, count):
            parser.error("--reasons-json must be omitted or repeated once per input")
        reasons: list[object] = []
        for raw in raw_reasons:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parser.error("--reasons-json values must be JSON arrays")
            if type(parsed) is not list:
                parser.error("--reasons-json values must be JSON arrays")
            reasons.append(parsed)
        if not reasons:
            reasons = [[] for _ in range(count)]
        exit_code, document = command_decision_batch(
            arguments.frontdoor_paths,
            arguments.wgm_paths,
            questions=arguments.questions,
            consequences=arguments.consequences,
            router_paths=arguments.router_paths or (),
            recommendations=recommendations,
            reasons=reasons,
        )
        if not _emit_text(document):
            return 1
        return exit_code
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
    "command_decision_batch",
    "command_demo",
    "command_decision_card",
    "command_doctor",
    "command_protocol_list",
    "command_protocol_validate",
    "command_verify",
    "main",
)
