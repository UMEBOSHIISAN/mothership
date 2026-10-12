"""Optional OpenAI Agents SDK host adapter for one retained merge session.

The SDK owns the pause/resume mechanics.  The Mothership session remains the
only owner of the live action, review binding, decision event and companion
execution.  This module intentionally imports the optional SDK lazily so the
base adapter package remains usable without ``openai-agents`` installed.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, TYPE_CHECKING

from mothership.contracts import canonical_json_bytes

from .session import MergeReviewSession

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from agents import Agent, RunState
    from agents.items import ToolApprovalItem


try:  # Optional route; the Core/companion environment intentionally omits it.
    from agents import Agent, RunConfig, RunHooks, Runner, function_tool
    from agents.tool import FunctionTool
    from agents.tool_context import ToolContext

    _AGENTS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the base environment
    Agent = Any  # type: ignore[assignment,misc]
    FunctionTool = Any  # type: ignore[assignment,misc]
    RunConfig = Any  # type: ignore[assignment,misc]
    RunHooks = object  # type: ignore[assignment,misc]
    Runner = None  # type: ignore[assignment]
    ToolContext = Any  # type: ignore[assignment,misc]
    function_tool = None  # type: ignore[assignment]
    _AGENTS_AVAILABLE = False


TOOL_NAME = "mothership_github_merge_pr"
_SCHEMA_VERSION = "mothership-agents-review.v0"
_TOOL_LOOKUP_KEY = ("bare", TOOL_NAME)
_MISSING = object()
_TOOL_BINDING_FIELDS = (
    "name",
    "qualified_name",
    "description",
    "params_json_schema",
    "strict_json_schema",
    "is_enabled",
    "tool_input_guardrails",
    "tool_output_guardrails",
    "needs_approval",
    "on_invoke_tool",
    "custom_data_extractor",
    "timeout_seconds",
    "timeout_behavior",
    "timeout_error_function",
    "defer_loading",
    "allowed_callers",
    "output_json_schema",
    "tool_namespace",
    "tool_lookup_key",
)
_TOOL_IDENTITY_FIELDS = frozenset(
    {
        "params_json_schema",
        "tool_input_guardrails",
        "tool_output_guardrails",
        "custom_data_extractor",
        "on_invoke_tool",
        "timeout_error_function",
        "allowed_callers",
        "output_json_schema",
    }
)


class AdapterError(ValueError):
    """Finite, sanitized host-adapter failure."""


class _SDKBindingHooks(RunHooks):
    """Capture the SDK-created callback context through its public run-hook API."""

    def __init__(self, adapter: "AgentsMergeAdapter") -> None:
        self._adapter = adapter

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        self._adapter._capture_tool_context(context, agent, tool)


def _detach(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except Exception:
        raise AdapterError("invalid adapter data") from None


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if type(raw) is not str:
        raise AdapterError("invalid tool arguments")

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite number")

    try:
        value = json.loads(raw, parse_constant=reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError):
        raise AdapterError("invalid tool arguments") from None
    if type(value) is not dict:
        raise AdapterError("invalid tool arguments")
    return _detach(value)


def _tool_field_signature(field: str, value: Any) -> tuple[Any, ...]:
    """Return a stable value/identity signature for one public FunctionTool field."""

    if value is _MISSING:
        return ("missing",)
    if field in _TOOL_IDENTITY_FIELDS or callable(value):
        try:
            payload = canonical_json_bytes(value)
        except Exception:
            payload = None
        return (
            "identity",
            id(value),
            type(value).__module__,
            type(value).__qualname__,
            payload,
        )
    try:
        payload = canonical_json_bytes(value)
    except Exception:
        return ("identity", id(value), type(value).__module__, type(value).__qualname__)
    return ("value", type(value).__module__, type(value).__qualname__, payload)


def _tool_binding_snapshot(tool: Any) -> dict[str, tuple[Any, ...]]:
    return {
        field: _tool_field_signature(field, getattr(tool, field, _MISSING))
        for field in _TOOL_BINDING_FIELDS
    }


class AgentsMergeAdapter:
    """Bind one Agents SDK approval interruption to one live Core session.

    ``prepare`` accepts a caller-owned agent and input, but clones the agent
    with exactly this adapter's typed tool.  ``resume`` accepts only the
    portable Core response; SDK state, agent replacement and serialized state
    are deliberately not part of the public API.
    """

    def __init__(self, session: MergeReviewSession):
        if not _AGENTS_AVAILABLE:
            raise AdapterError("openai-agents optional dependency unavailable")
        if not isinstance(session, MergeReviewSession):
            raise AdapterError("invalid retained session")
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._session = session
        self._phase = "new"
        self._agent: Any = None
        self._state: Any = None
        self._approval: Any = None
        self._request: dict[str, Any] | None = None
        self._parameters: dict[str, Any] | None = None
        self._call_id: str | None = None
        self._raw_arguments: str | None = None
        self._review_response: dict[str, Any] | None = None
        self._session_result: dict[str, Any] | None = None
        self._sdk_context = object()
        self._native_context: Any = None
        self._sdk_hooks = _SDKBindingHooks(self)
        self._tool = self._build_tool()
        self._tool_binding = _tool_binding_snapshot(self._tool)

    @property
    def tool(self) -> Any:
        """The single fixed typed merge tool supplied to the caller's agent."""

        return self._tool

    def _check_pid(self) -> None:
        if os.getpid() != self._pid:
            raise AdapterError("adapter owner lost")

    def _tool_binding_matches(self) -> bool:
        return _tool_binding_snapshot(self._tool) == self._tool_binding

    def _assert_tool_binding(self) -> None:
        if not self._tool_binding_matches():
            raise AdapterError("adapter tool binding changed")

    def _capture_tool_context(self, context: Any, agent: Any, tool: Any) -> None:
        with self._lock:
            if (
                self._phase == "armed"
                and agent is self._agent
                and tool is self._tool
                and self._native_context is None
            ):
                self._assert_tool_binding()
                self._native_context = context

    def _build_tool(self) -> Any:
        async def invoke(
            context: ToolContext[Any],
            repository: str,
            pull_request: int,
            expected_head_sha: str,
            expected_base: str,
            merge_method: str,
        ) -> str:
            parameters = {
                "repository": repository,
                "pull_request": pull_request,
                "expected_head_sha": expected_head_sha,
                "expected_base": expected_base,
                "merge_method": merge_method,
            }
            return await self._invoke_tool(context, parameters)

        assert function_tool is not None  # guarded by __init__
        return function_tool(
            invoke,
            name_override=TOOL_NAME,
            description_override=(
                "Merge exactly the retained GitHub pull request after the portable review "
                "response has been accepted."
            ),
            use_docstring_info=False,
            strict_mode=True,
            needs_approval=True,
            failure_error_function=None,
        )

    def _retained_parameters(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            request = _detach(self._session.request)
            action = request["action"]
            parameters = _detach(action["execution_parameters"])
            if type(parameters) is not dict:
                raise ValueError()
        except Exception:
            raise AdapterError("session request unavailable") from None
        return request, parameters

    async def prepare(self, agent: Any, input: Any) -> dict[str, Any]:
        """Run the supplied agent until exactly one matching approval pause."""

        self._check_pid()
        with self._lock:
            if self._phase != "new":
                raise AdapterError("adapter phase unavailable")
            self._phase = "preparing"
        if not _AGENTS_AVAILABLE or not isinstance(agent, Agent):
            with self._lock:
                self._phase = "failed"
            raise AdapterError("invalid supplied agent")
        if getattr(agent, "hooks", None) is not None:
            with self._lock:
                self._phase = "failed"
            raise AdapterError("caller agent hooks unsupported")

        try:
            self._assert_tool_binding()
            request, parameters = self._retained_parameters()
            input_value = _detach(input)
            existing_tools = list(agent.tools)
            if any(getattr(tool, "qualified_name", getattr(tool, "name", None)) == TOOL_NAME
                   for tool in existing_tools):
                raise AdapterError("duplicate adapter tool")
            bound_agent = agent.clone(tools=[*existing_tools, self._tool], hooks=None)
            if getattr(bound_agent, "hooks", _MISSING) is not None:
                raise AdapterError("bound agent hooks unsupported")
            self._assert_tool_binding()
            run_result = await Runner.run(
                bound_agent,
                input_value,
                context=self._sdk_context,
                hooks=self._sdk_hooks,
                run_config=RunConfig(tracing_disabled=True),
            )
            interruptions = list(getattr(run_result, "interruptions", ()))
            if len(interruptions) != 1:
                raise AdapterError("unexpected approval interruptions")
            approval = interruptions[0]
            if getattr(approval, "name", None) != TOOL_NAME:
                raise AdapterError("unexpected approval tool")
            call_id = getattr(approval, "call_id", None)
            raw_arguments = getattr(approval, "arguments", None)
            if type(call_id) is not str or not call_id:
                raise AdapterError("invalid approval call id")
            if type(raw_arguments) is not str:
                raise AdapterError("invalid approval arguments")
            raw_item = getattr(approval, "raw_item", None)
            raw_item_name = (
                raw_item.get("name")
                if isinstance(raw_item, dict)
                else getattr(raw_item, "name", None)
            )
            raw_item_namespace = (
                raw_item.get("namespace")
                if isinstance(raw_item, dict)
                else getattr(raw_item, "namespace", None)
            )
            if (
                approval.qualified_name != self._tool.qualified_name
                or getattr(approval, "tool_namespace", None) is not None
                or getattr(approval, "tool_lookup_key", None) != _TOOL_LOOKUP_KEY
                or raw_item_name != TOOL_NAME
                or raw_item_namespace is not None
                or getattr(approval, "agent", None) is not bound_agent
            ):
                raise AdapterError("approval tool identity differs")
            parsed = _parse_json_object(raw_arguments)
            if canonical_json_bytes(parsed) != canonical_json_bytes(parameters):
                raise AdapterError("approval arguments differ")
            state = run_result.to_state()
        except AdapterError:
            with self._lock:
                self._phase = "failed"
            raise
        except Exception:
            with self._lock:
                self._phase = "failed"
            raise AdapterError("agent preparation failed") from None

        with self._lock:
            self._agent = bound_agent
            self._state = state
            self._approval = approval
            self._request = request
            self._parameters = parameters
            self._call_id = call_id
            self._raw_arguments = raw_arguments
            self._phase = "prepared"
            return {
                "schema_version": _SCHEMA_VERSION,
                "review_request": _detach(request),
                "tool_name": TOOL_NAME,
                "call_id": call_id,
                "raw_arguments": raw_arguments,
            }

    async def _invoke_tool(self, context: Any, parameters: dict[str, Any]) -> str:
        self._check_pid()
        try:
            self._assert_tool_binding()
            tool_name = getattr(context, "tool_name", None)
            call_id = getattr(context, "tool_call_id", None)
            raw_arguments = getattr(context, "tool_arguments", None)
            tool_call = getattr(context, "tool_call", None)
            approval = self._approval
            retained_raw_item = getattr(approval, "raw_item", None)
            if (
                tool_name != TOOL_NAME
                or call_id != self._call_id
                or tool_call is None
                or tool_call != retained_raw_item
                or getattr(context, "tool_namespace", None) is not None
                or getattr(context, "agent", None) is not self._agent
                or context is not self._native_context
                or getattr(context, "context", _MISSING) is not self._sdk_context
            ):
                raise AdapterError("tool identity differs")
            get_approval_status = getattr(context, "get_approval_status", None)
            if (
                approval is None
                or not callable(get_approval_status)
                or get_approval_status(
                    TOOL_NAME,
                    self._call_id,
                    tool_namespace=None,
                    existing_pending=approval,
                    tool_lookup_key=getattr(approval, "tool_lookup_key", None),
                )
                is not True
            ):
                raise AdapterError("tool approval context differs")
            if raw_arguments != self._raw_arguments:
                raise AdapterError("tool arguments differ")
            parsed = _parse_json_object(raw_arguments)
            if canonical_json_bytes(parsed) != canonical_json_bytes(parameters):
                raise AdapterError("tool arguments differ")
            with self._lock:
                if self._phase != "armed":
                    raise AdapterError("tool is not armed")
                retained = _detach(self._parameters)
                if canonical_json_bytes(parsed) != canonical_json_bytes(retained):
                    raise AdapterError("retained parameters differ")
                self._phase = "executing"
            result = self._session.execute(retained)
            detached = _detach(result)
            with self._lock:
                self._session_result = detached
                self._phase = "finished"
            return json.dumps(detached, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except AdapterError:
            with self._lock:
                if self._phase not in {"finished", "failed"}:
                    self._phase = "failed"
            raise
        except Exception:
            with self._lock:
                self._phase = "failed"
            raise AdapterError("tool execution failed") from None

    async def resume(self, response: Any) -> dict[str, Any]:
        """Validate the Core response, approve/reject the retained state, and resume once."""

        self._check_pid()
        with self._lock:
            if self._phase != "prepared":
                raise AdapterError("adapter phase unavailable")
            try:
                self._assert_tool_binding()
            except AdapterError:
                self._phase = "failed"
                raise
            state = self._state
            approval = self._approval
            agent = self._agent
            request = _detach(self._request)
            self._phase = "resuming"
        try:
            retained_response = _detach(response)
            decision = self._session.review(retained_response)
            with self._lock:
                self._review_response = retained_response
            self._assert_tool_binding()
            if decision == "approve":
                state.approve(approval, always_approve=False)
                with self._lock:
                    self._phase = "armed"
            elif decision == "reject":
                state.reject(approval, always_reject=False)
            else:
                raise AdapterError("invalid session decision")
            self._assert_tool_binding()
            resumed_result = await Runner.run(
                agent,
                state,
                hooks=self._sdk_hooks,
                run_config=RunConfig(tracing_disabled=True),
            )
            if list(getattr(resumed_result, "interruptions", ())):
                raise AdapterError("unexpected resumed interruptions")
            if decision == "approve":
                with self._lock:
                    result = _detach(self._session_result)
                    if type(result) is not dict:
                        raise AdapterError("missing session result")
                return result
            with self._lock:
                self._phase = "finished"
            return {
                "request": request,
                "response": retained_response,
                "decision": "reject",
                "receipt": None,
                "verification": None,
            }
        except AdapterError:
            with self._lock:
                if self._phase not in {"finished", "failed"}:
                    self._phase = "failed"
            raise
        except Exception:
            with self._lock:
                self._phase = "failed"
            raise AdapterError("agent resume failed") from None


__all__ = ["AdapterError", "AgentsMergeAdapter", "TOOL_NAME"]
