"""Pure frozen-action and bound-decision transport validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import datetime
import re
from types import MappingProxyType

from .canonical import canonical_json_sha256
from .errors import ContractError


_APPROVAL_TTL = datetime.timedelta(minutes=10)
_ACTION_ID = re.compile(r"act-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_HEAD_SHA = re.compile(r"[0-9a-f]{40}\Z")
_BASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_UTC_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
_EXCLUDED_OPERATIONS = ("squash", "rebase", "force_push", "branch_delete")


class ActionAuthorityError(ContractError):
    """Base error for the closed authority-action transport boundary."""


class MalformedActionError(ActionAuthorityError):
    """Raised when an action or frozen context does not meet the closed profile."""


class UnsupportedOperationError(ActionAuthorityError):
    """Raised when an action requests an operation outside the v0 profile."""


class ActionBindingError(ActionAuthorityError):
    """Raised when a human decision is not bound to the exact frozen action."""


class ExpiredActionError(MalformedActionError):
    """Raised when a frozen action context is no longer within its deadline."""


@dataclass(frozen=True)
class FrozenAction:
    """An in-memory immutable action, its canonical digest, and its deadline."""

    action: Mapping[str, object]
    action_sha256: str
    expires_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, Mapping):
            raise MalformedActionError("frozen action must be a mapping")
        object.__setattr__(self, "action", _freeze_value(self.action))


def freeze_action(
    action_id: str,
    operation: str,
    execution_parameters: dict[str, object],
) -> FrozenAction:
    """Validate and freeze one closed github.merge_pr action instance."""

    action = _validated_action(
        {
            "action_id": action_id,
            "operation": operation,
            "execution_parameters": execution_parameters,
            "display": _display_for(operation, execution_parameters),
        }
    )
    frozen_at = _utc_now()
    return FrozenAction(
        action=action,
        action_sha256=canonical_json_sha256(action),
        expires_at=_format_utc(frozen_at + _APPROVAL_TTL),
    )


def action_sha256(action: dict[str, object]) -> str:
    """Return the canonical SHA-256 of one exact, validated frozen action."""

    return canonical_json_sha256(_validated_action(action))


def validate_decision_transport(
    frozen_action: FrozenAction,
    decision: object,
    action_id: object,
    supplied_action_sha256: object,
) -> dict[str, str]:
    """Validate a structured approve/reject decision bound to one frozen action."""

    action = _validated_frozen_action(frozen_action)
    if type(decision) is not str or decision not in {"approve", "reject"}:
        raise ActionBindingError("decision must be approve or reject")
    if type(action_id) is not str or not action_id or action_id != action["action_id"]:
        raise ActionBindingError("decision action_id does not match frozen action")
    if (
        type(supplied_action_sha256) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", supplied_action_sha256)
        or supplied_action_sha256 != frozen_action.action_sha256
    ):
        raise ActionBindingError("decision action_sha256 does not match frozen action")
    return {
        "decision": decision,
        "action_id": action_id,
        "action_sha256": supplied_action_sha256,
    }


def _validated_frozen_action(frozen_action: FrozenAction) -> dict[str, object]:
    if not isinstance(frozen_action, FrozenAction):
        raise MalformedActionError("frozen action context is invalid")
    action = _validated_action(frozen_action.action)
    expected_digest = canonical_json_sha256(action)
    if type(frozen_action.action_sha256) is not str or frozen_action.action_sha256 != expected_digest:
        raise MalformedActionError("frozen action digest is invalid")
    expires_at = _parse_utc(frozen_action.expires_at)
    now = _utc_now()
    if expires_at > now + _APPROVAL_TTL:
        raise MalformedActionError("frozen action expiry exceeds the fixed policy window")
    if expires_at <= now:
        raise ExpiredActionError("frozen action has expired")
    return action


def _validated_action(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "action_id",
        "operation",
        "execution_parameters",
        "display",
    }:
        raise MalformedActionError("action must have exactly the closed frozen-action fields")
    action_id = value["action_id"]
    operation = value["operation"]
    parameters = value["execution_parameters"]
    display = value["display"]
    _validate_action_id(action_id)
    if type(operation) is not str:
        raise MalformedActionError("operation must be a string")
    if operation != "github.merge_pr":
        raise UnsupportedOperationError("operation is not supported")
    checked_parameters = _validated_parameters(parameters)
    expected_display = _display_for(operation, checked_parameters)
    if not isinstance(display, Mapping) or set(display) != set(expected_display):
        raise MalformedActionError("action display must have exactly the derived fields")
    if _thaw_value(display) != expected_display:
        raise MalformedActionError("action display does not match executable parameters")
    return {
        "action_id": action_id,
        "operation": operation,
        "execution_parameters": checked_parameters,
        "display": expected_display,
    }


def _validated_parameters(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "repository",
        "pull_request",
        "expected_head_sha",
        "expected_base",
        "merge_method",
    }:
        raise MalformedActionError("execution parameters must match the closed merge profile")
    repository = value["repository"]
    pull_request = value["pull_request"]
    expected_head_sha = value["expected_head_sha"]
    expected_base = value["expected_base"]
    merge_method = value["merge_method"]
    if type(repository) is not str or not _REPOSITORY.fullmatch(repository):
        raise MalformedActionError("repository is invalid")
    if type(pull_request) is not int or pull_request < 1:
        raise MalformedActionError("pull_request is invalid")
    if type(expected_head_sha) is not str or not _HEAD_SHA.fullmatch(expected_head_sha):
        raise MalformedActionError("expected_head_sha is invalid")
    if (
        type(expected_base) is not str
        or not 1 <= len(expected_base) <= 128
        or not _BASE.fullmatch(expected_base)
    ):
        raise MalformedActionError("expected_base is invalid")
    if merge_method != "merge":
        raise MalformedActionError("merge_method must be merge")
    return {
        "repository": repository,
        "pull_request": pull_request,
        "expected_head_sha": expected_head_sha,
        "expected_base": expected_base,
        "merge_method": merge_method,
    }


def _validate_action_id(value: object) -> None:
    if type(value) is not str or not _ACTION_ID.fullmatch(value):
        raise MalformedActionError("action_id is invalid")


def _display_for(operation: object, parameters: object) -> dict[str, object]:
    if operation != "github.merge_pr":
        raise UnsupportedOperationError("operation is not supported")
    checked = _validated_parameters(parameters)
    repository = checked["repository"]
    pull_request = checked["pull_request"]
    expected_head_sha = checked["expected_head_sha"]
    expected_base = checked["expected_base"]
    return {
        "target": f"PR #{pull_request} -> {expected_base}",
        "scope": (
            f"repository={repository}; expected_head_sha={expected_head_sha}; "
            f"expected_base={expected_base}; merge_method=merge"
        ),
        "excluded_operations": list(_EXCLUDED_OPERATIONS),
        "consequence_if_approved": (
            f"PR #{pull_request} changes will be integrated into {expected_base}."
        ),
    }


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_thaw_value(item) for item in value]
    return value


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def _format_utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).strftime(_UTC_TIMESTAMP)


def _parse_utc(value: object) -> datetime.datetime:
    if type(value) is not str:
        raise MalformedActionError("frozen action expiry is invalid")
    try:
        return datetime.datetime.strptime(value, _UTC_TIMESTAMP).replace(tzinfo=datetime.UTC)
    except ValueError:
        raise MalformedActionError("frozen action expiry is invalid") from None
