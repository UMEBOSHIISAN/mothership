"""Supplemental bridge between a local Harness lease and one Core Session.

The local lease is an observation and lifecycle guard.  It never becomes
Core approval or external-action authority.  The host supplies Core context
through a separate callback, and the retained :class:`MergeReviewSession`
continues to own approval, consume, transport and receipt semantics.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable

from mothership.contracts import canonical_json_bytes

from .session import MergeReviewSession, SessionError


_MISSING = object()
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA1 = re.compile(r"[0-9a-f]{40}\Z")


class HarnessBridgeError(SessionError):
    """Finite bridge error that never contains callback or state details."""


def _canonical(value: object) -> bytes:
    try:
        return canonical_json_bytes(value)
    except Exception:
        raise HarnessBridgeError("bridge data is not canonical") from None


def _require_text(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise HarnessBridgeError("lease evidence is incomplete")
    return value


def _require_digest(value: object, length: int) -> str:
    value = _require_text(value)
    pattern = _SHA256 if length == 64 else _GIT_SHA1
    if pattern.fullmatch(value) is None:
        raise HarnessBridgeError("lease evidence digest is invalid")
    return value


def _require_time(value: object) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise HarnessBridgeError("lease evidence time is invalid")
    return value


def _observation(value: object, *, starting_head: str | None = None) -> dict[str, str]:
    if type(value).__name__ != "ObservedExecutionState":
        raise HarnessBridgeError("lease observation type is invalid")
    try:
        observed_start = _require_digest(getattr(value, "starting_head"), 40)
        status_digest = _require_digest(getattr(value, "status_digest"), 64)
        tree_digest = _require_digest(getattr(value, "tree_digest"), 64)
    except (AttributeError, TypeError):
        raise HarnessBridgeError("lease observation is incomplete") from None
    if starting_head is not None and observed_start != starting_head:
        raise HarnessBridgeError("lease observation head differs")
    return {
        "starting_head": observed_start,
        "status_digest": status_digest,
        "tree_digest": tree_digest,
    }


def _lease_snapshot(state: object) -> dict[str, object]:
    """Validate one actual Harness LeaseRuntimeState and detach its evidence."""

    if type(state).__name__ != "LeaseRuntimeState":
        raise HarnessBridgeError("lease state type is invalid")
    try:
        lifecycle = getattr(getattr(state, "lifecycle"), "value")
        lease_id = _require_digest(getattr(state, "lease_id"), 64)
        task_id = _require_text(getattr(state, "task_id"))
        task_contract_sha256 = _require_digest(getattr(state, "task_contract_sha256"), 64)
        policy_id = _require_text(getattr(state, "policy_id"))
        policy_sha256 = _require_digest(getattr(state, "policy_sha256"), 64)
        repository = _require_text(getattr(state, "repository"))
        worktree_realpath = _require_text(getattr(state, "worktree_realpath"))
        branch = _require_text(getattr(state, "branch"))
        starting_head = _require_digest(getattr(state, "starting_head"), 40)
        issued_at = _require_time(getattr(state, "issued_at"))
        expires_at = _require_time(getattr(state, "expires_at"))
        open_operation_id = getattr(state, "open_operation_id")
        open_operation_started_at = getattr(state, "open_operation_started_at")
        expected = _observation(
            getattr(state, "expected_execution_state"),
            starting_head=starting_head,
        )
    except (AttributeError, TypeError):
        raise HarnessBridgeError("lease state is incomplete") from None

    if lifecycle != "ACTIVE":
        raise HarnessBridgeError("lease is not active")
    if not os.path.isabs(worktree_realpath) or os.path.normpath(worktree_realpath) != worktree_realpath:
        raise HarnessBridgeError("lease worktree identity is invalid")
    now = time.time()
    if not math.isfinite(now) or issued_at > now or expires_at <= issued_at or now >= expires_at:
        raise HarnessBridgeError("lease is expired or has invalid bounds")
    if open_operation_id is not None or open_operation_started_at is not None:
        raise HarnessBridgeError("lease has an open operation")

    baseline = getattr(state, "baseline_anchor", _MISSING)
    baseline_snapshot = None if baseline is _MISSING or baseline is None else _observation(
        baseline,
        starting_head=starting_head,
    )
    delta = getattr(state, "delta_chain_digest", _MISSING)
    delta_snapshot = None if delta is _MISSING or delta is None else _require_digest(delta, 64)
    return {
        "lease_id": lease_id,
        "task_id": task_id,
        "task_contract_sha256": task_contract_sha256,
        "policy_id": policy_id,
        "policy_sha256": policy_sha256,
        "repository": repository,
        "worktree_realpath": worktree_realpath,
        "branch": branch,
        "starting_head": starting_head,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "expected_execution_state": expected,
        "baseline_anchor": baseline_snapshot,
        "delta_chain_digest": delta_snapshot,
    }


class HarnessMergeBridge:
    """Keep a local Harness owner and one retained Core merge Session together.

    The bridge has no approval path of its own.  ``request`` is detached
    preview data, ``review`` records the supplied Core decision through the
    retained Session, and ``execute`` delegates one-shot consume/transport
    behavior to that same Session.
    """

    def __init__(
        self,
        parameters: object,
        *,
        host_context_provider: Callable[[], object],
        lease_observer: Callable[[], object],
        authority_path: Path,
        attempts_path: Path,
        transport: object,
        executor_ref: object,
    ) -> None:
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._busy = False
        self._suspended = False
        self._cancel_generation = 0
        if not callable(host_context_provider) or not callable(lease_observer):
            raise HarnessBridgeError("bridge callbacks are invalid")
        self._host_context_provider = host_context_provider
        self._lease_observer = lease_observer
        try:
            self._lease_snapshot = self._observe_lease()
            self._session = MergeReviewSession(
                parameters,
                context_provider=self._context_provider,
                authority_path=authority_path,
                attempts_path=attempts_path,
                transport=transport,
                executor_ref=executor_ref,
            )
            self._construction_context = self._detached_context(
                self._session.request["host_context"]
            )
        except SessionError:
            raise
        except Exception:
            raise HarnessBridgeError("bridge construction failed") from None

    def _check_pid(self) -> None:
        if os.getpid() != self._pid:
            raise HarnessBridgeError("bridge owner lost")

    def _observe_lease(self) -> dict[str, object]:
        try:
            state = self._lease_observer()
            return _lease_snapshot(state)
        except HarnessBridgeError:
            raise
        except Exception:
            raise HarnessBridgeError("lease observation failed") from None

    def _assert_lease_current(self) -> None:
        current = self._observe_lease()
        if _canonical(current) != _canonical(self._lease_snapshot):
            raise HarnessBridgeError("lease evidence changed")

    @staticmethod
    def _detached_context(value: object) -> object:
        try:
            import json

            return json.loads(_canonical(value))
        except HarnessBridgeError:
            raise
        except Exception:
            raise HarnessBridgeError("host context is invalid") from None

    def _context_provider(self) -> object:
        self._check_pid()
        self._assert_lease_current()
        try:
            return self._detached_context(self._host_context_provider())
        except HarnessBridgeError:
            raise
        except Exception:
            raise HarnessBridgeError("host context observation failed") from None

    def _admit(self, operation: str) -> int:
        self._check_pid()
        with self._lock:
            if self._busy:
                raise HarnessBridgeError("bridge is busy")
            if operation == "resume":
                if not self._suspended:
                    raise HarnessBridgeError("bridge is not suspended")
            elif self._suspended:
                if operation == "suspend":
                    raise HarnessBridgeError("bridge is already suspended")
                raise HarnessBridgeError("bridge is suspended")
            self._busy = True
            return self._cancel_generation

    def _release_admission(self) -> None:
        with self._lock:
            self._busy = False

    @property
    def request(self) -> dict[str, object]:
        self._check_pid()
        return self._session.request

    @property
    def state(self) -> str:
        self._check_pid()
        with self._lock:
            if self._suspended:
                return "suspended"
        return self._session.state

    def review(self, response: object) -> str:
        self._admit("review")
        try:
            return self._session.review(response)
        finally:
            self._release_admission()

    def execute(self, parameters: object) -> dict[str, object]:
        self._admit("execute")
        try:
            return self._session.execute(parameters)
        finally:
            self._release_admission()

    def cancel(self) -> None:
        self._check_pid()
        with self._lock:
            self._cancel_generation += 1
        self._session.cancel()
        with self._lock:
            self._suspended = False

    def suspend(self) -> None:
        cancel_generation = self._admit("suspend")
        try:
            if self._session.state not in {"pending", "approved"}:
                raise HarnessBridgeError("bridge cannot be suspended")
            with self._lock:
                if self._cancel_generation != cancel_generation:
                    raise HarnessBridgeError("bridge cannot be suspended")
                self._suspended = True
        finally:
            self._release_admission()

    def resume(self) -> None:
        self._admit("resume")
        try:
            current_context = self._context_provider()
            if _canonical(current_context) != _canonical(self._construction_context):
                raise HarnessBridgeError("host context changed")
            with self._lock:
                if not self._suspended:
                    raise HarnessBridgeError("bridge is not suspended")
                self._suspended = False
        finally:
            self._release_admission()


__all__ = ["HarnessBridgeError", "HarnessMergeBridge"]
