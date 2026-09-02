"""Bundled Draft 2020-12 subset and fixed public contracts."""

from __future__ import annotations

import math
from pathlib import Path, PurePosixPath
import re

from .errors import ContractError
from .jsonio import load_strict


_ROOT = Path(__file__).resolve().parents[2]
_SCHEMAS = {
    "approval-event": _ROOT / "evidence/contracts/approval-event.schema.json",
    "consequence-proposal.v0": (
        _ROOT / "evidence/contracts/consequence-proposal.v0.schema.json"
    ),
    "external-action-receipt.v0": (
        _ROOT / "evidence/contracts/external-action-receipt.v0.schema.json"
    ),
    "external-action-verification.v0": (
        _ROOT / "evidence/contracts/external-action-verification.v0.schema.json"
    ),
    "authority-action-approval": (
        _ROOT / "evidence/contracts/authority-action-approval.v0.schema.json"
    ),
    "authority-action-consume": (
        _ROOT / "evidence/contracts/authority-action-consume.v0.schema.json"
    ),
    "decision-card": _ROOT / "evidence/contracts/decision-card.v0.schema.json",
    "decision-approval": _ROOT / "evidence/contracts/decision-approval.v0.schema.json",
    "assessment": _ROOT / "safety/contracts/assessment.schema.json",
    "decision": _ROOT / "frontdoor/contracts/decision.schema.json",
    "task": _ROOT / "frontdoor/contracts/task.schema.json",
    "invocation-request": _ROOT / "orchestration/contracts/invocation-request.schema.json",
    "executor-registry": _ROOT / "orchestration/contracts/executor-registry.schema.json",
}


def _matches_type(value: object, expected: str) -> bool:
    if expected == "object":
        return type(value) is dict
    if expected == "array":
        return type(value) is list
    if expected == "string":
        return type(value) is str
    if expected == "integer":
        return type(value) is int or (
            type(value) is float and math.isfinite(value) and value.is_integer()
        )
    if expected == "number":
        return type(value) is int or (type(value) is float and math.isfinite(value))
    if expected == "boolean":
        return type(value) is bool
    if expected == "null":
        return value is None
    return False


def _json_equal(left: object, right: object) -> bool:
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left == right
    if type(left) in (int, float) and type(right) in (int, float):
        if type(left) is float and not math.isfinite(left):
            return False
        if type(right) is float and not math.isfinite(right):
            return False
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if type(left) is dict:
        return set(left) == set(right) and all(_json_equal(left[key], right[key]) for key in left)
    return left == right


def _validate_declared_type(value: object, declared: object) -> None:
    if type(declared) is str:
        expected_types = [declared]
    elif (
        type(declared) is list
        and declared
        and all(type(item) is str for item in declared)
        and len(set(declared)) == len(declared)
    ):
        expected_types = declared
    else:
        raise ContractError("schema type declaration is invalid")
    if not any(_matches_type(value, expected) for expected in expected_types):
        raise ContractError("value has the wrong type")


def _validate_object(value: dict[object, object], schema: dict[str, object]) -> None:
    if any(type(key) is not str for key in value):
        raise ContractError("object keys must be strings")
    properties = schema.get("properties", {})
    if type(properties) is not dict:
        raise ContractError("schema properties declaration is invalid")
    required = schema.get("required", [])
    if type(required) is not list or any(type(name) is not str for name in required):
        raise ContractError("schema required declaration is invalid")
    for name in required:
        if name not in value:
            raise ContractError("required object field is missing")
    unknown_names = set(value) - set(properties)
    additional = schema.get("additionalProperties", None)
    if additional is False:
        if unknown_names:
            raise ContractError("object contains an unknown field")
    elif type(additional) is dict:
        for name in unknown_names:
            _validate_schema(value[name], additional)
    elif additional is not None:
        raise ContractError("schema additionalProperties declaration is invalid")
    for name, item in value.items():
        if name in properties:
            property_schema = properties[name]
            if type(property_schema) is not dict:
                raise ContractError("schema property declaration is invalid")
            _validate_schema(item, property_schema)


def _validate_array(value: list[object], schema: dict[str, object]) -> None:
    if "minItems" in schema and len(value) < schema["minItems"]:
        raise ContractError("array is shorter than permitted")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        raise ContractError("array is longer than permitted")
    if schema.get("uniqueItems") is True:
        for index, item in enumerate(value):
            if any(_json_equal(item, prior) for prior in value[:index]):
                raise ContractError("array entries must be unique")
    item_schema = schema.get("items", None)
    if item_schema is False:
        if value:
            raise ContractError("array items are not permitted")
    elif type(item_schema) is dict:
        for item in value:
            _validate_schema(item, item_schema)
    elif item_schema is not None:
        raise ContractError("schema items declaration is invalid")


def _validate_string(value: str, schema: dict[str, object]) -> None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        raise ContractError("string is shorter than permitted")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        raise ContractError("string is longer than permitted")
    if "pattern" in schema:
        pattern = schema["pattern"]
        if type(pattern) is not str:
            raise ContractError("schema pattern is invalid")
        try:
            matches = re.fullmatch(pattern, value)
        except re.error:
            raise ContractError("schema pattern is invalid") from None
        if matches is None:
            raise ContractError("string does not match pattern")


def _validate_number(value: int | float, schema: dict[str, object]) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        raise ContractError("number is below minimum")
    if "maximum" in schema and value > schema["maximum"]:
        raise ContractError("number is above maximum")


def _validate_schema(value: object, schema: object) -> object:
    """Validate one value using the supported deterministic schema subset."""

    if type(schema) is not dict:
        raise ContractError("schema must be an object")
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise ContractError("value does not match const")
    if "enum" in schema:
        options = schema["enum"]
        if type(options) is not list or not options:
            raise ContractError("schema enum declaration is invalid")
        if not any(_json_equal(value, option) for option in options):
            raise ContractError("value is outside enum")
    if "type" in schema:
        _validate_declared_type(value, schema["type"])
    if type(value) is dict:
        _validate_object(value, schema)
    if type(value) is list:
        _validate_array(value, schema)
    if type(value) is str:
        _validate_string(value, schema)
    if type(value) in (int, float) and type(value) is not bool:
        _validate_number(value, schema)
    return value


def _require_safe_relative_path(value: object, label: str) -> None:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ContractError(f"{label} is unsafe")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or parsed == PurePosixPath("."):
        raise ContractError(f"{label} is unsafe")
    if any(part in ("", ".", "..") for part in parsed.parts) or parsed.as_posix() != value:
        raise ContractError(f"{label} is unsafe")


def _validate_task_semantics(task: dict[str, object]) -> None:
    context_files = task["context_files"]
    for path in context_files:
        _require_safe_relative_path(path, "context path")
    _require_safe_relative_path(task["prompt_file"], "prompt path")
    if len(context_files) > task["max_context_files"]:
        raise ContractError("context file count exceeds declared maximum")


def validate_contract(kind: str, value: object) -> dict[str, object]:
    """Validate one exact bundled contract by its fixed public kind."""

    if type(kind) is not str or kind not in _SCHEMAS:
        raise ContractError("contract kind is unknown")
    schema = load_strict(_SCHEMAS[kind])
    result = _validate_schema(value, schema)
    if type(result) is not dict:
        raise ContractError("contract value must be an object")
    if kind == "task":
        _validate_task_semantics(result)
    return dict(result)
