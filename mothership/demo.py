"""Deterministic validation of the bundled synthetic ecosystem chain."""

from __future__ import annotations

from importlib import resources

from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import loads_strict

from .protocols import ProtocolError, list_protocols, validate_protocol


_RESOURCE_PACKAGE = "mothership.resources"
_STAGES = (
    ("frontdoor-task", "golden-path/01-frontdoor-task.json"),
    ("governance-handoff", "golden-path/02-governance-handoff.json"),
    ("router-manifest", "golden-path/03-router-manifest.json"),
    ("observation-snapshot", "golden-path/04-observation-snapshot.json"),
)


class DemoError(ValueError):
    """The bundled golden path failed validation or continuity checks."""


def _load_document(relative_path: str) -> dict[str, object]:
    try:
        raw = resources.files(_RESOURCE_PACKAGE).joinpath(relative_path).read_bytes()
        value = loads_strict(raw)
    except (ContractError, FileNotFoundError, OSError, TypeError, ValueError):
        raise DemoError("golden-path resource is invalid") from None
    if type(value) is not dict:
        raise DemoError("golden-path resource must be an object")
    return value


def _load_stage_documents() -> tuple[tuple[str, dict[str, object]], ...]:
    return tuple((kind, _load_document(path)) for kind, path in _STAGES)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DemoError(reason)


def run_demo() -> dict[str, object]:
    """Validate packaged fixtures only and return one deterministic summary."""

    stages = _load_stage_documents()
    registry_kinds = tuple(entry["kind"] for entry in list_protocols())
    _require(
        tuple(kind for kind, _document in stages) == registry_kinds,
        "golden-path stage order does not match the protocol registry",
    )

    checked: list[tuple[str, dict[str, object]]] = []
    for kind, document in stages:
        try:
            checked.append((kind, validate_protocol(kind, document)))
        except ProtocolError:
            raise DemoError(f"{kind} failed protocol validation") from None

    frontdoor = checked[0][1]
    governance = checked[1][1]
    router = checked[2][1]
    observation = checked[3][1]

    task_id = frontdoor["request_id"]
    capability = frontdoor["predicted_worker_capability"]
    _require(governance["task_id"] == task_id, "frontdoor-to-governance task identifier drift")
    _require(governance["capability"] == capability, "frontdoor-to-governance capability drift")
    _require(router["task_id"] == task_id, "governance-to-router task identifier drift")
    _require(router["capability"] == capability, "governance-to-router capability drift")
    _require(observation["task_id"] == task_id, "router-to-observation task identifier drift")
    _require(observation["source_kind"] == "router-manifest", "observation source kind drift")
    _require(
        observation["source_schema_version"] == router["schema_version"],
        "router-to-observation schema version drift",
    )
    _require(observation["status"] == router["status"], "router-to-observation status drift")
    _require(
        router["authority_effect"] is False and observation["authority_effect"] is False,
        "golden path claims an authority effect",
    )
    _require(
        router["execution_effect"] is False and observation["execution_effect"] is False,
        "golden path claims an execution effect",
    )

    summary = {
        "schema_version": "mothership.demo.v1",
        "status": "passed",
        "task_id": task_id,
        "capability": capability,
        "stages": [
            {
                "kind": kind,
                "schema_version": document["schema_version"],
                "valid": True,
            }
            for kind, document in checked
        ],
        "authority_effect": False,
        "execution_effect": False,
        "claim": "protocol-composition-only",
    }
    expected = _load_document("golden-path/expected-summary.json")
    _require(summary == expected, "golden-path summary does not match its frozen expectation")
    return summary


__all__ = ("DemoError", "run_demo")
