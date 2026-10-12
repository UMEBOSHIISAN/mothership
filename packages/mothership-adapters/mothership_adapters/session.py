"""One process-owned review and one companion execution opportunity.

Context checks are best-effort observations immediately before transport calls,
not atomic revocation fences. The host owns callbacks, credentials and transport.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
import uuid

from mothership.action_authority import freeze_action, record_action_decision
from mothership.action_review import build_review_request, validate_review_response
from mothership.contracts import canonical_json_bytes
from mothership_github.executor import execute_action_merge_pr
from mothership_github.external_action import build_external_action_receipt


class SessionError(ValueError):
    """Finite, sanitized adapter error; never permission to retry an action."""


def _detach(value):
    return json.loads(canonical_json_bytes(value))


class _GuardedTransport:
    def __init__(self, owner):
        self.owner = owner

    def get_pull_request(self, repository, pull_request):
        owner = self.owner
        owner._guard()
        if canonical_json_bytes([repository, pull_request]) != canonical_json_bytes(
            [owner._parameters["repository"], owner._parameters["pull_request"]]
        ):
            raise SessionError("transport parameters differ")
        return owner._transport.get_pull_request(repository, pull_request)

    def merge_pull_request(self, **parameters):
        owner = self.owner
        # Companion has consumed by this point. A failure here is caught by
        # companion and recorded as one uncertain attempt, with no actual PUT.
        owner._guard()
        expected = {key: owner._parameters[key] for key in (
            "repository", "pull_request", "expected_head_sha", "merge_method"
        )}
        if canonical_json_bytes(parameters) != canonical_json_bytes(expected):
            raise SessionError("transport parameters differ")
        return owner._transport.merge_pull_request(**parameters)


class MergeReviewSession:
    """Retain one issued action; detached data cannot recreate this owner.

    review() records one caller-attested Core decision; execute() delegates
    consume and attempts exclusively to the companion. All terminal phases are
    spent. Errors and duplicate calls never create a replacement action.
    """

    def __init__(self, parameters, *, context_provider, authority_path,
                 attempts_path, transport, executor_ref):
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._state = "pending"
        self._canceled = False
        self._response = None
        self._decision = None
        self._provider = context_provider
        self._transport = transport
        self._authority_path = authority_path
        self._attempts_path = attempts_path
        try:
            if not callable(context_provider) or not all(callable(getattr(transport, key, None))
                    for key in ("get_pull_request", "merge_pull_request")):
                raise ValueError()
            if not isinstance(authority_path, Path) or not isinstance(attempts_path, Path):
                raise ValueError()
            if authority_path.resolve() == attempts_path.resolve():
                raise ValueError()
            ref = _detach(executor_ref)
            if (type(ref) is not dict or set(ref) != {"ref_id", "sha256"}
                    or type(ref["ref_id"]) is not str or not 1 <= len(ref["ref_id"]) <= 256
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", ref["ref_id"])
                    or type(ref["sha256"]) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])):
                raise ValueError()
            self._executor_ref = ref
            self._parameters = _detach(parameters)
            context = _detach(context_provider())
            self._action = freeze_action("act-" + uuid.uuid4().hex, "github.merge_pr", self._parameters)
            self._request = build_review_request(self._action, request_id="review-" + uuid.uuid4().hex,
                                                 host_context=context)
        except Exception:
            self._state = "failed"
            raise SessionError("session construction failed") from None

    def _check_pid(self):
        # Before the mutex: an inherited locked mutex must not hang a child.
        if os.getpid() != self._pid:
            raise SessionError("session owner lost")

    @property
    def request(self):
        self._check_pid()
        return _detach(self._request)

    @property
    def state(self):
        self._check_pid()
        with self._lock:
            return self._state

    def _claim(self, expected, phase):
        self._check_pid()
        with self._lock:
            if self._state != expected or self._canceled:
                raise SessionError("session phase unavailable")
            self._state = phase

    def _guard(self):
        self._check_pid()
        with self._lock:
            if self._canceled:
                raise SessionError("session canceled")
        if self._response is None:
            raise SessionError("session has no review")
        validate_review_response(self._action, self._request, self._response,
                                 current_host_context=_detach(self._provider()))

    def _fail(self):
        with self._lock:
            # A claimed operation may have written a decision, consumed
            # authority or sent PUT. Cancellation must not hide its error.
            self._state = "failed"

    def review(self, response) -> str:
        self._claim("pending", "reviewing")
        try:
            retained = _detach(response)
            checked = validate_review_response(self._action, self._request, retained,
                                               current_host_context=_detach(self._provider()))
            with self._lock:
                if self._canceled:
                    raise SessionError("session canceled")
            decision = record_action_decision(self._authority_path, self._action,
                                              checked["decision"], checked["action_id"],
                                              checked["action_sha256"])
            with self._lock:
                self._response, self._decision = retained, decision
                self._state = ("canceled" if self._canceled else
                               "approved" if checked["decision"] == "approve" else "rejected")
            return checked["decision"]
        except Exception:
            self._fail()
            raise SessionError("session failed") from None

    def execute(self, parameters) -> dict:
        self._claim("approved", "executing")
        try:
            if canonical_json_bytes(parameters) != canonical_json_bytes(self._parameters):
                raise SessionError("execution parameters differ")
            self._guard()
            result = execute_action_merge_pr(self._authority_path, self._attempts_path,
                                             self._action, self._decision["event_id"],
                                             _GuardedTransport(self))
            receipt = build_external_action_receipt(
                result["attempt_started"], result["attempt_finished"],
                expected_action_id=self._request["action"]["action_id"],
                expected_action_sha256=self._request["action_sha256"],
                expected_consume_event_id=result["consume_event"]["event_id"],
                executor_ref=self._executor_ref)
            with self._lock:
                self._state = "finished"
            return _detach({**result, "request": self._request, "response": self._response,
                            "decision": self._decision, "receipt": receipt, "verification": None})
        except Exception:
            self._fail()
            raise SessionError("session failed") from None

    def cancel(self) -> None:
        self._check_pid()
        with self._lock:
            if self._state in {"finished", "rejected", "failed", "canceled"}:
                return
            self._canceled = True
            if self._state in {"pending", "approved"}:
                self._state = "canceled"

    def __copy__(self):
        raise TypeError("live sessions cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("live sessions cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("live sessions cannot be restored")


__all__ = ["MergeReviewSession", "SessionError"]
