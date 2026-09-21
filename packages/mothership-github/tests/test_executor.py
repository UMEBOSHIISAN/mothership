from __future__ import annotations

import copy
import datetime
import inspect
import pathlib
import unittest
from unittest import mock

from mothership_github import executor
from orchestration.lib import action_authority


_NOW = datetime.datetime(2026, 9, 21, 10, 0, 0, tzinfo=datetime.UTC)
_HEAD = "a" * 40
_MERGE_SHA = "b" * 40
_PARAMETERS = {
    "repository": "owner/repo",
    "pull_request": 7,
    "expected_head_sha": _HEAD,
    "expected_base": "main",
    "merge_method": "merge",
}


class FakeTransport:
    def __init__(self, mutation=None, *, get_result=None):
        self.mutation = mutation if mutation is not None else {
            "http_status": 200,
            "merged": True,
            "merge_commit_sha": _MERGE_SHA,
        }
        self.get_result = get_result if get_result is not None else {
            "http_status": 200,
            "state": "open",
            "merged": False,
            "head_sha": _HEAD,
            "base_ref": "main",
        }
        self.get_calls = []
        self.put_calls = []

    def get_pull_request(self, repository, pull_request):
        self.get_calls.append((repository, pull_request))
        return copy.deepcopy(self.get_result)

    def merge_pull_request(self, **kwargs):
        self.put_calls.append(copy.deepcopy(kwargs))
        if isinstance(self.mutation, BaseException):
            raise self.mutation
        return copy.deepcopy(self.mutation)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        with mock.patch.object(action_authority, "_utc_now", return_value=_NOW):
            self.frozen = action_authority.freeze_action(
                "act-merge-pr-001", "github.merge_pr", copy.deepcopy(_PARAMETERS)
            )
        self.verified_action = copy.deepcopy(action_authority._thaw_value(self.frozen.action))
        self.authority_path = pathlib.Path("/tmp/option-a-authority.jsonl")
        self.receipt_path = pathlib.Path("/tmp/option-a-receipts.jsonl")
        self.consume_event = {
            "schema_version": "authority-action-consume.v0",
            "event_type": "authority_action_consume",
            "event_id": "event-" + "1" * 32,
            "approval_event_id": "event-" + "2" * 32,
            "action_id": "act-merge-pr-001",
            "action_sha256": self.frozen.action_sha256,
            "consumed_at": "2026-09-21T10:01:00Z",
            "expires_at": self.frozen.expires_at,
        }
        self.started = {
            "schema_version": "github-execution-attempt.v1",
            "event_type": "attempt_started",
            "event_id": "event-start-1",
            "action_id": "act-merge-pr-001",
            "action_sha256": self.frozen.action_sha256,
            "consume_event_id": self.consume_event["event_id"],
            "recorded_at": "2026-09-21T10:01:01Z",
        }
        self.finished = {
            "schema_version": "github-execution-attempt.v1",
            "event_type": "attempt_finished",
            "event_id": "event-finish-1",
            "attempt_started_event_id": self.started["event_id"],
            "outcome": "success",
            "observation": {
                "http_status": 200,
                "merged": True,
                "merge_commit_sha": _MERGE_SHA,
            },
            "recorded_at": "2026-09-21T10:01:02Z",
        }

    def test_public_executor_signature_has_no_aliases_or_clock_override(self):
        self.assertEqual(
            (
                "action_ledger_path",
                "receipt_ledger_path",
                "frozen_action",
                "approval_event_id",
                "transport",
            ),
            tuple(inspect.signature(executor.execute_action_merge_pr).parameters),
        )

    def test_consumes_core_tuple_and_mutates_only_once_from_verified_action(self):
        transport = FakeTransport()
        start = mock.Mock(return_value=self.started)
        finish = mock.Mock(return_value=self.finished)
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=_NOW),
            mock.patch.object(executor, "consume_action", return_value=(self.consume_event, copy.deepcopy(self.verified_action))) as consume,
            mock.patch.object(executor, "record_attempt_started", start),
            mock.patch.object(executor, "record_attempt_finished", finish),
        ):
            result = executor.execute_action_merge_pr(
                self.authority_path,
                self.receipt_path,
                self.frozen,
                "event-" + "2" * 32,
                transport,
            )

        consume.assert_called_once_with(
            self.authority_path,
            "event-" + "2" * 32,
            "act-merge-pr-001",
            self.frozen.action_sha256,
        )
        start.assert_called_once()
        finish.assert_called_once()
        self.assertEqual(1, len(transport.put_calls))
        self.assertEqual(
            {
                "repository": "owner/repo",
                "pull_request": 7,
                "expected_head_sha": _HEAD,
                "merge_method": "merge",
            },
            transport.put_calls[0],
        )
        self.assertEqual("success", result["status"])

    def test_forged_action_is_rejected_before_any_get(self):
        transport = FakeTransport()
        with self.assertRaises(action_authority.MalformedActionError):
            executor.execute_action_merge_pr(
                self.authority_path,
                self.receipt_path,
                {"action": self.frozen.action},
                "event-" + "2" * 32,
                transport,
            )
        self.assertEqual([], transport.get_calls)

    def test_expiry_is_revalidated_after_preflight_before_consume(self):
        transport = FakeTransport()
        expired = action_authority.ExpiredActionError("expired")
        validate = mock.Mock(side_effect=[copy.deepcopy(self.verified_action), expired])
        with (
            mock.patch.object(action_authority, "_validated_frozen_action", validate),
            mock.patch.object(executor, "consume_action") as consume,
        ):
            with self.assertRaises(action_authority.ExpiredActionError):
                executor.execute_action_merge_pr(
                    self.authority_path,
                    self.receipt_path,
                    self.frozen,
                    "event-" + "2" * 32,
                    transport,
                )
        self.assertEqual(1, len(transport.get_calls))
        consume.assert_not_called()
        self.assertEqual([], transport.put_calls)

    def test_changed_core_returned_action_burns_authority_without_put(self):
        transport = FakeTransport()
        changed = copy.deepcopy(self.verified_action)
        changed["execution_parameters"]["repository"] = "other/repo"
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=_NOW),
            mock.patch.object(executor, "consume_action", return_value=(self.consume_event, changed)),
            mock.patch.object(executor, "record_attempt_started") as start,
        ):
            with self.assertRaises(executor.ActionExecutionError):
                executor.execute_action_merge_pr(
                    self.authority_path,
                    self.receipt_path,
                    self.frozen,
                    "event-" + "2" * 32,
                    transport,
                )
        start.assert_not_called()
        self.assertEqual([], transport.put_calls)

    def test_start_failure_consumes_but_never_puts_or_retries(self):
        transport = FakeTransport()
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=_NOW),
            mock.patch.object(executor, "consume_action", return_value=(self.consume_event, copy.deepcopy(self.verified_action))) as consume,
            mock.patch.object(executor, "record_attempt_started", side_effect=OSError("write failed")),
        ):
            with self.assertRaises(OSError):
                executor.execute_action_merge_pr(
                    self.authority_path,
                    self.receipt_path,
                    self.frozen,
                    "event-" + "2" * 32,
                    transport,
                )
        consume.assert_called_once()
        self.assertEqual([], transport.put_calls)

    def test_unknown_put_exception_is_reconciliation_required_and_has_no_retry(self):
        transport = FakeTransport(RuntimeError("opaque transport failure"))
        finish = mock.Mock(return_value=self.finished)
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=_NOW),
            mock.patch.object(executor, "consume_action", return_value=(self.consume_event, copy.deepcopy(self.verified_action))),
            mock.patch.object(executor, "record_attempt_started", return_value=self.started),
            mock.patch.object(executor, "record_attempt_finished", finish),
        ):
            executor.execute_action_merge_pr(
                self.authority_path,
                self.receipt_path,
                self.frozen,
                "event-" + "2" * 32,
                transport,
            )
        self.assertEqual(1, len(transport.put_calls))
        self.assertEqual("reconciliation_required", finish.call_args.args[2])
        self.assertEqual(
            {"http_status", "merged", "merge_commit_sha"},
            set(finish.call_args.args[3]),
        )

    def test_success_aliases_cannot_create_strong_success(self):
        transport = FakeTransport(
            {
                "http_status": 0,
                "success": True,
                "outcome": "success",
                "merged": True,
                "merge_commit_sha": _MERGE_SHA,
            }
        )
        finish = mock.Mock(return_value=self.finished)
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=_NOW),
            mock.patch.object(executor, "consume_action", return_value=(self.consume_event, copy.deepcopy(self.verified_action))),
            mock.patch.object(executor, "record_attempt_started", return_value=self.started),
            mock.patch.object(executor, "record_attempt_finished", finish),
        ):
            executor.execute_action_merge_pr(
                self.authority_path,
                self.receipt_path,
                self.frozen,
                "event-" + "2" * 32,
                transport,
            )
        self.assertEqual("reconciliation_required", finish.call_args.args[2])

    def test_preflight_requires_explicit_unmerged_and_http_success(self):
        for change in ({"merged": None}, {"http_status": 503}, {"http_status": True}):
            facts = FakeTransport().get_result
            facts.update(change)
            with self.subTest(change=change), self.assertRaises(executor.ActionPreflightError):
                executor._validate_preflight(facts, _PARAMETERS)
        facts = FakeTransport().get_result
        del facts["merged"]
        with self.assertRaises(executor.ActionPreflightError):
            executor._validate_preflight(facts, _PARAMETERS)

    def test_contradictory_failure_facts_remain_unresolved(self):
        for status in (302, 409):
            with self.subTest(status=status):
                outcome, _ = executor._normalized_observation({
                    "http_status": status, "merged": True,
                    "merge_commit_sha": _MERGE_SHA,
                    "redirect_rejected": status == 302,
                })
                self.assertEqual("reconciliation_required", outcome)
