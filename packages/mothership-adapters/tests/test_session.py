from __future__ import annotations

import copy
import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from mothership_adapters.session import MergeReviewSession, SessionError
from orchestration.lib import action_authority


PARAMETERS = dict(repository="example/repo", pull_request=7, expected_head_sha="a" * 40,
                  expected_base="main", merge_method="merge")
CONTEXT = dict(host_id="test", session_id="session", actor_id="actor",
               runtime_generation="generation", scope=["github.merge_pr"])
REF = dict(ref_id="executor:synthetic", sha256="c" * 64)


def response(request, decision="approve"):
    return dict(schema_version="authority-action-review-response.v0", decision=decision,
                request_id=request["request_id"], request_sha256=request["request_sha256"],
                action_id=request["action"]["action_id"], action_sha256=request["action_sha256"])


class Transport:
    def __init__(self):
        self.gets, self.puts = [], []
        self.on_get = lambda: None
        self.mutation = dict(http_status=200, merged=True, merge_commit_sha="b" * 40)
        self.head = "a" * 40

    def get_pull_request(self, repository, pull_request):
        self.gets.append((repository, pull_request))
        self.on_get()
        return dict(http_status=200, state="open", merged=False,
                    head_sha=self.head, base_ref="main")

    def merge_pull_request(self, **parameters):
        self.puts.append(parameters)
        if isinstance(self.mutation, Exception):
            raise self.mutation
        return self.mutation


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.context = copy.deepcopy(CONTEXT)
        self.transport = Transport()
        self.provider_error = False
        self.session = self.make_session()

    def provider(self):
        if self.provider_error:
            raise RuntimeError("private text must never leave callback")
        return copy.deepcopy(self.context)

    def make_session(self):
        return MergeReviewSession(copy.deepcopy(PARAMETERS), context_provider=self.provider,
                                  authority_path=self.root / "authority.jsonl",
                                  attempts_path=self.root / "attempts.jsonl",
                                  transport=self.transport, executor_ref=REF)

    def rows(self, name):
        path = self.root / name
        return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []

    def approve(self):
        self.assertEqual("approve", self.session.review(response(self.session.request)))

    def test_reject_records_one_decision_without_preflight_or_consume(self):
        self.assertEqual("reject", self.session.review(response(self.session.request, "reject")))
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual("rejected", self.session.state)
        self.assertEqual(["reject"], [row["decision"] for row in self.rows("authority.jsonl")])
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))

    def test_one_approval_one_companion_consume_and_genuine_receipt(self):
        self.approve()
        result = self.session.execute(PARAMETERS)
        self.assertEqual("finished", self.session.state)
        self.assertEqual("SUCCESS", result["receipt"]["status"])
        self.assertEqual("external-action-receipt.v0", result["receipt"]["schema_version"])
        self.assertEqual(result["attempt_started"]["action_sha256"], result["receipt"]["action_sha256"])
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual(["authority_action_approval", "authority_action_consume"],
                         [row["event_type"] for row in self.rows("authority.jsonl")])
        self.assertEqual(2, len(self.rows("attempts.jsonl")))
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.gets))

    def test_execute_without_review_and_duplicate_review_cannot_record_or_execute(self):
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertFalse(self.rows("authority.jsonl"))
        self.approve()
        with self.assertRaises(SessionError):
            self.session.review(response(self.session.request))
        self.assertEqual(1, len(self.rows("authority.jsonl")))

    def test_detached_request_does_not_replace_retained_action(self):
        request = self.session.request
        request["action"]["execution_parameters"]["pull_request"] = 999
        self.assertEqual(7, self.session.request["action"]["execution_parameters"]["pull_request"])
        self.approve()
        result = self.session.execute(PARAMETERS)
        result["receipt"]["status"] = "FAILED"
        self.assertEqual(7, self.transport.puts[0]["pull_request"])

    def test_changed_or_type_coerced_parameters_rejected_before_get(self):
        for change in ({"pull_request": 8}, {"pull_request": 7.0}, {"repository": "other/repo"}):
            self.session = self.make_session()
            self.approve()
            with self.subTest(change=change), self.assertRaises(SessionError):
                self.session.execute({**PARAMETERS, **change})
        self.assertEqual([], self.transport.gets)

    def test_context_drift_on_review_is_terminal_and_records_nothing(self):
        for field in CONTEXT:
            with self.subTest(field=field):
                self.context = copy.deepcopy(CONTEXT)
                session = self.make_session()
                self.context[field] = [] if field == "scope" else "changed"
                with self.assertRaises(SessionError):
                    session.review(response(session.request))
                self.assertEqual("failed", session.state)
        self.assertFalse(self.rows("authority.jsonl"))

    def test_context_drift_after_review_is_rejected_before_get(self):
        self.approve()
        self.context["actor_id"] = "changed"
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual([], self.transport.gets)
        self.assertEqual(1, len(self.rows("authority.jsonl")))

    def test_expired_action_never_preflights(self):
        self.approve()
        later = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=11)
        with patch.object(action_authority, "_utc_now", return_value=later):
            with self.assertRaises(SessionError):
                self.session.execute(PARAMETERS)
        self.assertEqual([], self.transport.gets)

    def test_forged_correlator_records_no_decision(self):
        value = response(self.session.request)
        value["request_id"] = "forged"
        with self.assertRaises(SessionError):
            self.session.review(value)
        self.assertFalse(self.rows("authority.jsonl"))

    def test_provider_exception_sanitized_and_no_get(self):
        self.approve()
        self.provider_error = True
        with self.assertRaisesRegex(SessionError, "^session failed$"):
            self.session.execute(PARAMETERS)
        self.assertEqual([], self.transport.gets)

    def test_creator_pid_fence_rejects_each_public_operation(self):
        with patch("mothership_adapters.session.os.getpid", return_value=os.getpid() + 1):
            for call in (lambda: self.session.request, lambda: self.session.state,
                         lambda: self.session.review({}), lambda: self.session.execute(PARAMETERS),
                         self.session.cancel):
                with self.assertRaises(SessionError):
                    call()
        self.assertFalse(self.rows("authority.jsonl"))

    def test_cancel_before_review_and_after_approval_never_gets(self):
        self.session.cancel()
        with self.assertRaises(SessionError):
            self.session.review(response(self.session.request))
        another = self.make_session()
        another.review(response(another.request))
        another.cancel()
        with self.assertRaises(SessionError):
            another.execute(PARAMETERS)
        self.assertEqual([], self.transport.gets)

    def test_host_context_drift_during_valid_get_burns_consume_no_put_unknown(self):
        self.approve()
        self.transport.on_get = lambda: self.context.update(actor_id="revoked")
        result = self.session.execute(PARAMETERS)
        self.assertEqual("reconciliation_required", result["status"])
        self.assertEqual("UNKNOWN", result["receipt"]["status"])
        self.assertEqual(2, len(self.rows("authority.jsonl")))
        self.assertEqual([], self.transport.puts)
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)

    def test_preflight_head_drift_stops_before_consume(self):
        self.approve()
        self.transport.head = "d" * 40
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.rows("authority.jsonl")))
        self.assertEqual([], self.transport.puts)

    def test_cancel_or_provider_failure_during_get_becomes_unknown_without_put(self):
        for operation in (lambda: self.session.cancel(), lambda: setattr(self, "provider_error", True)):
            with self.subTest(operation=operation):
                self.provider_error = False
                self.session = self.make_session()
                self.approve()
                self.transport.on_get = operation
                result = self.session.execute(PARAMETERS)
                self.assertEqual("UNKNOWN", result["receipt"]["status"])
                self.assertEqual([], self.transport.puts)

    def test_uncertain_put_is_attempted_once_and_never_replayed(self):
        self.approve()
        self.transport.mutation = TimeoutError("response lost")
        result = self.session.execute(PARAMETERS)
        self.assertEqual("UNKNOWN", result["receipt"]["status"])
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.puts))

    def test_concurrent_execute_cannot_send_second_get(self):
        self.approve()
        entered, release = threading.Event(), threading.Event()
        self.transport.on_get = lambda: (entered.set(), release.wait(5))
        results = []
        thread = threading.Thread(target=lambda: results.append(self.session.execute(PARAMETERS)))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(SessionError):
                self.session.execute(PARAMETERS)
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(1, len(results))
        self.assertEqual(1, len(self.transport.puts))

    def test_reentrant_execute_from_transport_cannot_claim_another_attempt(self):
        self.approve()
        def nested():
            with self.assertRaises(SessionError):
                self.session.execute(PARAMETERS)
        self.transport.on_get = nested
        self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))

    def test_cancel_inside_inflight_put_does_not_hide_observed_success(self):
        self.approve()
        original = self.transport.merge_pull_request
        def merge(**parameters):
            self.session.cancel()
            return original(**parameters)
        self.transport.merge_pull_request = merge
        result = self.session.execute(PARAMETERS)
        self.assertEqual("SUCCESS", result["receipt"]["status"])
        self.assertEqual("finished", self.session.state)

    def test_finish_write_failure_preserves_consumed_start_without_inventing_receipt(self):
        self.approve()
        with patch("mothership_github.executor.record_attempt_finished", side_effect=OSError("private")):
            with self.assertRaisesRegex(SessionError, "^session failed$"):
                self.session.execute(PARAMETERS)
        self.assertEqual("failed", self.session.state)
        self.assertEqual(2, len(self.rows("authority.jsonl")))
        self.assertEqual(1, len(self.rows("attempts.jsonl")))
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)

    def test_cancel_then_finish_failure_is_failed_with_consumed_authority(self):
        self.approve()
        original = self.transport.merge_pull_request
        def merge(**parameters):
            self.session.cancel()
            return original(**parameters)
        self.transport.merge_pull_request = merge
        with patch("mothership_github.executor.record_attempt_finished", side_effect=OSError("private")):
            with self.assertRaises(SessionError):
                self.session.execute(PARAMETERS)
        self.assertEqual("failed", self.session.state)
        self.assertEqual(2, len(self.rows("authority.jsonl")))
        self.assertEqual(1, len(self.rows("attempts.jsonl")))
        self.assertEqual(1, len(self.transport.puts))

    def test_cancel_during_review_ledger_error_is_failed_without_execution(self):
        def failed_record(*args, **kwargs):
            self.session.cancel()
            raise OSError("private ledger error")
        with patch("mothership_adapters.session.record_action_decision", side_effect=failed_record):
            with self.assertRaisesRegex(SessionError, "^session failed$"):
                self.session.review(response(self.session.request))
        self.assertEqual("failed", self.session.state)
        self.assertFalse(self.rows("authority.jsonl"))
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))
        with self.assertRaises(SessionError):
            self.session.review(response(self.session.request))

    def test_direct_error_diagnostic_is_fresh_finite_and_secret_free(self):
        error = SessionError("private token should never leave the exception")
        first = error.diagnostic
        self.assertEqual({
            "code": "unknown",
            "phase": "unknown",
            "authority_use": "unknown",
            "external_effect": "unknown",
            "next_check": "existing_evidence_bundle",
            "retry_allowed": False,
        }, first)
        self.assertIsNot(first, error.diagnostic)
        first["code"] = "tampered"
        self.assertEqual("unknown", error.diagnostic["code"])
        self.assertNotIn("private", json.dumps(error.diagnostic))

    def test_session_error_preserves_valueerror_constructor_arity(self):
        for args in ((), ("one",), ("one", "two")):
            with self.subTest(args=args):
                expected = ValueError(*args)
                actual = SessionError(*args)
                self.assertEqual(expected.args, actual.args)
                self.assertEqual(str(expected), str(actual))
                self.assertEqual("unknown", actual.diagnostic["code"])
                self.assertEqual("unknown", actual.diagnostic["phase"])
                self.assertFalse(actual.diagnostic["retry_allowed"])

    def test_review_validation_diagnostic_is_scoped_and_detached(self):
        value = response(self.session.request)
        value["request_id"] = "review-secret-token"
        with self.assertRaises(SessionError) as raised:
            self.session.review(value)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("review_validation", diagnostic["phase"])
        self.assertEqual("review_validation_failed", diagnostic["code"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["authority_use"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["external_effect"])
        self.assertEqual("review_request", diagnostic["next_check"])
        self.assertFalse(diagnostic["retry_allowed"])
        self.assertNotIn("review-secret-token", json.dumps(diagnostic))
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)

    def test_decision_record_failure_points_to_authority_records(self):
        def failed_record(*args, **kwargs):
            raise OSError("ledger-secret-token")
        with patch("mothership_adapters.session.record_action_decision", side_effect=failed_record):
            with self.assertRaises(SessionError) as raised:
                self.session.review(response(self.session.request))
        diagnostic = raised.exception.diagnostic
        self.assertEqual("decision_record", diagnostic["phase"])
        self.assertEqual("decision_record_failed", diagnostic["code"])
        self.assertEqual("authority_records", diagnostic["next_check"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["authority_use"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["external_effect"])
        self.assertNotIn("ledger-secret-token", json.dumps(diagnostic))
        self.assertEqual([], self.transport.puts)

    def test_execution_parameter_failure_is_pre_companion_and_does_no_io(self):
        self.approve()
        with self.assertRaises(SessionError) as raised:
            self.session.execute({**PARAMETERS, "repository": "secret/repository"})
        diagnostic = raised.exception.diagnostic
        self.assertEqual("execution_validation", diagnostic["phase"])
        self.assertEqual("execution_validation_failed", diagnostic["code"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["authority_use"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["external_effect"])
        self.assertEqual("review_request_and_existing_records", diagnostic["next_check"])
        self.assertNotIn("secret/repository", json.dumps(diagnostic))
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)

    def test_preflight_transport_phase_is_unknown_after_companion_entry(self):
        self.approve()
        self.transport.on_get = lambda: (_ for _ in ()).throw(
            OSError("transport-secret-token")
        )
        with self.assertRaises(SessionError) as raised:
            self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("preflight_transport", diagnostic["phase"])
        self.assertEqual("preflight_transport_failed", diagnostic["code"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual("authority_and_attempt_records", diagnostic["next_check"])
        self.assertNotIn("transport-secret-token", json.dumps(diagnostic))
        self.assertEqual([], self.transport.puts)

    def test_finish_write_failure_before_persist_keeps_last_transport_phase(self):
        self.approve()
        with patch("mothership_github.executor.record_attempt_finished",
                   side_effect=OSError("finish-secret-token")):
            with self.assertRaises(SessionError) as raised:
                self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("mutation_returned", diagnostic["phase"])
        self.assertEqual("mutation_returned_failed", diagnostic["code"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual("authority_and_attempt_records", diagnostic["next_check"])
        self.assertNotIn("finish-secret-token", json.dumps(diagnostic))
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual("failed", self.session.state)

    def test_after_write_failure_keeps_mutation_transport_phase(self):
        self.approve()
        self.transport.mutation = TimeoutError("put-secret-token")
        with patch("mothership_github.executor.record_attempt_finished",
                   side_effect=OSError("finish-secret-token")):
            with self.assertRaises(SessionError) as raised:
                self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("mutation_transport", diagnostic["phase"])
        self.assertEqual("mutation_transport_failed", diagnostic["code"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual("authority_and_attempt_records", diagnostic["next_check"])
        self.assertNotIn("put-secret-token", json.dumps(diagnostic))
        self.assertEqual(1, len(self.transport.puts))

    def test_receipt_projection_failure_uses_existing_evidence_bundle(self):
        self.approve()
        with patch("mothership_adapters.session.build_external_action_receipt",
                   side_effect=ValueError("receipt-secret-token")):
            with self.assertRaises(SessionError) as raised:
                self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("receipt_build", diagnostic["phase"])
        self.assertEqual("receipt_build_failed", diagnostic["code"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual("existing_evidence_bundle", diagnostic["next_check"])
        self.assertNotIn("receipt-secret-token", json.dumps(diagnostic))
        self.assertEqual(1, len(self.transport.puts))

    def test_duplicate_and_reentrant_failures_have_independent_diagnostics_and_no_new_io(self):
        self.approve()
        nested = []

        def reentrant_get():
            try:
                self.session.execute(PARAMETERS)
            except SessionError as error:
                nested.append(error)

        self.transport.on_get = reentrant_get
        self.session.execute(PARAMETERS)
        self.assertEqual(1, len(nested))
        self.assertEqual("unknown", nested[0].diagnostic["phase"])
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))
        with self.assertRaises(SessionError) as raised:
            self.session.execute(PARAMETERS)
        duplicate = raised.exception.diagnostic
        self.assertEqual("unknown", duplicate["phase"])
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))
        self.assertIsNot(nested[0].diagnostic, duplicate)

    def test_decision_after_persist_failure_retains_row_and_does_not_attempt_execution(self):
        from mothership.action_authority import record_action_decision as real_record

        def append_then_raise(*args, **kwargs):
            result = real_record(*args, **kwargs)
            raise OSError("decision-after-persist")

        with patch("mothership_adapters.session.record_action_decision",
                   side_effect=append_then_raise):
            with self.assertRaises(SessionError) as raised:
                self.session.review(response(self.session.request))
        diagnostic = raised.exception.diagnostic
        self.assertEqual("decision_record", diagnostic["phase"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["authority_use"])
        self.assertEqual("not_attempted BY THIS CALL", diagnostic["external_effect"])
        self.assertEqual(["authority_action_approval"],
                         [row["event_type"] for row in self.rows("authority.jsonl")])
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))
        with self.assertRaises(SessionError):
            self.session.review(response(self.session.request))
        self.assertEqual(1, len(self.rows("authority.jsonl")))

    def test_consume_after_persist_failure_retains_row_without_start_or_put(self):
        from mothership_github import executor as github_executor

        self.approve()
        real_consume = github_executor.consume_action

        def consume_then_raise(*args, **kwargs):
            result = real_consume(*args, **kwargs)
            raise OSError("consume-after-persist")

        with patch("mothership_github.executor.consume_action", side_effect=consume_then_raise):
            with self.assertRaises(SessionError) as raised:
                self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("preflight_returned", diagnostic["phase"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual(["authority_action_approval", "authority_action_consume"],
                         [row["event_type"] for row in self.rows("authority.jsonl")])
        self.assertEqual([], self.rows("attempts.jsonl"))
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual([], self.transport.puts)
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual([], self.transport.puts)
        self.assertEqual(2, len(self.rows("authority.jsonl")))

    def test_attempt_start_after_persist_failure_retains_row_without_put(self):
        from mothership_github import executor as github_executor

        self.approve()
        real_start = github_executor.record_attempt_started

        def start_then_raise(*args, **kwargs):
            result = real_start(*args, **kwargs)
            raise OSError("start-after-persist")

        with patch("mothership_github.executor.record_attempt_started", side_effect=start_then_raise):
            with self.assertRaises(SessionError) as raised:
                self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("preflight_returned", diagnostic["phase"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual(2, len(self.rows("authority.jsonl")))
        self.assertEqual(["attempt_started"],
                         [row["event_type"] for row in self.rows("attempts.jsonl")])
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual([], self.transport.puts)
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual([], self.transport.puts)
        self.assertEqual(1, len(self.rows("attempts.jsonl")))

    def test_attempt_finish_after_persist_failure_retains_terminal_row_without_replay(self):
        from mothership_github import executor as github_executor

        self.approve()
        real_finish = github_executor.record_attempt_finished

        def finish_then_raise(*args, **kwargs):
            result = real_finish(*args, **kwargs)
            raise OSError("finish-after-persist")

        with patch("mothership_github.executor.record_attempt_finished", side_effect=finish_then_raise):
            with self.assertRaises(SessionError) as raised:
                self.session.execute(PARAMETERS)
        diagnostic = raised.exception.diagnostic
        self.assertEqual("mutation_returned", diagnostic["phase"])
        self.assertEqual("unknown", diagnostic["authority_use"])
        self.assertEqual("unknown", diagnostic["external_effect"])
        self.assertEqual(2, len(self.rows("authority.jsonl")))
        self.assertEqual(["attempt_started", "attempt_finished"],
                         [row["event_type"] for row in self.rows("attempts.jsonl")])
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))
        with self.assertRaises(SessionError):
            self.session.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual(2, len(self.rows("attempts.jsonl")))

    def test_consume_and_start_before_persist_failures_leave_expected_rows_only(self):
        from mothership_github import executor as github_executor

        for stage in ("consume", "start"):
            with self.subTest(stage=stage):
                transport = Transport()
                authority_path = self.root / f"{stage}-authority.jsonl"
                attempts_path = self.root / f"{stage}-attempts.jsonl"
                session = MergeReviewSession(
                    copy.deepcopy(PARAMETERS),
                    context_provider=self.provider,
                    authority_path=authority_path,
                    attempts_path=attempts_path,
                    transport=transport,
                    executor_ref=REF,
                )
                session.review(response(session.request))
                target = ("mothership_github.executor.consume_action"
                          if stage == "consume"
                          else "mothership_github.executor.record_attempt_started")
                with patch(target, side_effect=OSError(f"{stage}-before-persist")):
                    with self.assertRaises(SessionError) as raised:
                        session.execute(PARAMETERS)
                diagnostic = raised.exception.diagnostic
                self.assertEqual("preflight_returned", diagnostic["phase"])
                self.assertEqual("unknown", diagnostic["authority_use"])
                self.assertEqual("unknown", diagnostic["external_effect"])
                authority_rows = [json.loads(row) for row in authority_path.read_text().splitlines()]
                attempt_rows = [json.loads(row) for row in attempts_path.read_text().splitlines()] \
                    if attempts_path.exists() else []
                expected_authority = (1 if stage == "consume" else 2)
                self.assertEqual(expected_authority, len(authority_rows))
                self.assertEqual([] if stage == "consume" else ["authority_action_consume"],
                                 [row["event_type"] for row in authority_rows[1:]])
                self.assertEqual([], attempt_rows)
                self.assertEqual(1, len(transport.gets))
                self.assertEqual([], transport.puts)
                with self.assertRaises(SessionError):
                    session.execute(PARAMETERS)
                self.assertEqual(1, len(transport.gets))
                self.assertEqual([], transport.puts)
