"""Bounded, single-attempt GitHub REST transport for the Option A executor.

The transport accepts a token explicitly at construction time.  It does not
look in the environment, persist response bodies, or follow redirects.  PUT
responses are deliberately kept as a small internal fact mapping; the
executor is responsible for converting that mapping into the closed receipt
observation.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Protocol

from orchestration.lib import jsonio
from orchestration.lib.action_authority import ActionAuthorityError


_BASE_URL = "https://api.github.com"
_ALLOWED_HOST = "api.github.com"
_MAX_RESPONSE_BYTES = 1024 * 1024
_REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_MISSING = object()


class ActionExecutionError(ActionAuthorityError):
    """Raised when an execution transport input is invalid."""


class ActionPreflightError(ActionAuthorityError):
    """Raised when a read-only GitHub preflight cannot be accepted."""


class GitHubTransport(Protocol):
    """The minimal transport surface used by the bounded executor."""

    def get_pull_request(self, repository: str, pull_request: int) -> dict[str, Any]:
        """Return normalized read-only facts for one pull request."""

    def merge_pull_request(
        self,
        repository: str,
        pull_request: int,
        expected_head_sha: str,
        merge_method: str = "merge",
        commit_title: str | None = None,
        commit_message: str | None = None,
    ) -> dict[str, Any]:
        """Perform the one allowed PUT and return bounded mutation facts."""


class _StrictNoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject every redirect before urllib can issue a follow-up request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "HTTP redirect rejected",
            headers,
            fp,
        )

    def _reject(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "HTTP redirect rejected",
            headers,
            fp,
        )

    def http_error_300(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)

    def http_error_301(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)

    def http_error_302(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)

    def http_error_303(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)

    def http_error_305(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)

    def http_error_307(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)

    def http_error_308(self, req, fp, code, msg, headers):
        return self._reject(req, fp, code, msg, headers)


class _ResponseError(Exception):
    """Internal bounded-response failure; its text never crosses the API."""


def _strict_json_object(raw: bytes) -> dict[str, object]:
    if not raw:
        raise _ResponseError
    try:
        value = jsonio.loads_strict(raw)
    except Exception:
        raise _ResponseError from None
    if not isinstance(value, dict):
        raise _ResponseError
    return value


def _status_code(response: object) -> int:
    for name in ("status", "code"):
        value = getattr(response, name, None)
        if type(value) is int and 100 <= value <= 599:
            return value
    return 0


def _read_bounded(response: object) -> bytes:
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        length = headers.get("Content-Length")
        if length is not None:
            try:
                if int(length) > _MAX_RESPONSE_BYTES:
                    raise _ResponseError
            except (TypeError, ValueError):
                raise _ResponseError from None
    reader = getattr(response, "read", None)
    if not callable(reader):
        raise _ResponseError
    try:
        raw = reader(_MAX_RESPONSE_BYTES + 1)
    except Exception:
        raise _ResponseError from None
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or len(raw) > _MAX_RESPONSE_BYTES:
        raise _ResponseError
    return raw


def _close(response: object | None) -> None:
    closer = getattr(response, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass


def _failure(status: int, *, ambiguous: bool = False, redirect_rejected: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "http_status": status if status == 0 or 100 <= status <= 599 else 0,
        "merged": None,
        "merge_commit_sha": None,
    }
    if ambiguous:
        result["ambiguous"] = True
    if redirect_rejected:
        result["redirect_rejected"] = True
    return result


def _wire_mutation_result(data: Mapping[str, object], status: int) -> dict[str, Any]:
    # A rejection status classifies the request, not the PR's merge state.
    # Preserve only explicitly observed facts, including contradictions that
    # the executor must keep unresolved. HTTP 200 still requires strong facts.
    result = _failure(status, redirect_rejected=300 <= status <= 399)
    ambiguous = status == 0 or status >= 500 or not (200 == status or 300 <= status <= 499)
    explicit_ambiguous = data.get("ambiguous", False)
    if type(explicit_ambiguous) is not bool or explicit_ambiguous:
        ambiguous = True

    merged = data.get("merged", _MISSING)
    if type(merged) is bool:
        result["merged"] = merged
    elif (merged is not _MISSING and merged is not None) or status == 200:
        ambiguous = True

    sha_values = [data[key] for key in ("sha", "merge_commit_sha") if key in data]
    sha = sha_values[0] if sha_values else None
    if len(sha_values) == 2 and sha_values[0] != sha_values[1]:
        ambiguous = True
    elif type(sha) is str and _SHA_PATTERN.fullmatch(sha):
        result["merge_commit_sha"] = sha
    elif sha is not None or status == 200:
        ambiguous = True
    if status == 200 and (
        type(merged) is not bool
        or result["merge_commit_sha"] is None
        or type(explicit_ambiguous) is not bool
    ):
        return _failure(status, ambiguous=True)
    if ambiguous:
        result["ambiguous"] = True
    return result


def _mutation_response(response: object) -> dict[str, Any]:
    """Inspect one bounded body on both ordinary and HTTPError responses."""
    status = _status_code(response)
    try:
        data = _strict_json_object(_read_bounded(response))
    except _ResponseError:
        return _failure(status, ambiguous=True, redirect_rejected=300 <= status <= 399)
    return _wire_mutation_result(data, status)


def _validate_repository(repository: object) -> str:
    if type(repository) is not str or not _REPO_PATTERN.fullmatch(repository):
        raise ActionExecutionError("repository is invalid")
    return repository


def _validate_pull_request(pull_request: object) -> int:
    if type(pull_request) is not int or pull_request <= 0:
        raise ActionExecutionError("pull_request is invalid")
    return pull_request


def _validate_sha(value: object) -> str:
    if type(value) is not str or not _SHA_PATTERN.fullmatch(value):
        raise ActionExecutionError("expected_head_sha is invalid")
    return value


class GitHubRestTransport:
    """REST transport pinned to the GitHub API origin with no retries."""

    def __init__(
        self,
        token: str,
        base_url: str = _BASE_URL,
        timeout: float = 15.0,
        user_agent: str = "mothership-executor/1.0",
        opener: Any | None = None,
    ) -> None:
        if type(token) is not str or not token or token != token.strip():
            raise ActionExecutionError("explicit GitHub token is required")
        if type(base_url) is not str or base_url not in {_BASE_URL, _BASE_URL + "/"}:
            raise ActionExecutionError("base_url must be exactly https://api.github.com")
        if type(timeout) not in {int, float} or isinstance(timeout, bool) or timeout <= 0:
            raise ActionExecutionError("timeout is invalid")
        if type(user_agent) is not str or not user_agent:
            raise ActionExecutionError("user_agent is invalid")
        self._token = token
        self._base_url = _BASE_URL
        self._timeout = timeout
        self._user_agent = user_agent
        self._opener = opener if opener is not None else urllib.request.build_opener(_StrictNoRedirectHandler())

    def _build_request(self, method: str, path: str, body: bytes | None = None) -> urllib.request.Request:
        url = f"{self._base_url}/{path.lstrip('/')}"
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != _ALLOWED_HOST
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ActionExecutionError("request URL is outside the pinned GitHub origin")
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", self._user_agent)
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        return request

    def get_pull_request(self, repository: str, pull_request: int) -> dict[str, Any]:
        repository = _validate_repository(repository)
        pull_request = _validate_pull_request(pull_request)
        request = self._build_request("GET", f"repos/{repository}/pulls/{pull_request}")
        response: object | None = None
        try:
            response = self._opener.open(request, timeout=self._timeout)
            status = _status_code(response)
            if 300 <= status <= 399:
                raise ActionPreflightError("GitHub redirect rejected during preflight")
            if status < 200 or status >= 300:
                raise ActionPreflightError("GitHub preflight returned a non-success status")
            data = _strict_json_object(_read_bounded(response))
            number = data.get("number")
            state = data.get("state")
            merged = data.get("merged")
            head = data.get("head")
            base = data.get("base")
            if (
                type(number) is not int
                or number != pull_request
                or type(state) is not str
                or type(merged) is not bool
                or not isinstance(head, Mapping)
                or not isinstance(base, Mapping)
                or type(head.get("sha")) is not str
                or type(base.get("ref")) is not str
            ):
                raise ActionPreflightError("GitHub preflight response was malformed")
            return {
                "http_status": status,
                "state": state,
                "merged": merged,
                "head_sha": head["sha"],
                "base_ref": base["ref"],
            }
        except ActionPreflightError:
            raise
        except urllib.error.HTTPError as error:
            status = _status_code(error)
            if 300 <= status <= 399:
                raise ActionPreflightError("GitHub redirect rejected during preflight") from None
            raise ActionPreflightError("GitHub preflight request failed") from None
        except (TimeoutError, urllib.error.URLError, _ResponseError):
            raise ActionPreflightError("GitHub preflight could not be read") from None
        except Exception:
            raise ActionPreflightError("GitHub preflight failed") from None
        finally:
            _close(response)

    def merge_pull_request(
        self,
        repository: str,
        pull_request: int,
        expected_head_sha: str,
        merge_method: str = "merge",
        commit_title: str | None = None,
        commit_message: str | None = None,
    ) -> dict[str, Any]:
        repository = _validate_repository(repository)
        pull_request = _validate_pull_request(pull_request)
        expected_head_sha = _validate_sha(expected_head_sha)
        if merge_method != "merge":
            raise ActionExecutionError("merge_method is invalid")
        payload: dict[str, object] = {
            "sha": expected_head_sha,
            "merge_method": merge_method,
        }
        if commit_title is not None:
            if type(commit_title) is not str:
                raise ActionExecutionError("commit_title is invalid")
            payload["commit_title"] = commit_title
        if commit_message is not None:
            if type(commit_message) is not str:
                raise ActionExecutionError("commit_message is invalid")
            payload["commit_message"] = commit_message
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        request = self._build_request(
            "PUT", f"repos/{repository}/pulls/{pull_request}/merge", body=body
        )
        response: object | None = None
        try:
            response = self._opener.open(request, timeout=self._timeout)
            return _mutation_response(response)
        except urllib.error.HTTPError as error:
            response = error
            return _mutation_response(error)
        except (TimeoutError, urllib.error.URLError, _ResponseError):
            return _failure(0, ambiguous=True)
        except Exception:
            return _failure(0, ambiguous=True)
        finally:
            _close(response)


__all__ = [
    "ActionExecutionError",
    "ActionPreflightError",
    "GitHubRestTransport",
    "GitHubTransport",
]
