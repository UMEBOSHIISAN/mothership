from __future__ import annotations

import json
import io
import ssl
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


class _HostileValue:
    def __str__(self):
        raise AssertionError("hostile value must not be stringified")

    def __repr__(self):
        raise AssertionError("hostile value must not be represented")

    def __eq__(self, other):
        raise AssertionError("hostile value must not be compared")

    def __hash__(self):
        raise AssertionError("hostile value must not be hashed")


class TransportTests(unittest.TestCase):
    def test_preflight_error_has_only_closed_safe_metadata(self):
        error = ActionPreflightError(
            _HostileValue(), reason_code="http_error", http_status=401
        )
        self.assertEqual(("GitHub preflight failed",), error.args)
        self.assertEqual("GitHub preflight failed", str(error))
        self.assertNotIn("secret", repr(error))
        self.assertEqual("http_error", error.reason_code)
        self.assertEqual(401, error.http_status)
        self.assertEqual({"reason_code", "http_status"}, set(vars(error)))

        invalid = ActionPreflightError(
            _HostileValue(), reason_code=_HostileValue(), http_status=_HostileValue()
        )
        self.assertEqual("unexpected_error", invalid.reason_code)
        self.assertIsNone(invalid.http_status)
        self.assertEqual(("GitHub preflight failed",), invalid.args)

        for reason_code in (None, "secret-code", "HTTP_ERROR", _HostileValue()):
            for http_status in (True, 99, 600, "401", _HostileValue()):
                with self.subTest(reason_type=type(reason_code).__name__, status_type=type(http_status).__name__):
                    candidate = ActionPreflightError(
                        _HostileValue(), reason_code=reason_code, http_status=http_status
                    )
                    self.assertEqual("unexpected_error", candidate.reason_code)
                    self.assertIsNone(candidate.http_status)

        for reason_code, http_status in (("secret-code", 401), ("http_error", True)):
            candidate = ActionPreflightError(reason_code=reason_code, http_status=http_status)
            self.assertEqual("unexpected_error", candidate.reason_code)
            self.assertIsNone(candidate.http_status)

    def test_get_success_mapping_and_cleanup_are_unchanged(self):
        response = FakeResponse(
            json.dumps(
                {
                    "number": 1,
                    "state": "open",
                    "merged": False,
                    "head": {"sha": _HEAD},
                    "base": {"ref": "main"},
                }
            )
        )
        opener = FakeOpener(response)
        result = _transport(opener).get_pull_request("owner/repo", 1)
        self.assertEqual(
            {
                "http_status": 200,
                "state": "open",
                "merged": False,
                "head_sha": _HEAD,
                "base_ref": "main",
            },
            result,
        )
        self.assertEqual(1, len(opener.requests))
        self.assertEqual("GET", opener.requests[0][0].get_method())
        self.assertTrue(response.closed)

    def test_get_http_error_categories_preserve_status_without_leaking_error_data(self):
        for status in (401, 403, 500):
            with self.subTest(status=status):
                body = io.BytesIO(b"secret response body")
                error = urllib.error.HTTPError(
                    "https://api.github.com/secret-url",
                    status,
                    "secret exception message",
                    {"X-Secret": "secret header"},
                    body,
                )
                opener = FakeOpener(error=error)
                with self.assertRaises(ActionPreflightError) as raised:
                    _transport(opener).get_pull_request("owner/repo", 1)
                failure = raised.exception
                self.assertIs(type(failure), ActionPreflightError)
                self.assertEqual("http_error", failure.reason_code)
                self.assertEqual(status, failure.http_status)
                self.assertEqual(1, len(opener.requests))
                self.assertTrue(error.closed)
                self.assertNotIn("secret", str(failure))
                self.assertNotIn("secret", repr(failure))
                self.assertNotIn("secret", repr(vars(failure)))

    def test_get_redirect_categories_preserve_status_without_retry(self):
        for status in (300, 301, 302, 307, 399):
            with self.subTest(status=status):
                response = FakeResponse(b"secret redirect body", status=status)
                opener = FakeOpener(response)
                with self.assertRaises(ActionPreflightError) as raised:
                    _transport(opener).get_pull_request("owner/repo", 1)
                failure = raised.exception
                self.assertIs(type(failure), ActionPreflightError)
                self.assertEqual("redirect_rejected", failure.reason_code)
                self.assertEqual(status, failure.http_status)
                self.assertEqual(1, len(opener.requests))
                self.assertTrue(response.closed)
                self.assertNotIn("secret", str(failure))

    def test_get_classifies_direct_and_wrapped_transport_errors(self):
        cases = (
            (TimeoutError("secret timeout"), "timeout"),
            (urllib.error.URLError(TimeoutError("secret timeout")), "timeout"),
            (ssl.SSLError("secret tls"), "tls_error"),
            (urllib.error.URLError(ssl.SSLError("secret tls")), "tls_error"),
            (OSError("secret network"), "network_error"),
            (urllib.error.URLError("secret network"), "network_error"),
        )
        for transport_error, reason_code in cases:
            with self.subTest(reason_code=reason_code, error_type=type(transport_error).__name__):
                opener = FakeOpener(error=transport_error)
                with self.assertRaises(ActionPreflightError) as raised:
                    _transport(opener).get_pull_request("owner/repo", 1)
                failure = raised.exception
                self.assertIs(type(failure), ActionPreflightError)
                self.assertEqual(reason_code, failure.reason_code)
                self.assertIsNone(failure.http_status)
                self.assertEqual(1, len(opener.requests))
                self.assertNotIn("secret", str(failure))
                self.assertIsNone(failure.__cause__)

    def test_get_invalid_response_body_is_response_invalid_with_observed_status(self):
        bodies = (
            b"",
            b"not-json",
            b"[]",
            b'{"state":"open","state":"closed"}',
        )
        for body in bodies:
            with self.subTest(body=body[:20]):
                response = FakeResponse(body, status=200)
                opener = FakeOpener(response)
                with self.assertRaises(ActionPreflightError) as raised:
                    _transport(opener).get_pull_request("owner/repo", 1)
                failure = raised.exception
                self.assertEqual("response_invalid", failure.reason_code)
                self.assertEqual(200, failure.http_status)
                self.assertEqual(1, len(opener.requests))
                self.assertTrue(response.closed)

        response = FakeResponse(b"{}", status=204, headers={"Content-Length": str(1024 * 1024 + 1)})
        opener = FakeOpener(response)
        with self.assertRaises(ActionPreflightError) as raised:
            _transport(opener).get_pull_request("owner/repo", 1)
        self.assertEqual("response_invalid", raised.exception.reason_code)
        self.assertEqual(204, raised.exception.http_status)
        self.assertEqual(1, len(opener.requests))
        self.assertTrue(response.closed)

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
