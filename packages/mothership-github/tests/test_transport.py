from __future__ import annotations

import json
import io
import urllib.error
import unittest
from unittest import mock

from mothership_github.executor import _normalized_observation
from mothership_github.transport import (
    ActionExecutionError,
    ActionPreflightError,
    GitHubRestTransport,
)


_HEAD = "a" * 40
_MERGE_SHA = "b" * 40


class FakeResponse:
    def __init__(self, body=b"", status=200, headers=None):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.status = status
        self.code = status
        self.headers = headers or {}
        self.closed = False

    def read(self, size=-1):
        if size is None or size < 0:
            data, self.body = self.body, b""
            return data
        data, self.body = self.body[:size], self.body[size:]
        return data

    def close(self):
        self.closed = True


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


def _transport(opener):
    return GitHubRestTransport("synthetic-token", opener=opener, timeout=3.0)


class TransportTests(unittest.TestCase):
    def test_base_url_is_pinned_to_exact_github_origin(self):
        for base_url in (
            "https://api.github.com/v3",
            "https://api.github.com?x=1",
            "https://api.github.com#fragment",
            "http://api.github.com",
            "https://evil.example",
            "https://api.github.com//",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ActionExecutionError):
                    GitHubRestTransport("synthetic-token", base_url=base_url)
        GitHubRestTransport("synthetic-token", base_url="https://api.github.com/")

    def test_get_rejects_duplicate_json_keys_without_exposing_body(self):
        opener = FakeOpener(FakeResponse(
            b'{"state":"open","state":"closed","merged":false,"head":{"sha":"%s"},"base":{"ref":"main"}}' % _HEAD.encode()
        ))
        with self.assertRaises(ActionPreflightError):
            _transport(opener).get_pull_request("owner/repo", 1)

    def test_get_requires_bounded_json_object(self):
        body = b"{" + b"x" * (1024 * 1024 + 10) + b"}"
        with self.assertRaises(ActionPreflightError):
            _transport(FakeOpener(FakeResponse(body))).get_pull_request("owner/repo", 1)

    def test_put_success_requires_exact_strong_fields(self):
        body = json.dumps({"merged": True, "sha": _MERGE_SHA}).encode()
        opener = FakeOpener(FakeResponse(body, 200))
        result = _transport(opener).merge_pull_request("owner/repo", 1, _HEAD)
        self.assertEqual(
            {
                "http_status": 200,
                "merged": True,
                "merge_commit_sha": _MERGE_SHA,
            },
            result,
        )
        request, timeout = opener.requests[0]
        self.assertEqual("PUT", request.get_method())
        self.assertEqual(3.0, timeout)
        self.assertEqual("Bearer synthetic-token", request.get_header("Authorization"))

    def test_empty_or_malformed_200_is_ambiguous(self):
        for body in (b"", b"not-json", b'{"merged":true,"sha":"not-a-sha"}'):
            with self.subTest(body=body):
                result = _transport(FakeOpener(FakeResponse(body, 200))).merge_pull_request(
                    "owner/repo", 1, _HEAD
                )
                self.assertEqual(200, result["http_status"])
                self.assertIsNone(result["merged"])
                self.assertIsNone(result["merge_commit_sha"])
                self.assertTrue(result["ambiguous"])

    def test_duplicate_put_json_keys_are_ambiguous(self):
        body = b'{"merged":true,"merged":false,"sha":"' + _MERGE_SHA.encode() + b'"}'
        result = _transport(FakeOpener(FakeResponse(body, 200))).merge_pull_request(
            "owner/repo", 1, _HEAD
        )
        self.assertTrue(result["ambiguous"])
        self.assertIsNone(result["merged"])
        self.assertIsNone(result["merge_commit_sha"])

    def test_5xx_and_timeout_are_ambiguous_but_client_rejection_is_failure(self):
        server = _transport(FakeOpener(FakeResponse(b"", 503))).merge_pull_request(
            "owner/repo", 1, _HEAD
        )
        self.assertTrue(server["ambiguous"])
        timeout = _transport(FakeOpener(error=TimeoutError())).merge_pull_request(
            "owner/repo", 1, _HEAD
        )
        self.assertTrue(timeout["ambiguous"])
        client = _transport(FakeOpener(FakeResponse(b'{"message":"Conflict"}', 409))).merge_pull_request(
            "owner/repo", 1, _HEAD
        )
        self.assertFalse(client.get("ambiguous", False))
        self.assertEqual(409, client["http_status"])

    def test_redirect_is_rejected_without_retry(self):
        opener = FakeOpener(FakeResponse(b"", 302))
        result = _transport(opener).merge_pull_request("owner/repo", 1, _HEAD)
        self.assertTrue(result["redirect_rejected"])
        self.assertEqual(1, len(opener.requests))

    def test_transport_has_no_ambient_token_fallback(self):
        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "ambient"}, clear=True):
            with self.assertRaises(TypeError):
                GitHubRestTransport()


class MutationEvidenceTests(unittest.TestCase):
    def test_no_response_preserves_unknown_merge_and_status(self):
        for error in (TimeoutError(), urllib.error.URLError("synthetic"), RuntimeError("synthetic")):
            with self.subTest(error=type(error).__name__):
                opener = FakeOpener(error=error)
                facts = _transport(opener).merge_pull_request("owner/repo", 1, _HEAD)
                outcome, observation = _normalized_observation(facts)
                self.assertEqual("reconciliation_required", outcome)
                self.assertEqual({"http_status": 0, "merged": None, "merge_commit_sha": None}, observation)
                self.assertEqual(1, len(opener.requests))

    def test_wire_contradiction_survives_response_and_http_error_paths(self):
        for status in (302, 409, 422, 503):
            for as_error in (False, True):
                with self.subTest(status=status, as_error=as_error):
                    body = json.dumps({"merged": True, "sha": _MERGE_SHA}).encode()
                    response = (urllib.error.HTTPError("https://api.github.com", status, "synthetic", {}, io.BytesIO(body))
                                if as_error else FakeResponse(body, status))
                    opener = FakeOpener(error=response) if as_error else FakeOpener(response)
                    facts = _transport(opener).merge_pull_request("owner/repo", 1, _HEAD)
                    outcome, observation = _normalized_observation(facts)
                    self.assertEqual("reconciliation_required", outcome)
                    self.assertEqual({"http_status": status, "merged": True, "merge_commit_sha": _MERGE_SHA}, observation)
                    self.assertEqual(1, len(opener.requests))
                    self.assertTrue(response.closed)

    def test_rejection_does_not_invent_negative_merge_fact(self):
        for data, merged in (({"message": "Conflict"}, None), ({"merged": False}, False)):
            with self.subTest(data=data):
                facts = _transport(FakeOpener(FakeResponse(json.dumps(data), 409))).merge_pull_request("owner/repo", 1, _HEAD)
                outcome, observation = _normalized_observation(facts)
                self.assertEqual("failure", outcome)
                self.assertIs(merged, observation["merged"])
                self.assertIsNone(observation["merge_commit_sha"])

    def test_unreadable_rejection_is_ambiguous_on_both_paths(self):
        bodies = (b"", b"not-json", b'[]', b'{"merged":false,"merged":true}',
                  b'{"merged":"false"}', b'{"sha":"bad"}',
                  json.dumps({"sha": _MERGE_SHA, "merge_commit_sha": "c" * 40}).encode(),
                  b"x" * (1024 * 1024 + 1))
        for body in bodies:
            for as_error in (False, True):
                with self.subTest(body_size=len(body), as_error=as_error):
                    response = (urllib.error.HTTPError("https://api.github.com", 409, "synthetic", {}, io.BytesIO(body))
                                if as_error else FakeResponse(body, 409))
                    facts = _transport(FakeOpener(error=response) if as_error else FakeOpener(response)).merge_pull_request("owner/repo", 1, _HEAD)
                    self.assertEqual("reconciliation_required", _normalized_observation(facts)[0])
                    self.assertTrue(response.closed)
