"""Validated staged registry loading and advisory eligibility."""

from __future__ import annotations

from pathlib import Path

from .contracts import validate_contract
from .jsonio import load_strict


def load_registry(path: Path) -> dict[str, object]:
    """Load one exact registry through the strict regular-file boundary."""

    return validate_contract("executor-registry", load_strict(path))


def eligible_aliases(
    task: dict[str, object],
    registry: dict[str, object],
) -> tuple[str, ...]:
    """Return staged aliases covering requirements without selecting or authorizing."""

    checked_task = validate_contract("task", task)
    checked_registry = validate_contract("executor-registry", registry)
    required = set(checked_task["required_capabilities"])
    eligible: list[str] = []
    for alias, entry in checked_registry.items():
        capabilities = set(entry["capabilities"])
        if required.issubset(capabilities):
            eligible.append(alias)
    return tuple(sorted(eligible))
