"""Pure portable-host review request and response binding."""

from __future__ import annotations

from .action_authority import (
    ActionAuthorityError,
    ActionBindingError,
    ExpiredActionError,
    _validated_frozen_action,
    validate_decision_transport,
)
from .canonical import canonical_json_bytes, canonical_json_sha256
from .contracts import validate_contract
from .errors import ContractError


_REQUEST_SCHEMA = "authority-action-review-request"
_RESPONSE_SCHEMA = "authority-action-review-response"
_REQUEST_VERSION = "authority-action-review-request.v0"


class ActionReviewError(ActionBindingError):
    """Raised when a portable-host review cannot bind to its live action."""


def _detach(value: object) -> object:
    if type(value) is dict:
        return {key: _detach(item) for key, item in value.items()}
    if type(value) is list:
        return [_detach(item) for item in value]
    return value


def _live_action_snapshot(
    frozen_action: object,
) -> tuple[dict[str, object], str, str]:
    try:
        action = _validated_frozen_action(frozen_action)
    except ExpiredActionError:
        raise
    except ActionAuthorityError as exc:
        raise ActionReviewError(f"live frozen action is invalid: {exc}") from exc

    try:
        action_sha256 = frozen_action.action_sha256
        expires_at = frozen_action.expires_at
    except (AttributeError, ActionAuthorityError) as exc:
        raise ActionReviewError("live frozen action fields are unavailable") from exc
    return _detach(action), action_sha256, expires_at  # type: ignore[return-value]


def _validated_request(value: object) -> dict[str, object]:
    try:
        return validate_contract(_REQUEST_SCHEMA, value)
    except ContractError as exc:
        raise ActionReviewError(f"review request is invalid: {exc}") from exc


def _validated_response(value: object) -> dict[str, object]:
    try:
        return validate_contract(_RESPONSE_SCHEMA, value)
    except ContractError as exc:
        raise ActionReviewError(f"review response is invalid: {exc}") from exc


def _make_request(
    action: dict[str, object],
    action_sha256: str,
    expires_at: str,
    request_id: object,
    host_context: object,
) -> dict[str, object]:
    unsigned = {
        "schema_version": _REQUEST_VERSION,
        "request_id": request_id,
        "action": _detach(action),
        "action_sha256": action_sha256,
        "expires_at": expires_at,
        "host_context": host_context,
    }
    try:
        request = {
            **unsigned,
            "request_sha256": canonical_json_sha256(unsigned),
        }
    except ContractError as exc:
        raise ActionReviewError(f"review request cannot be canonicalized: {exc}") from exc
    return _detach(_validated_request(request))  # type: ignore[return-value]


def build_review_request(
    frozen_action: object,
    *,
    request_id: object,
    host_context: object,
) -> dict[str, object]:
    """Build detached review data from one live Core-issued action."""

    action, action_sha256, expires_at = _live_action_snapshot(frozen_action)
    return _make_request(action, action_sha256, expires_at, request_id, host_context)


def _require_equal(actual: object, expected: object, field: str) -> None:
    if actual != expected:
        raise ActionReviewError(f"review {field} does not match the retained request")


def validate_review_response(
    frozen_action: object,
    expected_request: object,
    response: object,
    *,
    current_host_context: object,
) -> dict[str, str]:
    """Validate one response against the retained request and live action.

    The caller retains the expected request.  A returned request is never used
    as the expected value, and this helper records neither authority nor
    execution state.
    """

    expected = _validated_request(expected_request)
    action, action_sha256, expires_at = _live_action_snapshot(frozen_action)
    rebuilt = _make_request(
        action,
        action_sha256,
        expires_at,
        expected["request_id"],
        current_host_context,
    )
    try:
        expected_bytes = canonical_json_bytes(expected)
        rebuilt_bytes = canonical_json_bytes(rebuilt)
    except ContractError as exc:
        raise ActionReviewError(f"review request cannot be canonicalized: {exc}") from exc
    if rebuilt_bytes != expected_bytes:
        raise ActionReviewError("rebuilt review request differs from the retained request")

    checked_response = _validated_response(response)
    _require_equal(checked_response["request_id"], expected["request_id"], "request_id")
    _require_equal(
        checked_response["request_sha256"], expected["request_sha256"], "request_sha256"
    )
    _require_equal(checked_response["action_id"], action["action_id"], "action_id")
    _require_equal(checked_response["action_sha256"], action_sha256, "action_sha256")

    try:
        result = validate_decision_transport(
            frozen_action,
            checked_response["decision"],
            checked_response["action_id"],
            checked_response["action_sha256"],
        )
    except ExpiredActionError:
        raise
    except ActionBindingError as exc:
        raise ActionReviewError(f"review decision is not bound: {exc}") from exc

    if (
        result["decision"] == "approve"
        and action["operation"] not in rebuilt["host_context"]["scope"]
    ):
        raise ActionReviewError("approved operation is outside the current host scope")
    return result


__all__ = ("ActionReviewError", "build_review_request", "validate_review_response")
