"""Offline public LangGraph qualification for the retained session adapter."""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

try:
    import langgraph  # noqa: F401
    _LANGGRAPH_TEST_AVAILABLE = True
except ImportError:  # The base Core/companion environment omits this optional route.
    _LANGGRAPH_TEST_AVAILABLE = False

from mothership_adapters.langgraph_adapter import LangGraphMergeAdapter, AdapterError
from mothership_adapters.session import MergeReviewSession


PARAMETERS = {
    "repository": "example/repo",
    "pull_request": 7,
    "expected_head_sha": "a" * 40,
    "expected_base": "main",
    "merge_method": "merge",
}
CONTEXT = {
    "host_id": "test",
    "session_id": "session",
    "actor_id": "actor",
    "runtime_generation": "generation",
    "scope": ["github.merge_pr"],
}
REF = {"ref_id": "executor:synthetic", "sha256": "c" * 64}


class SyntheticTransport:
    def __init__(self) -> None:
        self.gets: list[tuple[str, int]] = []
        self.puts: list[dict[str, object]] = []

    def get_pull_request(self, repository: str, pull_request: int) -> dict[str, object]:
        self.gets.append((repository, pull_request))
        return {
            "http_status": 200,
            "state": "open",
            "merged": False,
            "head_sha": PARAMETERS["expected_head_sha"],
            "base_ref": PARAMETERS["expected_base"],
        }

    def merge_pull_request(self, **parameters: object) -> dict[str, object]:
        self.puts.append(parameters)
        return {"http_status": 200, "merged": True, "merge_commit_sha": "b" * 40}


class LangGraphFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        root.chmod(0o700)
        self.transport = SyntheticTransport()
        self.context = copy.deepcopy(CONTEXT)
        self.session = MergeReviewSession(
            copy.deepcopy(PARAMETERS),
            context_provider=lambda: copy.deepcopy(self.context),
            authority_path=root / "authority.jsonl",
            attempts_path=root / "attempts.jsonl",
            transport=self.transport,
            executor_ref=REF,
        )

    def response(self, decision: str = "approve") -> dict[str, object]:
        request = self.session.request
        return {
            "schema_version": "authority-action-review-response.v0",
            "decision": decision,
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "action_id": request["action"]["action_id"],
            "action_sha256": request["action_sha256"],
        }


@unittest.skipUnless(_LANGGRAPH_TEST_AVAILABLE, "LangGraph optional environment is not provisioned")
class LangGraphAdapterTests(LangGraphFixture):
    def test_prepare_interrupts_without_effect_and_resume_executes_once(self) -> None:
        adapter = LangGraphMergeAdapter(self.session)
        prepared = adapter.prepare("thread-1")
        self.assertEqual(self.session.request, prepared["review_request"])
        self.assertEqual("thread-1", prepared["thread_id"])
        self.assertIsInstance(prepared["interrupt_id"], str)
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)

        result = adapter.resume(
            self.response(), thread_id="thread-1", interrupt_id=prepared["interrupt_id"]
        )
        self.assertEqual(1, len(self.transport.gets))
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual(self.session.request, result["request"])
        self.assertEqual("approve", result["response"]["decision"])
        self.assertEqual("SUCCESS", result["receipt"]["status"])
        self.assertIsNone(result["verification"])
        with self.assertRaises(AdapterError):
            adapter.resume(
                self.response(), thread_id="thread-1", interrupt_id=prepared["interrupt_id"]
            )
        self.assertEqual(1, len(self.transport.puts))

    def test_reject_changed_thread_and_interrupt_fail_before_graph_execution(self) -> None:
        adapter = LangGraphMergeAdapter(self.session)
        prepared = adapter.prepare("thread-1")
        with self.assertRaises(AdapterError):
            adapter.resume(
                self.response(), thread_id="thread-2", interrupt_id=prepared["interrupt_id"]
            )
        with self.assertRaises(AdapterError):
            adapter.resume(
                self.response(), thread_id="thread-1", interrupt_id="wrong-interrupt"
            )
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)

    def test_reject_has_no_effect_and_ownerless_adapter_cannot_resume(self) -> None:
        adapter = LangGraphMergeAdapter(self.session)
        prepared = adapter.prepare("thread-1")
        result = adapter.resume(
            self.response("reject"),
            thread_id="thread-1",
            interrupt_id=prepared["interrupt_id"],
        )
        self.assertEqual("reject", result["decision"])
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)

        ownerless = LangGraphMergeAdapter(self.session)
        with self.assertRaises(AdapterError):
            ownerless.resume(
                self.response(),
                thread_id="thread-1",
                interrupt_id=prepared["interrupt_id"],
            )

    def test_changed_context_is_rejected_after_interrupt_before_effect(self) -> None:
        adapter = LangGraphMergeAdapter(self.session)
        prepared = adapter.prepare("thread-1")
        self.context["runtime_generation"] = "changed"
        with self.assertRaises(AdapterError):
            adapter.resume(
                self.response(),
                thread_id="thread-1",
                interrupt_id=prepared["interrupt_id"],
            )
        self.assertEqual([], self.transport.gets)
        self.assertEqual([], self.transport.puts)

    def test_checkpoint_state_contains_review_data_only(self) -> None:
        adapter = LangGraphMergeAdapter(self.session)
        prepared = adapter.prepare("thread-1")
        snapshot = adapter._graph.get_state(
            {"configurable": {"thread_id": "thread-1"}}
        )
        values = dict(snapshot.values)
        self.assertEqual(prepared["owner_id"], values["owner_id"])
        self.assertEqual(prepared["review_request"], values["review_request"])
        self.assertNotIn("session", values)
        self.assertNotIn("action", values)
        self.assertEqual([], self.transport.puts)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
