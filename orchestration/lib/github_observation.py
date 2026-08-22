"""One-shot, read-only GitHub source observation and contract mapping."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPException
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from mothership.protocols import ProtocolError, validate_protocol

from .decision import DecisionCardProductionError, build_decision_card
from .errors import ContractError
from .jsonio import loads_strict


_API_ROOT = "https://api.github.com"
_GITHUB_HOST = "github.com"
_TIMEOUT_SECONDS = 5.0
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_NUMBER_DIGITS = 19
_MAX_CANDIDATES = 20
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_NOT_FETCHED = ("comments", "reviews", "files", "checks")
_NOT_EVALUATED = ("body", "labels", "assignees", "milestone")


class GitHubObservationError(ContractError):
    """A GitHub observation could not be obtained or validated."""


@dataclass(frozen=True)
class GitHubRef:
    """A canonical public GitHub web reference and its API endpoint."""

    owner: str
    repo: str
    kind: str
    number: int
    source_url: str
    api_url: str
    evidence_ref: str


@dataclass(frozen=True)
class GitHubRepositoryRef:
    """A canonical public GitHub repository reference and PR list endpoint."""

    owner: str
    repo: str
    source_url: str
    api_url: str


@dataclass(frozen=True)
class GitHubObservation:
    """Selected source facts, with fetch/evaluation boundaries kept explicit."""

    ref: GitHubRef
    title: str
    state: str
    updated_at: str
    draft: bool | None
    head_sha: str | None
    not_fetched: tuple[str, ...] = _NOT_FETCHED
    not_evaluated: tuple[str, ...] = _NOT_EVALUATED

    @property
    def kind(self) -> str:
        return self.ref.kind

    @property
    def number(self) -> int:
        return self.ref.number

    def card_reasons(self) -> tuple[str, ...]:
        """Return source facts suitable for the existing Card reasons array."""

        reasons = [
            f"github.ref={self.ref.source_url}",
            f"github.kind={self.kind}",
            f"github.title={self.title}",
            f"github.state={self.state}",
        ]
        if self.draft is not None:
            reasons.append(f"github.draft={'true' if self.draft else 'false'}")
        if self.head_sha is not None:
            reasons.append(f"github.head_sha={self.head_sha}")
        reasons.append(f"github.updated_at={self.updated_at}")
        return tuple(reasons)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_DEFAULT_OPENER = build_opener(_NoRedirect)


def _default_open(request: Request, *, timeout: float) -> object:
    return _DEFAULT_OPENER.open(request, timeout=timeout)


def _invalid(message: str) -> GitHubObservationError:
    return GitHubObservationError(message)


def _safe_text(value: object, field: str, *, maximum: int = 512) -> str:
    if type(value) is not str:
        raise _invalid(f"GitHub {field} is invalid")
    value = value.strip()
    if not value or len(value) > maximum or _CONTROL.search(value):
        raise _invalid(f"GitHub {field} is invalid")
    return value


def parse_github_ref(ref: object) -> GitHubRef:
    """Parse one explicit public GitHub PR or Issue web URL."""

    if type(ref) is not str:
        raise _invalid("GitHub ref is invalid")
    try:
        parsed = urlsplit(ref)
        port = parsed.port
    except ValueError:
        raise _invalid("GitHub ref is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != _GITHUB_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid("GitHub ref is invalid")

    parts = parsed.path.split("/")
    if len(parts) != 5 or parts[0] or parts[1] == "" or parts[2] == "":
        raise _invalid("GitHub ref is invalid")
    owner, repo, path_kind, raw_number = parts[1:]
    if (
        _SAFE_COMPONENT.fullmatch(owner) is None
        or _SAFE_COMPONENT.fullmatch(repo) is None
        or path_kind not in {"pull", "issues"}
        or re.fullmatch(r"[1-9][0-9]*", raw_number) is None
        or len(raw_number) > _MAX_NUMBER_DIGITS
    ):
        raise _invalid("GitHub ref is invalid")

    try:
        number = int(raw_number)
    except ValueError:
        raise _invalid("GitHub ref is invalid") from None
    kind = "pull_request" if path_kind == "pull" else "issue"
    api_kind = "pulls" if kind == "pull_request" else "issues"
    source_url = f"https://github.com/{owner}/{repo}/{path_kind}/{number}"
    api_url = f"{_API_ROOT}/repos/{owner}/{repo}/{api_kind}/{number}"
    evidence_kind = "pr" if kind == "pull_request" else "issue"
    evidence_ref = f"github-{evidence_kind}-{owner}-{repo}-{number}"
    return GitHubRef(owner, repo, kind, number, source_url, api_url, evidence_ref)


def parse_github_repository(ref: object) -> GitHubRepositoryRef:
    """Parse one explicit public GitHub repository web URL."""

    if type(ref) is not str:
        raise _invalid("GitHub repository ref is invalid")
    try:
        parsed = urlsplit(ref)
        port = parsed.port
    except ValueError:
        raise _invalid("GitHub repository ref is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != _GITHUB_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid("GitHub repository ref is invalid")

    parts = parsed.path.split("/")
    if len(parts) != 3 or parts[0] or parts[1] == "" or parts[2] == "":
        raise _invalid("GitHub repository ref is invalid")
    owner, repo = parts[1:]
    if (
        _SAFE_COMPONENT.fullmatch(owner) is None
        or _SAFE_COMPONENT.fullmatch(repo) is None
        or repo.endswith(".git")
    ):
        raise _invalid("GitHub repository ref is invalid")
    source_url = f"https://github.com/{owner}/{repo}"
    if ref != source_url:
        raise _invalid("GitHub repository ref is invalid")

    return GitHubRepositoryRef(
        owner=owner,
        repo=repo,
        source_url=source_url,
        api_url=f"{_API_ROOT}/repos/{owner}/{repo}/pulls",
    )


def _payload_object(payload: object) -> dict[str, object]:
    if type(payload) is not dict:
        raise _invalid("GitHub response is not an object")
    return payload


def _required(payload: dict[str, object], field: str) -> object:
    if field not in payload:
        raise _invalid(f"GitHub response field is missing: {field}")
    return payload[field]


def _parse_observation(ref: GitHubRef, payload: object) -> GitHubObservation:
    document = _payload_object(payload)
    number = _required(document, "number")
    if type(number) is not int or number != ref.number:
        raise _invalid("GitHub response number does not match ref")
    title = _safe_text(_required(document, "title"), "title")
    state = _required(document, "state")
    if type(state) is not str or state not in {"open", "closed"}:
        raise _invalid("GitHub response state is invalid")
    updated_at = _safe_text(_required(document, "updated_at"), "updated_at", maximum=64)

    draft: bool | None = None
    head_sha: str | None = None
    if ref.kind == "pull_request":
        draft_value = _required(document, "draft")
        if type(draft_value) is not bool:
            raise _invalid("GitHub response draft is invalid")
        draft = draft_value
        head = _required(document, "head")
        if type(head) is not dict:
            raise _invalid("GitHub response head is invalid")
        head_sha_value = _safe_text(head.get("sha"), "head.sha", maximum=40)
        if _SHA.fullmatch(head_sha_value) is None:
            raise _invalid("GitHub response head.sha is invalid")
        head_sha = head_sha_value

    return GitHubObservation(
        ref=ref,
        title=title,
        state=state,
        updated_at=updated_at,
        draft=draft,
        head_sha=head_sha,
    )


def _pull_request_ref(repository: GitHubRepositoryRef, number: int) -> GitHubRef:
    source_url = f"{repository.source_url}/pull/{number}"
    return GitHubRef(
        owner=repository.owner,
        repo=repository.repo,
        kind="pull_request",
        number=number,
        source_url=source_url,
        api_url=f"{_API_ROOT}/repos/{repository.owner}/{repository.repo}/pulls/{number}",
        evidence_ref=f"github-pr-{repository.owner}-{repository.repo}-{number}",
    )


def _fetch_json(request: Request, *, opener: Callable[..., object] | None) -> object:
    open_request = _default_open if opener is None else opener
    try:
        with open_request(request, timeout=_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                raise _invalid("GitHub response status is not successful")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if type(raw) not in (bytes, str) or len(raw) > _MAX_RESPONSE_BYTES:
                raise _invalid("GitHub response is too large")
            return loads_strict(raw)
    except GitHubObservationError:
        raise
    except (
        HTTPError,
        HTTPException,
        URLError,
        TimeoutError,
        OSError,
        RecursionError,
        TypeError,
        ValueError,
        ContractError,
    ) as exc:
        raise GitHubObservationError("GitHub observation failed") from exc


def fetch_github_observation(
    ref: object,
    *,
    opener: Callable[..., object] | None = None,
) -> GitHubObservation:
    """Fetch one explicit ref with one GET and return a validated observation."""

    parsed_ref = parse_github_ref(ref)
    request = Request(
        parsed_ref.api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mothership-github-observation/0",
        },
        method="GET",
    )
    payload = _fetch_json(request, opener=opener)
    return _parse_observation(parsed_ref, payload)


def fetch_github_candidates(
    ref: object,
    *,
    opener: Callable[..., object] | None = None,
) -> tuple[GitHubObservation, ...]:
    """Fetch one bounded page of open PR observations with one GET."""

    repository = parse_github_repository(ref)

    request = Request(
        f"{repository.api_url}?state=open&sort=updated&direction=desc"
        f"&per_page={_MAX_CANDIDATES}&page=1",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mothership-github-observation/0",
        },
        method="GET",
    )
    payload = _fetch_json(request, opener=opener)
    if type(payload) is not list or len(payload) > _MAX_CANDIDATES:
        raise GitHubObservationError("GitHub candidate response is invalid")

    observations: list[GitHubObservation] = []
    for item in payload:
        if type(item) is not dict:
            raise GitHubObservationError("GitHub candidate item is invalid")
        number = item.get("number")
        if (
            type(number) is not int
            or number < 1
            or number >= 10**_MAX_NUMBER_DIGITS
        ):
            raise GitHubObservationError("GitHub candidate number is invalid")
        observation = _parse_observation(_pull_request_ref(repository, number), item)
        if observation.state != "open":
            raise GitHubObservationError("GitHub candidate state is invalid")
        observations.append(observation)
    return tuple(observations)


def map_observation_to_contracts(
    observation: GitHubObservation,
    frontdoor_task: object,
    governance_handoff: object,
) -> tuple[dict[str, object], dict[str, object]]:
    """Map source observation metadata into detached existing protocol objects."""

    if not isinstance(observation, GitHubObservation):
        raise GitHubObservationError("GitHub observation is invalid")
    try:
        frontdoor = validate_protocol("frontdoor-task", frontdoor_task)
        handoff = validate_protocol("governance-handoff", governance_handoff)
    except ProtocolError as exc:
        raise GitHubObservationError("existing contract validation failed") from exc

    unknowns = list(frontdoor["unknowns"])
    for field in observation.not_fetched:
        marker = f"github.not_fetched={field}"
        if marker not in unknowns:
            unknowns.append(marker)
    frontdoor["unknowns"] = unknowns

    evidence_references = list(handoff["evidence_references"])
    if observation.ref.evidence_ref not in evidence_references:
        evidence_references.append(observation.ref.evidence_ref)
    handoff["evidence_references"] = evidence_references
    return frontdoor, handoff


def build_github_decision_card(
    ref: object,
    frontdoor_task: object,
    governance_handoff: object,
    *,
    decision_id: object,
    question: object,
    consequence_if_approved: object,
    recommendation: object = None,
    reasons: object = (),
    router_manifest: object | None = None,
    opener: Callable[..., object] | None = None,
) -> dict[str, object] | None:
    """Fetch one source observation and compose the existing Decision Card."""

    observation = fetch_github_observation(ref, opener=opener)
    mapped_frontdoor, mapped_handoff = map_observation_to_contracts(
        observation,
        frontdoor_task,
        governance_handoff,
    )
    if type(reasons) not in (list, tuple):
        raise DecisionCardProductionError("GitHub Decision Card reasons must be a list")
    card_reasons = list(observation.card_reasons()) + list(reasons)
    return build_decision_card(
        mapped_frontdoor,
        mapped_handoff,
        decision_id=decision_id,
        question=question,
        recommendation=recommendation,
        reasons=card_reasons,
        consequence_if_approved=consequence_if_approved,
        router_manifest=router_manifest,
    )


__all__ = (
    "GitHubObservation",
    "GitHubObservationError",
    "GitHubRef",
    "GitHubRepositoryRef",
    "build_github_decision_card",
    "fetch_github_candidates",
    "fetch_github_observation",
    "map_observation_to_contracts",
    "parse_github_repository",
    "parse_github_ref",
)
