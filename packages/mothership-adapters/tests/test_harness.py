from __future__ import annotations

import copy
from dataclasses import replace
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import patch


# The bridge is qualified against the real Harness state implementation.  The
# fixture is local and read-only from the bridge's perspective; only this test
# adds its source directory to sys.path.
_fixture_path = os.environ.get("MOTHERSHIP_HARNESS_ROOT")
if not _fixture_path:
    raise unittest.SkipTest("set MOTHERSHIP_HARNESS_ROOT for pinned real Harness fixture qualification")
HARNESS_ROOT = Path(_fixture_path).resolve()
if not HARNESS_ROOT.is_dir():
    raise unittest.SkipTest("selected real Harness fixture is unavailable")
from tools.qualify_harness_bridge import check_checkout  # noqa: E402

check_checkout(HARNESS_ROOT)
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))
if str(HARNESS_ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT / "runtime"))

from local_execution_lease import (  # noqa: E402
    CanonicalTaskReference,
    PolicyReference,
    RuntimeContext,
    derive_lease,
)
from local_execution_lease_state import (  # noqa: E402
    LeaseLifecycle,
    LeaseStateStore,
    ObservedExecutionState,
)

from mothership_adapters.harness import (  # noqa: E402
    HarnessBridgeError,
    HarnessMergeBridge,
)
from mothership_adapters.session import SessionError  # noqa: E402


PARAMETERS = {
    "repository": "example/repo",
    "pull_request": 7,
    "expected_head_sha": "a" * 40,
    "expected_base": "main",
    "merge_method": "merge",
}
CONTEXT = {
    "host_id": "test-host",
    "session_id": "session",
    "actor_id": "actor",
    "runtime_generation": "generation",
    "scope": ["github.merge_pr"],
}
REF = {"ref_id": "executor:synthetic", "sha256": "c" * 64}


def approval_response(request: dict[str, object], decision: str = "approve") -> dict[str, object]:
    return {
        "schema_version": "authority-action-review-response.v0",
        "decision": decision,
        "request_id": request["request_id"],
        "request_sha256": request["request_sha256"],
        "action_id": request["action"]["action_id"],
        "action_sha256": request["action_sha256"],
    }


class SyntheticTransport:
    def __init__(self) -> None:
        self.gets: list[tuple[str, int]] = []
        self.puts: list[dict[str, object]] = []
        self.on_get = lambda: None
        self.mutation: object = {
            "http_status": 200,
            "merged": True,
            "merge_commit_sha": "b" * 40,
        }

    def get_pull_request(self, repository: str, pull_request: int) -> dict[str, object]:
        self.gets.append((repository, pull_request))
        self.on_get()
        return {
            "http_status": 200,
            "state": "open",
            "merged": False,
            "head_sha": PARAMETERS["expected_head_sha"],
            "base_ref": PARAMETERS["expected_base"],
        }

    def merge_pull_request(self, **parameters: object) -> object:
        self.puts.append(parameters)
        if isinstance(self.mutation, Exception):
            raise self.mutation
        return self.mutation


class HarnessBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.clock_now = int(time.time())
        self.observed = ObservedExecutionState(
            starting_head="a" * 40,
            status_digest="b" * 64,
            tree_digest="c" * 64,
        )
        self.store = LeaseStateStore(
            self.root / "lease-state.json",
            clock=lambda: self.clock_now,
            observer=lambda state: self.observed,
        )
        self.lease = derive_lease(
            CanonicalTaskReference(
                task_id="portable-host-core-20261005",
                task_contract_sha256="1" * 64,
                allowed_capabilities=frozenset({"edit", "test"}),
                test_profile="unit",
            ),
            PolicyReference(
                policy_id="policy-v0",
                policy_sha256="2" * 64,
                allowed_capabilities=frozenset({"edit", "test"}),
                approved_test_profiles=frozenset({"unit"}),
            ),
            RuntimeContext(
                repository="example/repo",
                worktree_realpath=str(self.root / "worktree"),
                branch="codex/harness",
                starting_head="a" * 40,
                baseline_status_digest="b" * 64,
                baseline_tree_digest="c" * 64,
            ),
        )
        self.store.issue(self.lease)
        self.store.activate(self.lease.lease_id)
        self.context = copy.deepcopy(CONTEXT)
        self.transport = SyntheticTransport()

    def lease_observer(self):
        return self.store.get(self.lease.lease_id)

    def host_context_provider(self):
        return copy.deepcopy(self.context)

    def make_bridge(self, *, lease_observer=None, host_context_provider=None):
        return HarnessMergeBridge(
            copy.deepcopy(PARAMETERS),
            host_context_provider=host_context_provider or self.host_context_provider,
            lease_observer=lease_observer or self.lease_observer,
            authority_path=self.root / "authority.jsonl",
            attempts_path=self.root / "attempts.jsonl",
            transport=self.transport,
            executor_ref=REF,
        )

    def rows(self, name: str) -> list[dict[str, object]]:
        path = self.root / name
        return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []

    def approve(self, bridge: HarnessMergeBridge) -> None:
        self.assertEqual("approve", bridge.review(approval_response(bridge.request)))

    def test_active_local_lease_does_not_approve_or_execute(self) -> None:
        bridge = self.make_bridge()
        self.assertEqual("pending", bridge.state)
        self.assertEqual(bridge.request["action"]["operation"], "github.merge_pr")
        with self.assertRaises(SessionError):
            bridge.execute(PARAMETERS)
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)
        self.assertEqual([], self.rows("authority.jsonl"))

    def test_explicit_core_approval_allows_one_synthetic_put(self) -> None:
        bridge = self.make_bridge()
        self.approve(bridge)
        result = bridge.execute(PARAMETERS)
        self.assertEqual("SUCCESS", result["receipt"]["status"])
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual(
            ["authority_action_approval", "authority_action_consume"],
            [row["event_type"] for row in self.rows("authority.jsonl")],
        )

    def test_revoke_before_review_records_no_core_decision(self) -> None:
        bridge = self.make_bridge()
        self.store.revoke(self.lease.lease_id, "test revoke")
        with self.assertRaises(SessionError):
            bridge.review(approval_response(bridge.request))
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)
        self.assertEqual([], self.rows("authority.jsonl"))

    def test_revoke_after_review_stops_before_preflight(self) -> None:
        bridge = self.make_bridge()
        self.approve(bridge)
        self.store.revoke(self.lease.lease_id, "test revoke")
        with self.assertRaises(SessionError):
            bridge.execute(PARAMETERS)
        self.assertEqual([], self.transport.gets)
        self.assertEqual(1, len(self.rows("authority.jsonl")))

    def test_revoke_during_get_consumes_once_without_put_and_stays_unknown(self) -> None:
        bridge = self.make_bridge()
        self.approve(bridge)
        self.transport.on_get = lambda: self.store.revoke(self.lease.lease_id, "during get")
        result = bridge.execute(PARAMETERS)
        self.assertEqual("UNKNOWN", result["receipt"]["status"])
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual([], self.transport.puts)
        with self.assertRaises(SessionError):
            bridge.execute(PARAMETERS)

    def test_expired_lease_is_rejected_before_review(self) -> None:
        state = self.store.get(self.lease.lease_id)
        bridge_time = state.expires_at
        with patch("mothership_adapters.harness.time.time", return_value=bridge_time):
            with self.assertRaises(SessionError):
                self.make_bridge()

    def test_missing_or_changed_observed_digests_are_rejected(self) -> None:
        active = self.store.get(self.lease.lease_id)
        bad_observed = replace(active.expected_execution_state, status_digest="")
        with self.assertRaises(SessionError):
            self.make_bridge(lease_observer=lambda: replace(active, expected_execution_state=bad_observed))
        changed_observed = replace(active.expected_execution_state, tree_digest="d" * 64)
        observations = iter((active, active, replace(active, expected_execution_state=changed_observed)))
        bridge = self.make_bridge(lease_observer=lambda: next(observations))
        with self.assertRaises(SessionError):
            bridge.review(approval_response(bridge.request))

    def test_missing_or_changed_lease_identity_fields_are_rejected(self) -> None:
        active = self.store.get(self.lease.lease_id)
        with self.assertRaises(SessionError):
            self.make_bridge(lease_observer=lambda: replace(active, lease_id=""))
        mutations = {
            "task_id": "changed-task",
            "task_contract_sha256": "f" * 64,
            "policy_id": "changed-policy",
            "policy_sha256": "e" * 64,
            "repository": "changed/repo",
            "worktree_realpath": str(self.root / "other-worktree"),
            "branch": "changed-branch",
            "starting_head": "d" * 40,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                observations = iter((active, active, replace(active, **{field: value})))
                bridge = self.make_bridge(lease_observer=lambda: next(observations))
                with self.assertRaises(SessionError):
                    bridge.review(approval_response(bridge.request))

    def test_terminal_or_open_operation_lease_state_is_rejected(self) -> None:
        active = self.store.get(self.lease.lease_id)
        terminal = replace(active, lifecycle=LeaseLifecycle.REVOKED)
        with self.assertRaises(SessionError):
            self.make_bridge(lease_observer=lambda: terminal)
        open_operation = replace(active, open_operation_id="operation")
        with self.assertRaises(SessionError):
            self.make_bridge(lease_observer=lambda: open_operation)

    def test_each_core_context_drift_and_empty_scope_is_rejected(self) -> None:
        for field in ("host_id", "session_id", "actor_id", "runtime_generation", "scope"):
            with self.subTest(field=field):
                bridge = self.make_bridge()
                self.context[field] = [] if field == "scope" else "changed"
                with self.assertRaises(SessionError):
                    bridge.review(approval_response(bridge.request))
                self.context = copy.deepcopy(CONTEXT)
        bridge = self.make_bridge()
        self.context["scope"] = []
        with self.assertRaises(SessionError):
            bridge.review(approval_response(bridge.request))

    def test_suspended_owner_cannot_review_or_execute_and_resume_keeps_action(self) -> None:
        bridge = self.make_bridge()
        action_id = bridge.request["action"]["action_id"]
        bridge.suspend()
        self.assertEqual("suspended", bridge.state)
        with self.assertRaises(SessionError):
            bridge.review(approval_response(bridge.request))
        with self.assertRaises(SessionError):
            bridge.execute(PARAMETERS)
        with self.assertRaises(SessionError):
            bridge.suspend()
        bridge.resume()
        self.assertEqual("pending", bridge.state)
        self.assertEqual(action_id, bridge.request["action"]["action_id"])
        self.approve(bridge)
        self.assertEqual("SUCCESS", bridge.execute(PARAMETERS)["receipt"]["status"])

    def test_suspend_rejects_after_review_admission_before_session_claim(self) -> None:
        bridge = self.make_bridge()
        response = approval_response(bridge.request)
        admitted = threading.Event()
        release = threading.Event()
        review_results: list[object] = []
        original_review = bridge._session.review

        def paused_review(value: object) -> object:
            admitted.set()
            release.wait(2)
            return original_review(value)

        def run_review() -> None:
            try:
                review_results.append(bridge.review(response))
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                review_results.append(exc)

        with patch.object(bridge._session, "review", side_effect=paused_review):
            thread = threading.Thread(target=run_review)
            thread.start()
            self.assertTrue(admitted.wait(2))
            try:
                with self.assertRaises(HarnessBridgeError):
                    bridge.suspend()
            finally:
                release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(["approve"], review_results)
        self.assertEqual("approved", bridge.state)

    def test_suspend_rejects_after_execute_admission_before_session_claim(self) -> None:
        bridge = self.make_bridge()
        self.approve(bridge)
        admitted = threading.Event()
        release = threading.Event()
        execute_results: list[object] = []
        original_execute = bridge._session.execute

        def paused_execute(value: object) -> object:
            admitted.set()
            release.wait(2)
            return original_execute(value)

        def run_execute() -> None:
            try:
                execute_results.append(bridge.execute(PARAMETERS))
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                execute_results.append(exc)

        with patch.object(bridge._session, "execute", side_effect=paused_execute):
            thread = threading.Thread(target=run_execute)
            thread.start()
            self.assertTrue(admitted.wait(2))
            try:
                with self.assertRaises(HarnessBridgeError):
                    bridge.suspend()
            finally:
                release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(1, len(execute_results))
        self.assertEqual("SUCCESS", execute_results[0]["receipt"]["status"])
        self.assertEqual("finished", bridge.state)

    def test_admission_gate_rejects_reentrant_and_concurrent_review(self) -> None:
        bridge = self.make_bridge()
        response = approval_response(bridge.request)
        original_review = bridge._session.review
        nested_errors: list[Exception] = []

        def reentrant_review(value: object) -> object:
            try:
                bridge.review(response)
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                nested_errors.append(exc)
            return original_review(value)

        with patch.object(bridge._session, "review", side_effect=reentrant_review):
            self.assertEqual("approve", bridge.review(response))
        self.assertEqual(1, len(nested_errors))
        self.assertIsInstance(nested_errors[0], HarnessBridgeError)

        bridge = self.make_bridge()
        response = approval_response(bridge.request)
        admitted = threading.Event()
        release = threading.Event()
        first_results: list[object] = []
        second_results: list[object] = []
        second_done = threading.Event()
        original_review = bridge._session.review
        call_count = 0

        def paused_review(value: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                admitted.set()
                release.wait(2)
            return original_review(value)

        def run_first() -> None:
            try:
                first_results.append(bridge.review(response))
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                first_results.append(exc)

        def run_second() -> None:
            try:
                second_results.append(bridge.review(response))
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                second_results.append(exc)
            finally:
                second_done.set()

        with patch.object(bridge._session, "review", side_effect=paused_review):
            first_thread = threading.Thread(target=run_first)
            first_thread.start()
            self.assertTrue(admitted.wait(2))
            second_thread = threading.Thread(target=run_second)
            second_thread.start()
            self.assertTrue(second_done.wait(2))
            release.set()
            first_thread.join(2)
            second_thread.join(2)
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(["approve"], first_results)
        self.assertEqual(1, len(second_results))
        self.assertIsInstance(second_results[0], HarnessBridgeError)

    def test_cancel_and_suspended_state_race_completes_without_deadlock(self) -> None:
        bridge = self.make_bridge()
        state_entered = threading.Event()
        release_state = threading.Event()
        original_state = type(bridge._session).state

        def blocked_state(owner: object) -> str:
            state_entered.set()
            release_state.wait(2)
            return original_state.fget(owner)

        suspend_results: list[object] = []
        cancel_results: list[object] = []

        def run_suspend() -> None:
            try:
                bridge.suspend()
                suspend_results.append("suspended")
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                suspend_results.append(exc)

        def run_cancel() -> None:
            try:
                bridge.cancel()
                cancel_results.append("canceled")
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                cancel_results.append(exc)

        with patch.object(type(bridge._session), "state", property(blocked_state)):
            suspend_thread = threading.Thread(target=run_suspend)
            suspend_thread.start()
            self.assertTrue(state_entered.wait(2))
            cancel_thread = threading.Thread(target=run_cancel)
            cancel_thread.start()
            release_state.set()
            suspend_thread.join(2)
            cancel_thread.join(2)
        self.assertFalse(suspend_thread.is_alive())
        self.assertFalse(cancel_thread.is_alive())
        self.assertEqual(["canceled"], cancel_results)
        self.assertEqual(1, len(suspend_results))
        self.assertEqual("canceled", bridge.state)

    def test_resume_rechecks_lease_and_context_without_refreezing(self) -> None:
        bridge = self.make_bridge()
        action_id = bridge.request["action"]["action_id"]
        bridge.suspend()
        self.context["actor_id"] = "changed"
        with self.assertRaises(SessionError):
            bridge.resume()
        self.assertEqual("suspended", bridge.state)
        self.context = copy.deepcopy(CONTEXT)
        self.store.revoke(self.lease.lease_id, "while suspended")
        with self.assertRaises(SessionError):
            bridge.resume()
        self.assertEqual("suspended", bridge.state)
        self.assertEqual(action_id, bridge.request["action"]["action_id"])

    def test_resume_observer_can_use_real_lease_state_resume(self) -> None:
        bridge = self.make_bridge(
            lease_observer=lambda: self.store.resume(self.lease.lease_id),
        )
        bridge.suspend()
        bridge.resume()
        self.assertEqual("pending", bridge.state)

    def test_unknown_result_cannot_be_reconsumed(self) -> None:
        bridge = self.make_bridge()
        self.approve(bridge)
        self.transport.mutation = TimeoutError("private transport detail")
        result = bridge.execute(PARAMETERS)
        self.assertEqual("UNKNOWN", result["receipt"]["status"])
        with self.assertRaises(SessionError):
            bridge.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.puts))

    def test_missing_finish_is_not_promoted_to_success_or_retried(self) -> None:
        bridge = self.make_bridge()
        self.approve(bridge)
        with patch(
            "mothership_github.executor.record_attempt_finished",
            side_effect=OSError("private finish failure"),
        ):
            with self.assertRaises(SessionError):
                bridge.execute(PARAMETERS)
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual(1, len(self.rows("attempts.jsonl")))
        with self.assertRaises(SessionError):
            bridge.execute(PARAMETERS)


if __name__ == "__main__":
    unittest.main()
