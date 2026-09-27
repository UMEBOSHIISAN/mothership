"""Independent, bounded GitHub read-back verification for merge actions."""

from __future__ import annotations

import datetime
import re
from types import MappingProxyType
from urllib.parse import urlsplit

from mothership.contracts import (
    ContractError,
    canonical_json_sha256,
    validate_external_action_receipt,
    validate_receipt_verification_binding,
)
from orchestration.lib import action_authority
from orchestration.lib.action_authority import FrozenAction

from .observation import GitHubObservationAdapter
from . import public_observation


_INVALID = "invalid GitHub read-back verification input"
_VERSION = "github-merge-readback.v0"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_API_ROOT = "https://api.github.com"
_PR_PROJECTION_KEYS = frozenset(
    {
        "repository",
        "number",
        "state",
        "merged",
        "merged_at",
        "head_sha",
        "base_ref",
        "merge_commit_sha",
    }
)
_COMMIT_PROJECTION_KEYS = frozenset({"sha", "parents"})


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def _format_utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _parse_utc(value: object) -> datetime.datetime:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        raise ValueError
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        raise ValueError from None


def _snapshot(
    value: object,
    *,
    _active: set[int] | None = None,
    allow_mappingproxy: bool = False,
) -> object:
    """Copy only plain JSON containers, without invoking custom copy hooks."""

    if value is None or type(value) in (str, int, bool):
        return value
    active = set() if _active is None else _active
    if type(value) in (dict, list, tuple, MappingProxyType):
        if type(value) is MappingProxyType and not allow_mappingproxy:
            raise ContractError(_INVALID)
        marker = id(value)
        if marker in active:
            raise ContractError(_INVALID)
        active.add(marker)
        try:
            if type(value) in (dict, MappingProxyType):
                if any(type(key) is not str for key in value):
                    raise ContractError(_INVALID)
                return {
                    key: _snapshot(
                        item, _active=active, allow_mappingproxy=allow_mappingproxy
                    )
                    for key, item in value.items()
                }
            return [
                _snapshot(item, _active=active, allow_mappingproxy=allow_mappingproxy)
                for item in value
            ]
        finally:
            active.remove(marker)
    raise ContractError(_INVALID)


def _snapshot_action(frozen_action: object) -> tuple[dict[str, object], str]:
    if type(frozen_action) is not FrozenAction:
        raise ContractError(_INVALID)
    try:
        # Accessing all public fields invokes Core's issuance/tamper checks.
        raw_action = frozen_action.action
        raw_digest = frozen_action.action_sha256
        frozen_action.expires_at
        if type(raw_digest) is not str or _DIGEST.fullmatch(raw_digest) is None:
            raise ContractError(_INVALID)
        if not isinstance(raw_action, MappingProxyType):
            raise ContractError(_INVALID)
        action = _snapshot(raw_action, allow_mappingproxy=True)
        if type(action) is not dict:
            raise ContractError(_INVALID)
        checked_digest = action_authority.action_sha256(action)
    except (ContractError, action_authority.ActionAuthorityError, TypeError, ValueError, RecursionError):
        raise ContractError(_INVALID) from None
    if checked_digest != raw_digest:
        raise ContractError(_INVALID)
    return action, raw_digest


def _snapshot_receipt(receipt: object, action: dict[str, object], digest: str) -> tuple[dict[str, object], str, datetime.datetime, datetime.datetime]:
    try:
        value = _snapshot(receipt)
        if type(value) is not dict:
            raise ContractError(_INVALID)
        checked = validate_external_action_receipt(value)
        if checked["action_id"] != action["action_id"] or checked["action_sha256"] != digest:
            raise ContractError(_INVALID)
        started = _parse_utc(checked["started_at"])
        finished = _parse_utc(checked["finished_at"])
        if started > finished:
            raise ContractError(_INVALID)
        return checked, canonical_json_sha256(checked), started, finished
    except (ContractError, TypeError, ValueError, RecursionError):
        raise ContractError(_INVALID) from None


def _same_repository(left: object, expected: str) -> bool:
    if type(left) is not str:
        return False
    try:
        parsed = public_observation.parse_github_repository("https://github.com/" + left)
    except Exception:
        return False
    return parsed.source_url.casefold() == ("https://github.com/" + expected).casefold()


def _same_api_resource(value: object, *, repository: str, kind: str, number_or_sha: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.github.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    owner, repo = repository.split("/", 1)
    parts = parsed.path.split("/")
    if kind == "pull":
        expected_parts = ["", "repos", owner, repo, "pulls", str(number_or_sha)]
    else:
        expected_parts = ["", "repos", owner, repo, "git", "commits", str(number_or_sha)]
    return (
        len(parts) == len(expected_parts)
        and parts[1] == expected_parts[1]
        and parts[4:] == expected_parts[4:]
        and parts[2].casefold() == owner.casefold()
        and parts[3].casefold() == repo.casefold()
    )


def _strict_sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _semantic_pr(
    payload: object,
    *,
    repository: str,
    number: int,
    response_finished: datetime.datetime,
    receipt_started: datetime.datetime,
) -> tuple[str, dict[str, object] | None, str]:
    """Return (classification, sanitized projection, reason)."""

    if type(payload) is not dict:
        return "UNKNOWN", None, "invalid_pr_observation"
    try:
        if type(payload.get("number")) is not int or payload["number"] != number:
            return "UNKNOWN", None, "pr_identity_mismatch"
        if not _same_api_resource(
            payload.get("url"), repository=repository, kind="pull", number_or_sha=number
        ):
            return "UNKNOWN", None, "pr_identity_mismatch"
        if not _same_repository(
            payload.get("base", {}).get("repo", {}).get("full_name")
            if type(payload.get("base")) is dict
            and type(payload["base"].get("repo")) is dict
            else None,
            repository,
        ):
            return "UNKNOWN", None, "pr_identity_mismatch"
        state = payload.get("state")
        closed = payload.get("closed")
        merged = payload.get("merged")
        if type(state) is not str or state not in {"open", "closed"}:
            return "UNKNOWN", None, "invalid_pr_observation"
        if type(merged) is not bool:
            return "UNKNOWN", None, "invalid_pr_observation"
        if closed is not None and (
            type(closed) is not bool or closed is not (state == "closed")
        ):
            return "UNKNOWN", None, "contradictory_pr_state"
        if merged and state != "closed":
            return "UNKNOWN", None, "contradictory_pr_state"

        head = payload.get("head")
        base = payload.get("base")
        if type(head) is not dict or type(base) is not dict:
            return "UNKNOWN", None, "invalid_pr_observation"
        head_sha = head.get("sha")
        base_ref = base.get("ref")
        if not _strict_sha(head_sha) or type(base_ref) is not str or not base_ref:
            return "UNKNOWN", None, "invalid_pr_observation"
        merged_at_value = payload.get("merged_at")
        merge_sha_value = payload.get("merge_commit_sha")
        if merged:
            if type(merged_at_value) is not str or not _strict_sha(merge_sha_value):
                return "UNKNOWN", None, "invalid_pr_observation"
            merged_at = _parse_utc(merged_at_value)
            if merged_at > response_finished:
                return "UNKNOWN", None, "future_merged_at"
            if merged_at < receipt_started:
                return "UNKNOWN", None, "preexisting_merge"
            if merged_at == receipt_started:
                return "UNKNOWN", None, "ambiguous_merge_time"
        else:
            if merged_at_value is not None:
                return "UNKNOWN", None, "contradictory_pr_state"
            if merge_sha_value is not None and not _strict_sha(merge_sha_value):
                return "UNKNOWN", None, "invalid_pr_observation"
            merged_at = None
            merge_sha_value = None
        projection = {
            "repository": repository,
            "number": number,
            "state": state,
            "merged": merged,
            "merged_at": merged_at_value,
            "head_sha": head_sha,
            "base_ref": base_ref,
            "merge_commit_sha": merge_sha_value,
        }
        if not merged:
            return "UNKNOWN", projection, "unmerged_pr"
        return "VALID", projection, "valid_merged_pr"
    except (TypeError, ValueError, AttributeError, OverflowError):
        return "UNKNOWN", None, "invalid_pr_observation"

def _semantic_commit(payload: object, *, repository: str, expected_sha: str, expected_head: str) -> tuple[str, dict[str, object] | None, str]:
    if type(payload) is not dict:
        return "UNKNOWN", None, "invalid_commit_observation"
    try:
        if not _strict_sha(payload.get("sha")) or payload["sha"] != expected_sha:
            return "UNKNOWN", None, "commit_identity_mismatch"
        if "url" in payload and not _same_api_resource(
            payload["url"], repository=repository, kind="commit", number_or_sha=expected_sha
        ):
            return "UNKNOWN", None, "commit_identity_mismatch"
        parents = payload.get("parents")
        if type(parents) is not list:
            return "UNKNOWN", None, "invalid_parent_shape"
        parent_shas: list[str] = []
        for parent in parents:
            if type(parent) is not dict or not _strict_sha(parent.get("sha")):
                return "UNKNOWN", None, "invalid_parent_shape"
            parent_shas.append(parent["sha"])
        if len(parent_shas) != len(set(parent_shas)):
            return "UNKNOWN", None, "duplicate_parent_sha"
        projection = {"sha": expected_sha, "parents": parent_shas}
        if len(parent_shas) != 2 or parent_shas[1] != expected_head:
            return "MISMATCH", projection, "merge_topology_mismatch"
        return "CONFIRMED", projection, "merge_confirmed"
    except (TypeError, ValueError, AttributeError):
        return "UNKNOWN", None, "invalid_commit_observation"


def _bundle(
    *,
    action: dict[str, object],
    digest: str,
    receipt: dict[str, object],
    receipt_digest: str,
    evidence: dict[str, object],
    status: str,
    observed_at: datetime.datetime,
) -> dict[str, object]:
    state = evidence["state"]
    state_sha = canonical_json_sha256(state) if any(value is not None for value in state.values()) else None
    evidence_sha = canonical_json_sha256(evidence)
    summary = {
        "CONFIRMED": "Observed merged pull request with a confirmed two-parent commit topology.",
        "MISMATCH": "Observed merged pull request or commit topology does not match the frozen action.",
        "UNKNOWN": "Observed GitHub pull request or commit topology is inconclusive.",
    }[status]
    verification = {
        "schema_version": "external-action-verification.v0",
        "action_id": action["action_id"],
        "action_sha256": digest,
        "verification_method": "read_only_external_observation",
        "observed_state": {"summary": summary, "state_sha256": state_sha},
        "evidence_refs": [{"ref_id": "github-readback:" + evidence_sha, "sha256": evidence_sha}],
        "observed_at": _format_utc(observed_at),
        "status": status,
        "receipt_ref": {"ref_id": "receipt:" + action["action_id"], "sha256": receipt_digest},
    }
    try:
        _, checked_verification = validate_receipt_verification_binding(
            receipt,
            verification,
            expected_action_id=action["action_id"],
            expected_action_sha256=digest,
        )
    except (ContractError, TypeError, ValueError):
        raise ContractError(_INVALID) from None
    return {"verification": checked_verification, "evidence": evidence}


def verify_merge_pr(
    frozen_action: FrozenAction,
    receipt: object,
    *,
    opener=None,
) -> dict[str, object]:
    """Produce one bounded public GitHub read-back for a Core merge action."""

    if opener is not None and not callable(opener):
        raise ContractError(_INVALID)
    action, digest = _snapshot_action(frozen_action)
    receipt_value, receipt_digest, receipt_started, receipt_finished = _snapshot_receipt(
        receipt, action, digest
    )
    try:
        parameters = action["execution_parameters"]
        repository = parameters["repository"]
        number = parameters["pull_request"]
        expected_head = parameters["expected_head_sha"]
        expected_base = parameters["expected_base"]
        if (
            type(parameters) is not dict
            or type(repository) is not str
            or type(number) is not int
            or type(expected_head) is not str
            or type(expected_base) is not str
        ):
            raise ContractError(_INVALID)
        parsed_repository = public_observation.parse_github_repository(
            "https://github.com/" + repository
        )
        repository = f"{parsed_repository.owner}/{parsed_repository.repo}"
        action["execution_parameters"]["repository"] = repository
    except (ContractError, KeyError, TypeError, ValueError):
        raise ContractError(_INVALID) from None

    evidence: dict[str, object] = {
        "version": _VERSION,
        "action_id": action["action_id"],
        "action_sha256": digest,
        "transport": "injected" if opener is not None else "default_tokenless",
        "observations": [],
        "state": {"pull_request": None, "commit": None},
        "reason": "readback_started",
    }
    now = _utc_now()
    if now < receipt_finished:
        evidence["reason"] = "receipt_not_finished"
        return _bundle(
            action=action, digest=digest, receipt=receipt_value, receipt_digest=receipt_digest,
            evidence=evidence, status="UNKNOWN", observed_at=now,
        )

    adapter = GitHubObservationAdapter(token=None, opener=opener)
    prior_time = now
    timing_invalid = False

    def finalize(status: str, reason: str) -> dict[str, object]:
        nonlocal timing_invalid
        observed_at = _utc_now()
        if observed_at < prior_time:
            timing_invalid = True
        if timing_invalid:
            status = "UNKNOWN"
            reason = "clock_rollback"
        evidence["reason"] = reason
        return _bundle(
            action=action,
            digest=digest,
            receipt=receipt_value,
            receipt_digest=receipt_digest,
            evidence=evidence,
            status=status,
            observed_at=observed_at,
        )

    def observe(endpoint: str, operation):
        nonlocal prior_time, timing_invalid
        started = _utc_now()
        if started < prior_time:
            timing_invalid = True
        try:
            value = operation()
            return_value = value
        except Exception:
            return_value = None
        finished = _utc_now()
        if finished < started or finished < prior_time:
            timing_invalid = True
        prior_time = finished
        evidence["observations"].append(
            {"endpoint": endpoint, "started_at": _format_utc(started), "finished_at": _format_utc(finished)}
        )
        return return_value

    pr_endpoint = f"{_API_ROOT}/repos/{parsed_repository.owner}/{parsed_repository.repo}/pulls/{number}"
    pr_payload = observe(
        pr_endpoint,
        lambda: adapter.fetch_pull_request(repository, number),
    )
    pr_finished = _parse_utc(evidence["observations"][0]["finished_at"])
    pr_kind, projection, reason = _semantic_pr(
        pr_payload,
        repository=repository,
        number=number,
        response_finished=pr_finished,
        receipt_started=receipt_started,
    )
    if projection is not None:
        evidence["state"]["pull_request"] = projection
    if timing_invalid or pr_payload is None:
        return finalize("UNKNOWN", "clock_rollback" if timing_invalid else reason)
    if pr_kind != "VALID":
        return finalize("UNKNOWN" if pr_kind == "UNKNOWN" else pr_kind, reason)
    pr_projection = projection
    if pr_projection["head_sha"] != expected_head or pr_projection["base_ref"] != expected_base:
        return finalize("MISMATCH", "head_or_base_mismatch")

    merge_sha = pr_projection["merge_commit_sha"]
    commit_endpoint = f"{_API_ROOT}/repos/{parsed_repository.owner}/{parsed_repository.repo}/git/commits/{merge_sha}"
    commit_payload = observe(
        commit_endpoint,
        lambda: adapter.fetch_commit(repository, merge_sha),
    )
    commit_kind, commit_projection, commit_reason = _semantic_commit(
        commit_payload, repository=repository, expected_sha=merge_sha, expected_head=expected_head
    )
    if commit_projection is not None:
        evidence["state"]["commit"] = commit_projection
    return finalize(commit_kind, commit_reason)


__all__ = ["verify_merge_pr"]
