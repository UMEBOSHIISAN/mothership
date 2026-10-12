"""Offline public OpenAI Agents SDK qualification for the retained session adapter."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

try:
    from agents import Agent, AgentHooks, Model, RunConfig, Runner, function_tool, tool_namespace
    from agents.items import ModelResponse
    from agents.tool_context import ToolContext
    from agents.usage import Usage
    from openai.types.responses import (
        ResponseFunctionToolCall,
        ResponseOutputMessage,
        ResponseOutputText,
    )
    _AGENTS_TEST_AVAILABLE = True
except ImportError:  # The base Core/companion environment omits this optional route.
    Agent = Model = RunConfig = Runner = object  # type: ignore[assignment,misc]
    ModelResponse = ToolContext = Usage = object  # type: ignore[assignment,misc]
    ResponseFunctionToolCall = ResponseOutputMessage = ResponseOutputText = object  # type: ignore[assignment,misc]
    AgentHooks = function_tool = tool_namespace = object  # type: ignore[assignment,misc]
    _AGENTS_TEST_AVAILABLE = False

from mothership_adapters.agents_sdk import AgentsMergeAdapter, AdapterError, TOOL_NAME
from mothership_adapters.session import MergeReviewSession, SessionError


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


class FixtureModel(Model):
    """A public SDK Model that only emits typed, local Responses items."""

    def __init__(self, *, arguments: str | None = None, call_id: str = "call-merge-1",
                 interruption_count: int = 1, tool_name: str | None = None,
                 tool_namespace: str | None = None) -> None:
        self.calls = 0
        self.arguments = arguments or json.dumps(PARAMETERS, separators=(",", ":"))
        self.call_id = call_id
        self.interruption_count = interruption_count
        self.tool_name = tool_name
        self.tool_namespace = tool_namespace

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, *, previous_response_id,
                           conversation_id, prompt):
        self.calls += 1
        if self.calls == 1:
            tool_calls = []
            for index in range(self.interruption_count):
                call_kwargs = {
                    "arguments": self.arguments,
                    "call_id": self.call_id if index == 0 else f"{self.call_id}-{index}",
                    "name": self.tool_name or tools[0].name,
                    "type": "function_call",
                }
                if self.tool_namespace is not None:
                    call_kwargs["namespace"] = self.tool_namespace
                tool_calls.append(ResponseFunctionToolCall(**call_kwargs))
            return ModelResponse(
                output=tool_calls,
                usage=Usage(),
                response_id="response-1",
            )
        return ModelResponse(
            output=[ResponseOutputMessage(
                id="message-2",
                content=[ResponseOutputText(
                    annotations=[], text="done", type="output_text"
                )],
                role="assistant",
                status="completed",
                type="message",
            )],
            usage=Usage(),
            response_id="response-2",
        )

    async def stream_response(self, *args, **kwargs):
        if False:
            yield None


class AgentsFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        root.chmod(0o700)
        self.transport = SyntheticTransport()
        self.context = copy.deepcopy(CONTEXT)
        self.authority_path = root / "authority.jsonl"
        self.attempts_path = root / "attempts.jsonl"
        self.session = MergeReviewSession(
            copy.deepcopy(PARAMETERS),
            context_provider=lambda: copy.deepcopy(self.context),
            authority_path=self.authority_path,
            attempts_path=self.attempts_path,
            transport=self.transport,
            executor_ref=REF,
        )

    def agent(self, model: Model | None = None) -> Agent:
        return Agent("fixture", model=model or FixtureModel())

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


@unittest.skipUnless(_AGENTS_TEST_AVAILABLE, "OpenAI Agents SDK optional environment is not provisioned")
class AgentsAdapterTests(AgentsFixture):
    def test_prepare_pauses_one_native_approval_and_resume_executes_once(self) -> None:
        async def run() -> None:
            adapter = AgentsMergeAdapter(self.session)
            prepared = await adapter.prepare(self.agent(), "merge this PR")
            self.assertEqual(self.session.request, prepared["review_request"])
            self.assertEqual("call-merge-1", prepared["call_id"])
            self.assertEqual(
                json.dumps(PARAMETERS, separators=(",", ":")), prepared["raw_arguments"]
            )
            self.assertEqual([], self.transport.gets)
            self.assertEqual([], self.transport.puts)

            result = await adapter.resume(self.response())
            self.assertEqual(1, len(self.transport.gets))
            self.assertEqual(1, len(self.transport.puts))
            self.assertEqual(self.session.request, result["request"])
            self.assertEqual("approve", result["response"]["decision"])
            self.assertEqual("approve", result["decision"]["decision"])
            self.assertEqual("SUCCESS", result["receipt"]["status"])
            self.assertIsNone(result["verification"])
            with self.assertRaises(AdapterError):
                await adapter.resume(self.response())

        asyncio.run(run())

    def test_reject_resumes_without_effect(self) -> None:
        async def run() -> None:
            adapter = AgentsMergeAdapter(self.session)
            await adapter.prepare(self.agent(), "merge this PR")
            result = await adapter.resume(self.response("reject"))
            self.assertEqual("reject", result["decision"])
            self.assertEqual([], self.transport.gets)
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())

    def test_direct_body_invocation_and_changed_arguments_fail_closed(self) -> None:
        async def run() -> None:
            adapter = AgentsMergeAdapter(self.session)
            prepared = await adapter.prepare(self.agent(), "merge this PR")
            with self.assertRaises(AdapterError):
                await adapter.tool.on_invoke_tool(
                    ToolContext(
                        None,
                        tool_name=prepared["tool_name"],
                        tool_call_id=prepared["call_id"],
                        tool_arguments=prepared["raw_arguments"],
                        run_config=RunConfig(tracing_disabled=True),
                    ),
                    prepared["raw_arguments"],
                )
            changed = dict(PARAMETERS, pull_request=8)
            model = FixtureModel(arguments=json.dumps(changed, separators=(",", ":")))
            other = AgentsMergeAdapter(self.session)
            with self.assertRaises(AdapterError):
                await other.prepare(self.agent(model), "merge this PR")
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())

    def test_wrong_call_id_and_raw_arguments_fail_closed(self) -> None:
        async def run() -> None:
            adapter = AgentsMergeAdapter(self.session)
            prepared = await adapter.prepare(self.agent(), "merge this PR")
            for call_id, raw_arguments in (
                ("wrong-call-id", prepared["raw_arguments"]),
                (prepared["call_id"], json.dumps(dict(PARAMETERS, pull_request=8))),
            ):
                with self.subTest(call_id=call_id):
                    with self.assertRaises(AdapterError):
                        await adapter.tool.on_invoke_tool(
                            ToolContext(
                                None,
                                tool_name=prepared["tool_name"],
                                tool_call_id=call_id,
                                tool_arguments=raw_arguments,
                                run_config=RunConfig(tracing_disabled=True),
                            ),
                            raw_arguments,
                        )
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())

    def test_multiple_or_foreign_interruptions_fail_closed(self) -> None:
        async def run() -> None:
            multiple = AgentsMergeAdapter(self.session)
            with self.assertRaises(AdapterError):
                await multiple.prepare(
                    self.agent(FixtureModel(interruption_count=2)), "merge this PR"
                )
            self.assertEqual([], self.transport.puts)

            foreign = AgentsMergeAdapter(self.session)
            with self.assertRaises(AdapterError):
                await foreign.prepare(
                    self.agent(FixtureModel(tool_name="foreign_tool")), "merge this PR"
                )
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())

    def test_same_basename_foreign_namespace_fails_closed(self) -> None:
        async def run() -> None:
            @function_tool(name_override="mothership_github_merge_pr", needs_approval=True)
            def foreign_merge_tool(
                repository: str,
                pull_request: int,
                expected_head_sha: str,
                expected_base: str,
                merge_method: str,
            ) -> str:
                return "foreign"

            namespaced_foreign_tool = tool_namespace(
                name="foreign",
                description="Foreign same-basename tool",
                tools=[foreign_merge_tool],
            )[0]
            agent = Agent(
                "fixture",
                model=FixtureModel(tool_namespace="foreign"),
                tools=[namespaced_foreign_tool],
            )
            adapter = AgentsMergeAdapter(self.session)
            with self.assertRaises(AdapterError):
                await adapter.prepare(agent, "merge this PR")
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())

    def test_caller_agent_hooks_are_rejected_before_runner_and_approval_record(self) -> None:
        class AttackHooks(AgentHooks):
            def __init__(self) -> None:
                self.starts = 0

            async def on_tool_start(self, context, agent, tool) -> None:
                self.starts += 1

        async def run() -> None:
            hooks = AttackHooks()
            adapter = AgentsMergeAdapter(self.session)
            with self.assertRaisesRegex(AdapterError, "caller agent hooks unsupported"):
                await adapter.prepare(
                    Agent("fixture", model=FixtureModel(), hooks=hooks),
                    "merge this PR",
                )
            self.assertEqual(0, hooks.starts)
            self.assertEqual([], self.transport.gets)
            self.assertEqual([], self.transport.puts)
            self.assertFalse(self.authority_path.exists())
            self.assertFalse(self.attempts_path.exists())

        asyncio.run(run())

    @staticmethod
    def _tool_mutations() -> tuple[tuple[str, object], ...]:
        async def replacement(_context, _raw_arguments):
            return "replacement"

        return (
            ("tool_input_guardrails", []),
            ("tool_output_guardrails", []),
            ("custom_data_extractor", lambda _context: None),
            ("needs_approval", False),
            ("is_enabled", False),
            ("on_invoke_tool", replacement),
            ("name", "foreign_tool"),
            ("description", "changed description"),
            ("params_json_schema", {"type": "object", "properties": {}}),
            ("strict_json_schema", False),
            ("defer_loading", True),
            ("tool_namespace", "foreign"),
            ("tool_lookup_key", ("namespaced", "foreign", TOOL_NAME)),
        )

    def test_fixed_tool_mutations_fail_before_prepare_runner(self) -> None:
        async def run() -> None:
            for field, value in self._tool_mutations():
                with self.subTest(field=field):
                    adapter = AgentsMergeAdapter(self.session)
                    setattr(adapter.tool, field, value)
                    with self.assertRaisesRegex(AdapterError, "adapter tool binding changed"):
                        await adapter.prepare(self.agent(), "merge this PR")
                    self.assertEqual([], self.transport.gets, field)
                    self.assertEqual([], self.transport.puts, field)
                    self.assertFalse(self.authority_path.exists(), field)
                    self.assertFalse(self.attempts_path.exists(), field)

        asyncio.run(run())

    def test_fixed_tool_mutations_fail_between_prepare_and_resume(self) -> None:
        async def attempt(field: str, value: object) -> None:
            fixture = AgentsFixture("run")
            fixture.setUp()
            try:
                adapter = AgentsMergeAdapter(fixture.session)
                await adapter.prepare(fixture.agent(), "merge this PR")
                setattr(adapter.tool, field, value)
                with self.assertRaisesRegex(AdapterError, "adapter tool binding changed"):
                    await adapter.resume(fixture.response())
                self.assertEqual("failed", adapter._phase, field)
                with self.assertRaisesRegex(AdapterError, "adapter phase unavailable"):
                    await adapter.resume(fixture.response())
                self.assertEqual([], fixture.transport.gets, field)
                self.assertEqual([], fixture.transport.puts, field)
                self.assertFalse(fixture.authority_path.exists(), field)
                self.assertFalse(fixture.attempts_path.exists(), field)
            finally:
                fixture.temp.cleanup()

        async def run() -> None:
            for field, value in self._tool_mutations():
                with self.subTest(field=field):
                    await attempt(field, value)

        asyncio.run(run())

    def test_cancelled_session_cannot_resume_native_approval(self) -> None:
        async def run() -> None:
            adapter = AgentsMergeAdapter(self.session)
            await adapter.prepare(self.agent(), "merge this PR")
            self.session.cancel()
            with self.assertRaises(AdapterError):
                await adapter.resume(self.response())
            self.assertEqual([], self.transport.gets)
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())

    def test_changed_review_context_is_rejected_before_native_approval(self) -> None:
        async def run() -> None:
            adapter = AgentsMergeAdapter(self.session)
            await adapter.prepare(self.agent(), "merge this PR")
            self.context["actor_id"] = "changed"
            with self.assertRaises(AdapterError):
                await adapter.resume(self.response())
            self.assertEqual([], self.transport.gets)
            self.assertEqual([], self.transport.puts)

        asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
