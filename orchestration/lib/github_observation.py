"""Lazy compatibility API for optional GitHub observation.

Core owns no HTTP implementation. Calling an observation API requires the
separately installed, matching mothership-github companion.
"""
from __future__ import annotations

from importlib import import_module
from .errors import ContractError

class GitHubObservationError(ContractError):
    """A GitHub observation could not be obtained or validated."""

class MissingGitHubIntegrationError(GitHubObservationError):
    """The optional GitHub companion is unavailable."""

def require_github_companion():
    try:
        return import_module("mothership_github.public_observation")
    except ModuleNotFoundError as exc:
        if exc.name not in {"mothership_github", "mothership_github.public_observation"}:
            raise
        raise MissingGitHubIntegrationError(
            "GitHub observation requires the matching mothership-github companion"
        ) from None

def parse_github_ref(ref: object):
    return require_github_companion().parse_github_ref(ref)

def parse_github_repository(ref: object):
    return require_github_companion().parse_github_repository(ref)

def fetch_github_observation(ref: object, *, opener=None):
    return require_github_companion().fetch_github_observation(ref, opener=opener)

def fetch_github_candidates(ref: object, *, opener=None):
    return require_github_companion().fetch_github_candidates(ref, opener=opener)

def map_observation_to_contracts(observation, frontdoor_task, governance_handoff):
    return require_github_companion().map_observation_to_contracts(
        observation, frontdoor_task, governance_handoff
    )

def build_github_decision_card(
    ref, frontdoor_task, governance_handoff, *, decision_id, question,
    consequence_if_approved, recommendation=None, reasons=(), router_manifest=None,
    opener=None,
):
    return require_github_companion().build_github_decision_card(
        ref, frontdoor_task, governance_handoff, decision_id=decision_id,
        question=question, consequence_if_approved=consequence_if_approved,
        recommendation=recommendation, reasons=reasons,
        router_manifest=router_manifest, opener=opener,
    )

def __getattr__(name):
    if name in {"GitHubRef", "GitHubRepositoryRef", "GitHubObservation"}:
        return getattr(require_github_companion(), name)
    raise AttributeError(name)

__all__ = (
    "GitHubObservationError", "MissingGitHubIntegrationError", "GitHubRef",
    "GitHubRepositoryRef", "GitHubObservation", "parse_github_ref",
    "parse_github_repository", "fetch_github_observation", "fetch_github_candidates",
    "map_observation_to_contracts", "build_github_decision_card",
)
