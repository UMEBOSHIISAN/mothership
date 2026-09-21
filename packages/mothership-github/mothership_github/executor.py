"""One-shot executor for the closed Core ``github.merge_pr`` action profile."""

from __future__ import annotations

import copy
import pathlib
import re
from collections.abc import Mapping
from typing import Any

from orchestration.lib import action_authority, action_authority_ledger
from orchestration.lib.action_authority import FrozenAction

from .transport import (
    ActionExecutionError,
    ActionPreflightError,
    GitHubTransport,
)


_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_PATTERN = re.compile(r"event-[0-9a-f]{32}\Z")
_MISSING = object()
_RECOGNIZED_CLIENT_FAILURES = frozenset(
    {
        400,
        401,
        403,
        404,
        405,
        406,
        409,
        412,
        413,
        415,
        422,
        428,
        431,
        451,
    }
)


def consume_action(
    ledger_path: pathlib.Path,
    approval_event_id: object,
    action_id: object,
    action_sha256: object,
) -> tuple[dict[str, object], dict[str, object]]:
    """Call Core's public one-shot consume API without a clock override."""

    return action_authority_ledger.consume_action(
        ledger_path, approval_event_id, action_id, action_sha256
    )


def record_attempt_started(
    receipt_path: pathlib.Path,
    authority_path: pathlib.Path,
    consume_event: Mapping[str, object],
    action: Mapping[str, object],
) -> dict[str, object]:
    """Persist a validated attempt start before mutation."""

    from .receipts import record_attempt_started as _record_attempt_started

    return _record_attempt_started(receipt_path, authority_path, consume_event, action)


def record_attempt_finished(
    receipt_path: pathlib.Path,
    started: Mapping[str, object],
    outcome: str,
    observation: Mapping[str, object],
) -> dict[str, object]:
    """Persist the terminal facts for the matching attempt."""

    from .receipts import record_attempt_finished as _record_attempt_finished

    return _record_attempt_finished(receipt_path, started, outcome, observation)


def _as_path(value: object, name: str) -> pathlib.Path:
    if isinstance(value, pathlib.Path):
        return value
    if type(value) is str:
        return pathlib.Path(value)
    raise ActionExecutionError(f"{name} must be a path")


def _validated_action_before_io(frozen_action: FrozenAction) -> tuple[dict[str, object], str]:
    """Validate Core issuance, digest, profile, and expiry before any GET."""

    action = action_authority._validated_frozen_action(frozen_action)
    if type(action) is not dict:
        raise ActionExecutionError("Core returned an invalid frozen action")
    try:
        digest = frozen_action.action_sha256
        checked_digest = action_authority.action_sha256(copy.deepcopy(action))
    except Exception:
        raise ActionExecutionError("Core frozen action validation failed") from None
    if type(digest) is not str or not _DIGEST_PATTERN.fullmatch(digest) or checked_digest != digest:
        raise ActionExecutionError("Core frozen action digest is invalid")
    return copy.deepcopy(action), digest


def _validated_consume_event(
    value: object,
    *,
    approval_event_id: str,
    action_id: str,
    action_sha256: str,
) -> dict[str, object]:
    """Validate the exact durable consume row returned by Core."""

    if not isinstance(value, Mapping):
        raise ActionExecutionError("Core consume result did not contain a durable event")
    try:
        candidate = copy.deepcopy(dict(value))
        checked = action_authority_ledger._validated_event(candidate)
    except Exception:
        raise ActionExecutionError("Core consume event is invalid") from None
    if (
        checked.get("schema_version") != "authority-action-consume.v0"
        or checked.get("event_type") != "authority_action_consume"
        or checked.get("approval_event_id") != approval_event_id
        or checked.get("action_id") != action_id
        or checked.get("action_sha256") != action_sha256
        or type(checked.get("event_id")) is not str
        or not _EVENT_PATTERN.fullmatch(checked["event_id"])
    ):
        raise ActionExecutionError("Core consume event is not bound to the requested action")
    return copy.deepcopy(checked)


def _verified_consumed_action(value: object, expected: Mapping[str, object], digest: str) -> dict[str, object]:
    """Revalidate Core's returned action and reject any changed projection."""

    if not isinstance(value, Mapping):
        raise ActionExecutionError("Core consume result did not contain a verified action")
    try:
        checked = action_authority._validated_action(copy.deepcopy(dict(value)))
        checked_digest = action_authority.action_sha256(copy.deepcopy(checked))
    except Exception:
        raise ActionExecutionError("Core returned a malformed consumed action") from None
    if checked_digest != digest or checked != dict(expected):
        raise ActionExecutionError("Core returned an action different from the validated snapshot")
    return copy.deepcopy(checked)


def _validate_preflight(snapshot: object, parameters: Mapping[str, object]) -> None:
    if not isinstance(snapshot, Mapping):
        raise ActionPreflightError("preflight result was malformed")
    state = snapshot.get("state")
    merged = snapshot.get("merged", _MISSING)
    head_sha = snapshot.get("head_sha", _MISSING)
    base_ref = snapshot.get("base_ref", _MISSING)
    if type(snapshot.get("http_status")) is not int or snapshot["http_status"] != 200:
        raise ActionPreflightError("preflight HTTP status was not successful")
    if state != "open":
        raise ActionPreflightError("pull request is not open")
    if type(merged) is not bool:
        raise ActionPreflightError("preflight merged state was malformed")
    if merged is True:
        raise ActionPreflightError("pull request is already merged")
    if head_sha != parameters["expected_head_sha"]:
        raise ActionPreflightError("pull request head does not match the frozen action")
    if base_ref != parameters["expected_base"]:
        raise ActionPreflightError("pull request base does not match the frozen action")


def _normalized_observation(
    value: object,
) -> tuple[str, dict[str, object]]:
    """Convert any transport result into the closed receipt outcome facts."""

    source: Mapping[str, object] = value if isinstance(value, Mapping) else {}
    ambiguous = False

    explicit_ambiguous = source.get("ambiguous", False)
    if type(explicit_ambiguous) is not bool:
        ambiguous = True
    elif explicit_ambiguous:
        ambiguous = True

    redirect_rejected = source.get("redirect_rejected", False)
    if type(redirect_rejected) is not bool:
        ambiguous = True
        redirect_rejected = False

    statuses: list[int] = []
    for key in ("http_status", "status_code"):
        if key not in source:
            continue
        candidate = source[key]
        if type(candidate) is not int or candidate < 0 or candidate > 599 or (
            candidate != 0 and candidate < 100
        ):
            ambiguous = True
            continue
        statuses.append(candidate)
    status = statuses[0] if statuses else 0
    if len(statuses) > 1 and statuses[0] != statuses[1]:
        ambiguous = True

    merged: object = source.get("merged", None)
    if merged is not None and type(merged) is not bool:
        ambiguous = True
        merged = None

    sha_values: list[object] = []
    for key in ("merge_commit_sha", "sha"):
        if key in source:
            sha_values.append(source[key])
    sha: object = sha_values[0] if sha_values else None
    if len(sha_values) > 1 and sha_values[0] != sha_values[1]:
        ambiguous = True
        sha = None
    if sha is not None and (type(sha) is not str or not _SHA_PATTERN.fullmatch(sha)):
        ambiguous = True
        sha = None

    if redirect_rejected and not 300 <= status <= 399:
        ambiguous = True

    if status != 200 and (merged is True or sha is not None):
        ambiguous = True

    observation = {
        "http_status": status,
        "merged": merged if type(merged) is bool else None,
        "merge_commit_sha": sha if type(sha) is str else None,
    }

    # Explicit ambiguity, including a malformed/contradictory alias, always
    # wins before the apparent HTTP/merge fields are considered.
    if ambiguous:
        return "reconciliation_required", observation
    if status == 200 and merged is True and type(sha) is str and _SHA_PATTERN.fullmatch(sha):
        return "success", observation
    if redirect_rejected and 300 <= status <= 399:
        return "failure", observation
    if status in _RECOGNIZED_CLIENT_FAILURES:
        return "failure", observation
    return "reconciliation_required", observation


def execute_action_merge_pr(
    action_ledger_path: pathlib.Path,
    receipt_ledger_path: pathlib.Path,
    frozen_action: FrozenAction,
    approval_event_id: str,
    transport: GitHubTransport,
) -> dict[str, object]:
    """Execute one validated merge action with one possible PUT.

    Core validation happens before the first transport GET and immediately
    after that GET.  Core's durable consume tuple then becomes the only
    action material passed to the receipt and mutation stages.
    """

    checked_action, action_digest = _validated_action_before_io(frozen_action)
    authority_path = _as_path(action_ledger_path, "action_ledger_path")
    receipt_path = _as_path(receipt_ledger_path, "receipt_ledger_path")
    if not isinstance(approval_event_id, str):
        raise ActionExecutionError("approval_event_id must be a string")
    if not callable(getattr(transport, "get_pull_request", None)) or not callable(
        getattr(transport, "merge_pull_request", None)
    ):
        raise ActionExecutionError("transport does not implement the GitHub transport contract")

    parameters = checked_action["execution_parameters"]
    if not isinstance(parameters, Mapping):
        raise ActionExecutionError("frozen action parameters are malformed")
    repository = parameters["repository"]
    pull_request = parameters["pull_request"]

    try:
        preflight = transport.get_pull_request(repository, pull_request)
    except ActionPreflightError:
        raise
    except Exception:
        raise ActionPreflightError("preflight transport failed") from None
    _validate_preflight(preflight, parameters)

    # Re-run Core's validator after the potentially slow/mutating GET so an
    # expiry boundary cannot be crossed between the initial check and consume.
    current_action, current_digest = _validated_action_before_io(frozen_action)
    if current_digest != action_digest or current_action != checked_action:
        raise ActionExecutionError("frozen action changed during preflight")

    consumed = consume_action(
        authority_path,
        approval_event_id,
        checked_action["action_id"],
        action_digest,
    )
    if type(consumed) is not tuple or len(consumed) != 2:
        raise ActionExecutionError("Core consume result must be a durable-event/action tuple")
    consume_event = _validated_consume_event(
        consumed[0],
        approval_event_id=approval_event_id,
        action_id=checked_action["action_id"],
        action_sha256=action_digest,
    )
    verified_action = _verified_consumed_action(consumed[1], checked_action, action_digest)

    # This write is intentionally after consume.  A start failure burns the
    # one-shot authority and stops before any PUT; it is never retried here.
    started = record_attempt_started(
        receipt_path,
        authority_path,
        copy.deepcopy(consume_event),
        copy.deepcopy(verified_action),
    )

    mutation_result: object
    try:
        mutation_result = transport.merge_pull_request(
            repository=verified_action["execution_parameters"]["repository"],
            pull_request=verified_action["execution_parameters"]["pull_request"],
            expected_head_sha=verified_action["execution_parameters"]["expected_head_sha"],
            merge_method=verified_action["execution_parameters"]["merge_method"],
        )
    except Exception:
        mutation_result = {
            "http_status": 0,
            "merged": None,
            "merge_commit_sha": None,
            "ambiguous": True,
        }

    outcome, observation = _normalized_observation(mutation_result)
    finished = record_attempt_finished(
        receipt_path,
        started,
        outcome,
        observation,
    )

    result: dict[str, object] = {
        "status": outcome,
        "outcome": outcome,
        "consume_event": copy.deepcopy(consume_event),
        "consume_receipt": copy.deepcopy(consume_event),
        "verified_action": copy.deepcopy(verified_action),
        "attempt_started": copy.deepcopy(started),
        "started_receipt": copy.deepcopy(started),
        "attempt_finished": copy.deepcopy(finished),
        "finished_receipt": copy.deepcopy(finished),
        "observation": copy.deepcopy(observation),
        "http_status": observation["http_status"],
        "merged": observation["merged"],
        "merge_commit_sha": observation["merge_commit_sha"],
    }
    return result


__all__ = [
    "ActionExecutionError",
    "ActionPreflightError",
    "execute_action_merge_pr",
]
