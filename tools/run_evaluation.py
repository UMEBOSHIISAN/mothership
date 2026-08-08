#!/usr/bin/env python3
"""Run the tracked, synthetic Mothership conformance evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mothership import __version__
from mothership.demo import run_demo
from mothership.protocols import ProtocolError, list_protocols, validate_protocol
from mothership.verify import verify_installation
from orchestration.lib.canonical import canonical_json_bytes
from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import loads_strict


CORPUS = ROOT / "evaluation/corpus/protocol-validation.v1.json"
GOLDEN = ROOT / "mothership/resources/golden-path"
KINDS = (
    "frontdoor-task",
    "governance-handoff",
    "router-manifest",
    "observation-snapshot",
)
FIXTURES = {
    "frontdoor-task": "01-frontdoor-task.json",
    "governance-handoff": "02-governance-handoff.json",
    "router-manifest": "03-router-manifest.json",
    "observation-snapshot": "04-observation-snapshot.json",
}
SEEDS = ("0", "1", "7", "42", "99", "31337", "65537", "random")


class EvaluationError(RuntimeError):
    """The tracked evaluation input or measured behavior is inconsistent."""


def _load_json(path: Path) -> object:
    try:
        return loads_strict(path.read_bytes())
    except (OSError, ContractError):
        raise EvaluationError("evaluation input is unavailable or invalid") from None


def _load_corpus() -> dict[str, object]:
    value = _load_json(CORPUS)
    if type(value) is not dict or set(value) != {"schema_version", "cases"}:
        raise EvaluationError("evaluation corpus shape is invalid")
    if value["schema_version"] != "mothership.protocol-evaluation-corpus.v1":
        raise EvaluationError("evaluation corpus version is unsupported")
    cases = value["cases"]
    if type(cases) is not list or len(cases) != 24:
        raise EvaluationError("evaluation corpus case count is invalid")
    identifiers: set[str] = set()
    per_kind = {kind: {"accepted": 0, "rejected": 0} for kind in KINDS}
    for case in cases:
        if type(case) is not dict or set(case) != {
            "id",
            "kind",
            "fixture",
            "expected",
            "mutation",
        }:
            raise EvaluationError("evaluation case shape is invalid")
        identifier = case["id"]
        kind = case["kind"]
        expected = case["expected"]
        if type(identifier) is not str or not identifier or identifier in identifiers:
            raise EvaluationError("evaluation case identifier is invalid")
        identifiers.add(identifier)
        if kind not in KINDS or case["fixture"] != FIXTURES[kind]:
            raise EvaluationError("evaluation case protocol mapping is invalid")
        if type(expected) is not str or expected not in {"accepted", "rejected"}:
            raise EvaluationError("evaluation case expectation is invalid")
        if expected == "accepted" and case["mutation"] is not None:
            raise EvaluationError("accepted evaluation case cannot be mutated")
        if expected == "rejected" and type(case["mutation"]) is not dict:
            raise EvaluationError("rejected evaluation case requires a mutation")
        per_kind[kind][expected] += 1
    if any(counts != {"accepted": 1, "rejected": 5} for counts in per_kind.values()):
        raise EvaluationError("evaluation case balance is invalid")
    return value


def _mutate(document: object, mutation: object) -> object:
    result = copy.deepcopy(document)
    if mutation is None:
        return result
    if type(mutation) is not dict or set(mutation) - {"op", "path", "value"}:
        raise EvaluationError("evaluation mutation shape is invalid")
    operation = mutation.get("op")
    path = mutation.get("path")
    if (
        type(operation) is not str
        or operation not in {"add", "delete", "set"}
        or type(path) is not list
        or not path
    ):
        raise EvaluationError("evaluation mutation instruction is invalid")
    if operation == "delete" and set(mutation) != {"op", "path"}:
        raise EvaluationError("delete mutation shape is invalid")
    if operation != "delete" and set(mutation) != {"op", "path", "value"}:
        raise EvaluationError("value mutation shape is invalid")

    parent = result
    for component in path[:-1]:
        if type(parent) is dict and type(component) is str and component in parent:
            parent = parent[component]
        elif type(parent) is list and type(component) is int and 0 <= component < len(parent):
            parent = parent[component]
        else:
            raise EvaluationError("evaluation mutation path is invalid")
    leaf = path[-1]
    if type(parent) is dict and type(leaf) is str:
        exists = leaf in parent
        if operation == "add" and exists:
            raise EvaluationError("add mutation target already exists")
        if operation in {"delete", "set"} and not exists:
            raise EvaluationError("evaluation mutation target is absent")
        if operation == "delete":
            del parent[leaf]
        else:
            parent[leaf] = copy.deepcopy(mutation["value"])
    elif type(parent) is list and type(leaf) is int and 0 <= leaf < len(parent):
        if operation != "set":
            raise EvaluationError("array mutation operation is invalid")
        parent[leaf] = copy.deepcopy(mutation["value"])
    else:
        raise EvaluationError("evaluation mutation target is invalid")
    return result


def _protocol_measurement(corpus: dict[str, object]) -> dict[str, int]:
    fixture_cache = {
        kind: _load_json(GOLDEN / filename)
        for kind, filename in FIXTURES.items()
    }
    valid_cases = 0
    valid_accepted = 0
    invalid_cases = 0
    invalid_rejected = 0
    for case in corpus["cases"]:
        document = _mutate(fixture_cache[case["kind"]], case["mutation"])
        if case["expected"] == "accepted":
            valid_cases += 1
            try:
                validate_protocol(case["kind"], document)
            except ProtocolError:
                continue
            valid_accepted += 1
        else:
            invalid_cases += 1
            try:
                validate_protocol(case["kind"], document)
            except ProtocolError:
                invalid_rejected += 1
    cases_passed = valid_accepted + invalid_rejected
    cases_total = valid_cases + invalid_cases
    if cases_passed != cases_total:
        raise EvaluationError("protocol conformance measurement did not pass")
    return {
        "valid_cases": valid_cases,
        "valid_accepted": valid_accepted,
        "invalid_cases": invalid_cases,
        "invalid_rejected": invalid_rejected,
        "cases_passed": cases_passed,
        "cases_total": cases_total,
    }


def _demo_determinism() -> dict[str, object]:
    outputs: list[bytes] = []
    with tempfile.TemporaryDirectory() as directory:
        cwd = Path(directory)
        for seed in SEEDS:
            environment = {
                "HOME": directory,
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": str(ROOT),
            }
            completed = subprocess.run(
                [sys.executable, "-m", "mothership", "demo"],
                cwd=cwd,
                env=environment,
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )
            if completed.returncode != 0 or completed.stderr:
                raise EvaluationError("demo determinism process failed")
            outputs.append(completed.stdout)
    distinct = len(set(outputs))
    if distinct != 1:
        raise EvaluationError("demo output was not byte-identical")
    return {
        "runs": len(outputs),
        "distinct_outputs": distinct,
        "byte_identical": True,
    }


def evaluate() -> dict[str, object]:
    """Return one deterministic, synthetic conformance result."""

    corpus = _load_corpus()
    integrity = verify_installation()
    if integrity.get("status") != "passed":
        raise EvaluationError("installed-resource integrity did not pass")
    demo = run_demo()
    protocols = list_protocols()
    return {
        "schema_version": "mothership.evaluation.v1",
        "subject": "mothership-control-plane",
        "subject_version": __version__,
        "claim_scope": "synthetic-conformance-only",
        "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "protocol_conformance": _protocol_measurement(corpus),
        "demo_determinism": _demo_determinism(),
        "resource_integrity": {"status": "passed"},
        "authority_boundary": {
            "demo_authority_effect": demo["authority_effect"],
            "demo_execution_effect": demo["execution_effect"],
            "protocols_authority_capable": sum(
                entry["authority_capable"] is True for entry in protocols
            ),
            "protocols_execution_capable": sum(
                entry["execution_capable"] is True for entry in protocols
            ),
            "protocols_total": len(protocols),
        },
    }


def main() -> int:
    try:
        result = evaluate()
    except (EvaluationError, OSError, subprocess.SubprocessError):
        print("evaluation failed closed", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
