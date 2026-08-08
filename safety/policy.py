"""Closed, non-authorizing safety classification."""

from __future__ import annotations

from orchestration.lib.contracts import ContractError, validate_contract
from orchestration.lib.paths import PreparedScope


_RISKS = frozenset(("low", "medium", "high", "unknown"))


def _identity(value: object, sentinel: str) -> str:
    return value if type(value) is str and value else sentinel


def _exact_or_legacy(
    task: dict[str, object],
    exact: str,
    legacy: str,
    default: object,
) -> object:
    if exact in task:
        return task[exact]
    return task.get(legacy, default)


def _switch_disabled(task: dict[str, object], exact: str, legacy: str) -> bool:
    if exact in task:
        value = task[exact]
        return type(value) is dict and set(value) == {"enabled"} and value["enabled"] is False
    return task.get(legacy, False) is False


def _assessment(
    task_id: str,
    invocation_id: str,
    classification: str,
    reasons: set[str],
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": "0.1.0",
        "task_id": task_id,
        "invocation_id": invocation_id,
        "classification": classification,
        "reason_codes": sorted(reasons),
        "authority_effect": "none",
    }
    try:
        return validate_contract("assessment", result)
    except ContractError as error:
        raise RuntimeError("bundled assessment schema rejected a generated result") from error


def assess(
    task: dict[str, object],
    mode: str,
    selected_alias: str | None,
    call_depth: int,
    scope: PreparedScope | None,
) -> dict[str, object]:
    """Classify every malformed input as a schema-valid closed result."""

    if type(task) is not dict:
        return _assessment(
            "invalid-task",
            "invalid-invocation",
            "blocked",
            {"unsupported_risk_class"},
        )

    task_id = _identity(task.get("task_id"), "invalid-task")
    invocation_id = _identity(task.get("invocation_id"), "invalid-invocation")
    reasons: set[str] = set()
    if task_id == "invalid-task" or invocation_id == "invalid-invocation":
        reasons.add("unsupported_risk_class")

    risk = task.get("risk_class", task.get("risk"))
    if type(risk) is not str or risk not in _RISKS:
        reasons.add("unsupported_risk_class")
    if type(mode) is not str or mode not in {"dry-run", "execute"}:
        reasons.add("invalid_mode")
    if type(call_depth) is not int or call_depth < 0:
        reasons.add("invalid_call_depth")
    if reasons:
        return _assessment(task_id, invocation_id, "blocked", reasons)

    elevated = risk in {"high", "unknown"}
    if mode == "dry-run":
        if elevated:
            return _assessment(
                task_id,
                invocation_id,
                "human-review-required",
                {"elevated_risk_human_review"},
            )
        return _assessment(
            task_id,
            invocation_id,
            "unclassified",
            {"no_authority_effect"},
        )

    maximum = task.get("max_call_depth", task.get("maximum_call_depth", 1))
    if (
        type(maximum) is not int
        or maximum < 0
        or call_depth > 1
        or call_depth > maximum
    ):
        reasons.add("call_depth_exceeds_maximum")
    if elevated:
        reasons.add("elevated_risk_execute_blocked")
    mutation = _exact_or_legacy(task, "mutation_class", "mutation", "none")
    if mutation != "none":
        reasons.add("mutation_not_none")
    if type(selected_alias) is not str or not selected_alias:
        reasons.add("missing_selected_alias_for_execute")
    if scope is None:
        reasons.add("missing_scope_for_execute")
    if not _switch_disabled(task, "retry", "retry_enabled"):
        reasons.add("retry_enabled")
    if not _switch_disabled(task, "fallback", "fallback_enabled"):
        reasons.add("fallback_enabled")
    attempts = task.get("max_attempts", 1)
    if type(attempts) is not int or attempts != 1:
        reasons.add("max_attempts_not_one")
    capabilities = _exact_or_legacy(
        task,
        "required_capabilities",
        "capabilities",
        [],
    )
    if type(capabilities) is not list or "read-only" not in capabilities:
        reasons.add("read_only_capability_required")

    if reasons:
        return _assessment(task_id, invocation_id, "blocked", reasons)
    return _assessment(
        task_id,
        invocation_id,
        "unclassified",
        {"no_authority_effect"},
    )
