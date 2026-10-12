"""Optional LangGraph host adapter for one retained merge session."""

from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any, TYPE_CHECKING, TypedDict

from mothership.contracts import canonical_json_bytes

from .session import MergeReviewSession

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph.state import CompiledStateGraph


try:  # Optional route; the Core/companion environment intentionally omits it.
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, Interrupt, interrupt

    _LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the base environment
    InMemorySaver = Any  # type: ignore[assignment,misc]
    StateGraph = None  # type: ignore[assignment]
    START = END = None  # type: ignore[assignment]
    Command = Interrupt = interrupt = None  # type: ignore[assignment]
    _LANGGRAPH_AVAILABLE = False


_SCHEMA_VERSION = "mothership-langgraph-review.v0"


class AdapterError(ValueError):
    """Finite, sanitized host-adapter failure."""


class _GraphState(TypedDict, total=False):
    owner_id: str
    review_request: dict[str, Any]
    result: dict[str, Any]


def _detach(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except Exception:
        raise AdapterError("invalid adapter data") from None


class LangGraphMergeAdapter:
    """Bind one LangGraph interrupt/checkpoint to one live Core session.

    The graph and ``InMemorySaver`` are constructed once, internally.  The
    checkpoint carries review data and owner identity only; it never carries
    or reconstructs the live Mothership action/session.
    """

    def __init__(self, session: MergeReviewSession):
        if not _LANGGRAPH_AVAILABLE:
            raise AdapterError("langgraph optional dependency unavailable")
        if not isinstance(session, MergeReviewSession):
            raise AdapterError("invalid retained session")
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._session = session
        self._owner_id = "owner-" + uuid.uuid4().hex
        self._phase = "new"
        self._thread_id: str | None = None
        self._interrupt_id: str | None = None
        self._request: dict[str, Any] | None = None
        self._parameters: dict[str, Any] | None = None
        self._session_result: dict[str, Any] | None = None
        self._checkpointer = InMemorySaver()
        builder = StateGraph(_GraphState)
        builder.add_node("review", self._review_node)
        builder.add_edge(START, "review")
        builder.add_edge("review", END)
        self._graph = builder.compile(checkpointer=self._checkpointer)

    def _check_pid(self) -> None:
        if os.getpid() != self._pid:
            raise AdapterError("adapter owner lost")

    def _review_node(self, state: _GraphState) -> dict[str, Any]:
        self._check_pid()
        with self._lock:
            owner_id = self._owner_id
            request = _detach(self._request)
            parameters = _detach(self._parameters)
            phase = self._phase
        if state.get("owner_id") != owner_id:
            raise AdapterError("graph owner differs")
        if canonical_json_bytes(state.get("review_request")) != canonical_json_bytes(request):
            raise AdapterError("graph request differs")
        if phase not in {"preparing", "resuming"}:
            raise AdapterError("graph phase unavailable")
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "owner_id": owner_id,
            "request": _detach(request),
        }
        answer = interrupt(payload)
        self._check_pid()
        with self._lock:
            if self._phase != "resuming":
                raise AdapterError("unexpected graph resume")
        response = _detach(answer)
        decision = self._session.review(response)
        if decision == "approve":
            result = _detach(self._session.execute(parameters))
            with self._lock:
                self._session_result = result
            return {"result": result}
        if decision != "reject":
            raise AdapterError("invalid session decision")
        return {
            "result": {
                "request": _detach(request),
                "response": response,
                "decision": "reject",
                "receipt": None,
                "verification": None,
            }
        }

    def prepare(self, thread_id: str) -> dict[str, Any]:
        """Start the one internal graph and return its first native interrupt."""

        self._check_pid()
        if type(thread_id) is not str or not thread_id:
            raise AdapterError("invalid thread id")
        with self._lock:
            if self._phase != "new":
                raise AdapterError("adapter phase unavailable")
            self._thread_id = thread_id
            self._phase = "preparing"
        try:
            request = _detach(self._session.request)
            parameters = _detach(request["action"]["execution_parameters"])
            if type(parameters) is not dict:
                raise ValueError()
            with self._lock:
                self._request = request
                self._parameters = parameters
            config = {"configurable": {"thread_id": thread_id}}
            output = self._graph.invoke(
                {"owner_id": self._owner_id, "review_request": _detach(request)},
                config,
            )
            interruptions = list(output.get("__interrupt__", ()))
            if len(interruptions) != 1:
                raise AdapterError("missing graph interrupt")
            native_interrupt = interruptions[0]
            if not isinstance(native_interrupt, Interrupt):
                raise AdapterError("invalid graph interrupt")
            if type(native_interrupt.id) is not str or not native_interrupt.id:
                raise AdapterError("invalid graph interrupt id")
            if canonical_json_bytes(native_interrupt.value.get("request")) != canonical_json_bytes(request):
                raise AdapterError("graph interrupt request differs")
            with self._lock:
                self._interrupt_id = native_interrupt.id
                self._phase = "prepared"
                return {
                    "schema_version": _SCHEMA_VERSION,
                    "owner_id": self._owner_id,
                    "thread_id": thread_id,
                    "interrupt_id": native_interrupt.id,
                    "interrupt": {
                        "id": native_interrupt.id,
                        "value": _detach(native_interrupt.value),
                    },
                    "review_request": _detach(request),
                }
        except AdapterError:
            with self._lock:
                self._phase = "failed"
            raise
        except Exception:
            with self._lock:
                self._phase = "failed"
            raise AdapterError("graph preparation failed") from None

    def resume(self, response: Any, *, thread_id: str, interrupt_id: str) -> dict[str, Any]:
        """Resume the retained graph only with the original thread/interrupt IDs."""

        self._check_pid()
        with self._lock:
            if self._phase != "prepared":
                raise AdapterError("adapter phase unavailable")
            if thread_id != self._thread_id or interrupt_id != self._interrupt_id:
                raise AdapterError("graph identity differs")
            request = _detach(self._request)
            self._phase = "resuming"
        try:
            retained_response = _detach(response)
            config = {"configurable": {"thread_id": thread_id}}
            output = self._graph.invoke(
                Command(resume=retained_response),
                config,
            )
            if "__interrupt__" in output:
                raise AdapterError("graph remained interrupted")
            result = _detach(output.get("result"))
            if type(result) is not dict:
                raise AdapterError("missing graph result")
            result.setdefault("review_request", _detach(request))
            result.setdefault("thread_id", thread_id)
            result.setdefault("interrupt_id", interrupt_id)
            with self._lock:
                self._phase = "finished"
            return result
        except AdapterError:
            with self._lock:
                if self._phase not in {"finished", "failed"}:
                    self._phase = "failed"
            raise
        except Exception:
            with self._lock:
                self._phase = "failed"
            raise AdapterError("graph resume failed") from None


__all__ = ["AdapterError", "LangGraphMergeAdapter"]
