"""Pure, non-authorizing advisory routing."""

from orchestration.lib.contracts import validate_contract
from orchestration.lib.registry import eligible_aliases


def route(task: dict[str, object], registry: dict[str, object]) -> dict[str, object]:
    """Return a closed advisory decision without selecting or executing."""
    checked_task = validate_contract("task", task)
    checked_registry = validate_contract("executor-registry", registry)
    aliases = eligible_aliases(checked_task, checked_registry)
    result: dict[str, object] = {
        "schema_version": "0.1.0", "task_id": checked_task["task_id"],
        "invocation_id": checked_task["invocation_id"], "recommended_alias": None,
        "selected_alias": None, "actual_alias": None, "authority_effect": "none",
    }
    if checked_task["risk_class"] in {"high", "unknown"}:
        result["status"] = "human_review_required"
    elif aliases:
        result["status"] = "recommended"
        result["recommended_alias"] = min(aliases)
    else:
        result["status"] = "no_eligible_alias"
    return validate_contract("decision", result)
