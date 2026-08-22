from __future__ import annotations

import json
from http.client import IncompleteRead
import sys
from typing import Any
import unittest
from unittest import mock
from urllib.error import HTTPError

from orchestration.lib.github_observation import (
    GitHubObservationError,
    build_github_decision_card,
    fetch_github_candidates,
    fetch_github_observation,
    map_observation_to_contracts,
    parse_github_repository,
    parse_github_ref,
)


class _Response:
    def __init__(self, payload: object, *, status: int = 200):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._payload

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return "https://api.github.com/repos/UMEBOSHIISAN/mothership/pulls/3"


class _TruncatedResponse(_Response):
    def read(self, _limit: int) -> bytes:
        raise IncompleteRead(b'{"number": 3}', 128)


def pull_request_payload() -> dict[str, Any]:
    return {
        "number": 3,
        "title": "docs: make Mothership the AI agent flight recorder",
        "state": "open",
        "draft": True,
        "updated_at": "2026-08-21T16:16:20Z",
        "head": {"sha": "a" * 40, "ref": "feature/example"},
        "base": {"ref": "main"},
        "body": "untrusted raw body is intentionally not evaluated",
        "labels": [{"name": "documentation"}],
        "comments": 0,
        "requested_reviewers": [],
    }


def issue_payload() -> dict[str, Any]:
    return {
        "number": 7,
        "title": "A bounded issue",
        "state": "open",
        "updated_at": "2026-08-21T17:00:00Z",
        "body": "untrusted issue body is intentionally not evaluated",
        "labels": [],
        "comments": 2,
    }


def candidate_payload(
    number: int,
    *,
    title: str,
    state: str = "open",
    draft: bool = False,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "state": state,
        "draft": draft,
        "updated_at": "2026-08-22T00:00:00Z",
        "head": {"sha": f"{number:02d}" * 20},
    }


def opener_for(payload: object, calls: list[object], *, error: BaseException | None = None):
    def opener(request: object, timeout: float) -> _Response:
        calls.append((request, timeout))
        if error is not None:
            raise error
        return _Response(payload)

    return opener


def frontdoor_task() -> dict[str, object]:
    return {
        "schema_version": "intake.v0",
        "request_id": "github-pr-3-review",
        "human_request": "Review the supplied GitHub observation",
        "task_class": "CODE_REVIEW",
        "risk_tags": [],
        "allowed_actions": ["read GitHub observation", "render Decision Card"],
        "forbidden_actions": ["write GitHub state", "execute commands"],
        "required_evidence": ["GitHub observation"],
        "required_manifest": None,
        "human_gate": "CONFIRM",
        "predicted_worker_capability": "code-review",
        "unknowns": [],
        "assumptions": ["the explicit public GitHub ref is the intended source"],
        "next_safe_step": "Review the fetched GitHub observation",
    }


def governance_handoff() -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "task_id": "github-pr-3-review",
        "capability": "code-review",
        "risk": "medium",
        "token_budget": 4000,
        "evidence_references": ["evidence:base"],
    }


class GitHubObservationTests(unittest.TestCase):
    def test_repository_ref_is_strict_and_candidate_fetch_uses_one_bounded_get(self) -> None:
        calls: list[object] = []
        payload = [
            candidate_payload(3, title="newer", draft=True),
            candidate_payload(2, title="older"),
        ]

        repository = parse_github_repository(
            "https://github.com/UMEBOSHIISAN/mothership"
        )
        observations = fetch_github_candidates(
            repository.source_url,
            opener=opener_for(payload, calls),
        )

        self.assertEqual([3, 2], [observation.number for observation in observations])
        self.assertTrue(observations[0].draft)
        self.assertEqual(1, len(calls))
        request, timeout = calls[0]
        self.assertEqual(5.0, timeout)
        self.assertEqual(
            "https://api.github.com/repos/UMEBOSHIISAN/mothership/pulls"
            "?state=open&sort=updated&direction=desc&per_page=20&page=1",
            request.full_url,
        )
        self.assertEqual("GET", request.get_method())
        self.assertIsNone(request.get_header("Authorization"))

    def test_repository_ref_rejects_noncanonical_public_urls_before_network(self) -> None:
        for ref in (
            "http://github.com/owner/repo",
            "https://evil.example/owner/repo",
            "https://github.com/owner/repo/",
            "https://github.com/owner/repo.git",
            "https://github.com/owner/repo?state=open",
            "https://github.com/owner/repo?",
            "https://github.com/owner/repo#",
            "\nhttps://github.com/owner/repo",
        ):
            with self.subTest(ref=ref):
                with self.assertRaises(GitHubObservationError):
                    parse_github_repository(ref)

    def test_candidate_window_rejects_any_non_200_without_retry(self) -> None:
        for status in (302, 401, 403, 404, 422, 500):
            with self.subTest(status=status):
                calls: list[object] = []

                def opener(request: object, timeout: float, *, status: int = status) -> _Response:
                    calls.append((request, timeout))
                    return _Response([], status=status)

                with self.assertRaises(GitHubObservationError):
                    fetch_github_candidates(
                        "https://github.com/UMEBOSHIISAN/mothership",
                        opener=opener,
                    )

                self.assertEqual(1, len(calls))

    def test_candidate_window_rejects_malformed_json_and_oversized_body(self) -> None:
        for payload in (b"not-json", b"x" * 1_048_577):
            with self.subTest(payload_size=len(payload)):
                calls: list[object] = []
                with self.assertRaises(GitHubObservationError):
                    fetch_github_candidates(
                        "https://github.com/UMEBOSHIISAN/mothership",
                        opener=opener_for(payload, calls),
                    )
                self.assertEqual(1, len(calls))

    def test_candidate_window_deeply_nested_json_fails_closed(self) -> None:
        calls: list[object] = []
        payload = b"[" * 5_000 + b"0" + b"]" * 5_000
        previous_limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(1_000)
            with mock.patch(
                "orchestration.lib.github_observation.loads_strict",
                side_effect=RecursionError(),
            ):
                with self.assertRaises(GitHubObservationError):
                    fetch_github_candidates(
                        "https://github.com/UMEBOSHIISAN/mothership",
                        opener=opener_for(payload, calls),
                    )
        finally:
            sys.setrecursionlimit(previous_limit)

        self.assertEqual(1, len(calls))

    def test_candidate_window_validates_all_items_before_returning(self) -> None:
        calls: list[object] = []
        malformed = candidate_payload(2, title="bad", state="open")
        malformed["draft"] = []

        with self.assertRaises(GitHubObservationError):
            fetch_github_candidates(
                "https://github.com/UMEBOSHIISAN/mothership",
                opener=opener_for(
                    [candidate_payload(3, title="valid"), malformed],
                    calls,
                ),
            )

        self.assertEqual(1, len(calls))

    def test_candidate_window_rejects_oversized_item_number(self) -> None:
        calls: list[object] = []
        malformed = candidate_payload(3, title="bad")
        malformed["number"] = 10**20

        with self.assertRaises(GitHubObservationError):
            fetch_github_candidates(
                "https://github.com/UMEBOSHIISAN/mothership",
                opener=opener_for([malformed], calls),
            )

        self.assertEqual(1, len(calls))

    def test_candidate_window_truncated_response_fails_closed_without_retry(self) -> None:
        calls: list[object] = []

        def opener(request: object, timeout: float) -> _TruncatedResponse:
            calls.append((request, timeout))
            return _TruncatedResponse([])

        with self.assertRaises(GitHubObservationError):
            fetch_github_candidates(
                "https://github.com/UMEBOSHIISAN/mothership",
                opener=opener,
            )

        self.assertEqual(1, len(calls))

    def test_pull_request_fetch_is_one_get_and_preserves_observation_boundary(self) -> None:
        calls: list[object] = []

        observation = fetch_github_observation(
            "https://github.com/UMEBOSHIISAN/mothership/pull/3",
            opener=opener_for(pull_request_payload(), calls),
        )

        self.assertEqual("pull_request", observation.kind)
        self.assertEqual("docs: make Mothership the AI agent flight recorder", observation.title)
        self.assertEqual("open", observation.state)
        self.assertTrue(observation.draft)
        self.assertEqual("a" * 40, observation.head_sha)
        self.assertIn("comments", observation.not_fetched)
        self.assertIn("body", observation.not_evaluated)
        self.assertEqual(1, len(calls))
        request, timeout = calls[0]
        self.assertEqual(5.0, timeout)
        self.assertEqual(
            "https://api.github.com/repos/UMEBOSHIISAN/mothership/pulls/3",
            request.full_url,
        )
        self.assertEqual("GET", request.get_method())
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual("application/vnd.github+json", request.get_header("Accept"))

    def test_issue_fetch_uses_issue_endpoint_without_pr_semantics(self) -> None:
        calls: list[object] = []

        observation = fetch_github_observation(
            "https://github.com/UMEBOSHIISAN/mothership/issues/7",
            opener=opener_for(issue_payload(), calls),
        )

        self.assertEqual("issue", observation.kind)
        self.assertIsNone(observation.draft)
        self.assertIsNone(observation.head_sha)
        self.assertEqual(
            "https://api.github.com/repos/UMEBOSHIISAN/mothership/issues/7",
            calls[0][0].full_url,
        )

    def test_invalid_ref_is_rejected_before_network(self) -> None:
        for ref in (
            "http://github.com/owner/repo/pull/3",
            "https://evil.example/owner/repo/pull/3",
            "https://github.com/owner/repo/pull/3?body=secret",
            "https://github.com/owner/repo/comments/3",
        ):
            with self.subTest(ref=ref):
                with self.assertRaises(GitHubObservationError):
                    parse_github_ref(ref)

    def test_oversized_numeric_ref_fails_closed_before_network(self) -> None:
        calls: list[object] = []
        ref = "https://github.com/owner/repo/pull/" + ("9" * 5000)

        with self.assertRaises(GitHubObservationError):
            fetch_github_observation(
                ref,
                opener=opener_for(pull_request_payload(), calls),
            )

        self.assertEqual([], calls)

    def test_timeout_is_fail_closed_without_retry(self) -> None:
        calls: list[object] = []

        with self.assertRaises(GitHubObservationError):
            fetch_github_observation(
                "https://github.com/UMEBOSHIISAN/mothership/pull/3",
                opener=opener_for(pull_request_payload(), calls, error=TimeoutError()),
            )

        self.assertEqual(1, len(calls))

    def test_http_error_and_malformed_response_are_fail_closed(self) -> None:
        calls: list[object] = []
        not_found = HTTPError(
            "https://api.github.com/repos/UMEBOSHIISAN/mothership/pulls/3",
            404,
            "not found",
            {},
            None,
        )
        with self.assertRaises(GitHubObservationError):
            fetch_github_observation(
                "https://github.com/UMEBOSHIISAN/mothership/pull/3",
                opener=opener_for(pull_request_payload(), calls, error=not_found),
            )

        with self.assertRaises(GitHubObservationError):
            fetch_github_observation(
                "https://github.com/UMEBOSHIISAN/mothership/pull/3",
                opener=opener_for(b"not-json", []),
            )

    def test_truncated_http_response_is_fail_closed_without_retry(self) -> None:
        calls: list[object] = []

        def opener(request: object, timeout: float) -> _TruncatedResponse:
            calls.append((request, timeout))
            return _TruncatedResponse(pull_request_payload())

        with self.assertRaises(GitHubObservationError):
            fetch_github_observation(
                "https://github.com/UMEBOSHIISAN/mothership/pull/3",
                opener=opener,
            )

        self.assertEqual(1, len(calls))

    def test_malformed_state_types_fail_closed_after_one_get(self) -> None:
        for bad_state in ([], {}):
            with self.subTest(state=bad_state):
                calls: list[object] = []
                payload = dict(pull_request_payload(), state=bad_state)

                with self.assertRaises(GitHubObservationError):
                    fetch_github_observation(
                        "https://github.com/UMEBOSHIISAN/mothership/pull/3",
                        opener=opener_for(payload, calls),
                    )

                self.assertEqual(1, len(calls))

    def test_mapping_separates_evidence_reference_facts_and_unknowns(self) -> None:
        calls: list[object] = []
        observation = fetch_github_observation(
            "https://github.com/UMEBOSHIISAN/mothership/pull/3",
            opener=opener_for(pull_request_payload(), calls),
        )
        frontdoor = frontdoor_task()
        handoff = governance_handoff()

        mapped_frontdoor, mapped_handoff = map_observation_to_contracts(
            observation,
            frontdoor,
            handoff,
        )

        self.assertIn("github-pr-UMEBOSHIISAN-mothership-3", mapped_handoff["evidence_references"])
        self.assertIn("github.not_fetched=comments", mapped_frontdoor["unknowns"])
        self.assertIn("github.not_fetched=checks", mapped_frontdoor["unknowns"])
        self.assertNotIn("github.not_evaluated=body", mapped_frontdoor["unknowns"])
        self.assertIn("github.title=docs: make Mothership the AI agent flight recorder", observation.card_reasons())
        self.assertNotIn("github.title", " ".join(mapped_handoff["evidence_references"]))
        self.assertEqual([], frontdoor["unknowns"])
        self.assertEqual(["evidence:base"], handoff["evidence_references"])

    def test_builder_preserves_explicit_recommendation_or_null_and_effects(self) -> None:
        calls: list[object] = []
        card = build_github_decision_card(
            "https://github.com/UMEBOSHIISAN/mothership/pull/3",
            frontdoor_task(),
            governance_handoff(),
            decision_id="decision-github-pr-3-review",
            question="Should the human review this GitHub observation?",
            consequence_if_approved="Only the separately owned review boundary may proceed.",
            opener=opener_for(pull_request_payload(), calls),
        )

        self.assertEqual("decision-card.v0", card["schema_version"])
        self.assertIsNone(card["recommendation"])
        self.assertTrue(any(reason.startswith("github.state=") for reason in card["reasons"]))
        self.assertIn("github.not_fetched=reviews", card["unknowns"])
        self.assertEqual("medium", card["risk"])
        self.assertFalse(card["authority_effect"])
        self.assertFalse(card["execution_effect"])


if __name__ == "__main__":
    unittest.main()
