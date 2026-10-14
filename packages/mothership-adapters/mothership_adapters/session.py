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


_NOT_ATTEMPTED = "not_attempted BY THIS CALL"
_UNKNOWN = "unknown"
_DIAGNOSTIC_KEYS = frozenset({
    "code", "phase", "authority_use", "external_effect", "next_check", "retry_allowed"
})
_PHASE_DIAGNOSTICS = {
    "review_validation": ("review_validation_failed", "review_request"),
    "decision_record": ("decision_record_failed", "authority_records"),
    "execution_validation": ("execution_validation_failed", "review_request_and_existing_records"),
    "preflight_transport": ("preflight_transport_failed", "review_request_and_existing_records"),
    "preflight_returned": ("preflight_returned_failed", "review_request_and_existing_records"),
    "companion_execution": ("companion_execution_failed", "authority_and_attempt_records"),
    "mutation_guard": ("mutation_guard_failed", "authority_and_attempt_records"),
    "mutation_transport": ("mutation_transport_failed", "authority_and_attempt_records"),
    "mutation_returned": ("mutation_returned_failed", "authority_and_attempt_records"),
    "receipt_build": ("receipt_build_failed", "existing_evidence_bundle"),
    "result_export": ("result_export_failed", "existing_evidence_bundle"),
}
_KNOWN_PHASES = frozenset(_PHASE_DIAGNOSTICS) | {"unknown"}
_KNOWN_CODES = frozenset(code for code, _ in _PHASE_DIAGNOSTICS.values()) | {"unknown"}
_KNOWN_NEXT_CHECKS = frozenset(next_check for _, next_check in _PHASE_DIAGNOSTICS.values())


def _unknown_diagnostic():
    return {
        "code": _UNKNOWN,
        "phase": _UNKNOWN,
        "authority_use": _UNKNOWN,
        "external_effect": _UNKNOWN,
        "next_check": "existing_evidence_bundle",
        "retry_allowed": False,
    }


def _sanitize_diagnostic(value):
    if type(value) is not dict or set(value) != _DIAGNOSTIC_KEYS:
        return _unknown_diagnostic()
    if (
        type(value["code"]) is not str
        or value["code"] not in _KNOWN_CODES
        or type(value["phase"]) is not str
        or value["phase"] not in _KNOWN_PHASES
        or type(value["authority_use"]) is not str
        or value["authority_use"] not in {_NOT_ATTEMPTED, _UNKNOWN}
        or type(value["external_effect"]) is not str
        or value["external_effect"] not in {_NOT_ATTEMPTED, _UNKNOWN}
        or type(value["next_check"]) is not str
        or value["next_check"] not in _KNOWN_NEXT_CHECKS
        or value["retry_allowed"] is not False
    ):
        return _unknown_diagnostic()
    return {key: value[key] for key in (
        "code", "phase", "authority_use", "external_effect", "next_check", "retry_allowed"
    )}


class _DiagnosticTracker:
    """Per-invocation control-flow observation with no durable state."""

    def __init__(self, phase):
        self._phase = phase if phase in _KNOWN_PHASES else _UNKNOWN
        self._entered_companion = False

    def set(self, phase):
        self._phase = phase if phase in _KNOWN_PHASES else _UNKNOWN

    def enter_companion(self):
        self._entered_companion = True
        self.set("companion_execution")

    def diagnostic(self):
        if self._phase not in _PHASE_DIAGNOSTICS:
            return _unknown_diagnostic()
        code, next_check = _PHASE_DIAGNOSTICS[self._phase]
        if self._entered_companion:
            authority_use = external_effect = _UNKNOWN
            if self._phase not in {"receipt_build", "result_export"}:
                next_check = "authority_and_attempt_records"
        else:
            authority_use = external_effect = _NOT_ATTEMPTED
        return _sanitize_diagnostic({
            "code": code,
            "phase": self._phase,
            "authority_use": authority_use,
            "external_effect": external_effect,
            "next_check": next_check,
            "retry_allowed": False,
        })


class SessionError(ValueError):
    """Finite, sanitized adapter error; never permission to retry an action."""

    def __init__(self, *args, _diagnostic=None):
        super().__init__(*args)
        self._diagnostic = _sanitize_diagnostic(_diagnostic)

    @property
    def diagnostic(self):
        return dict(self._diagnostic)


def _detach(value):
    return json.loads(canonical_json_bytes(value))


class _GuardedTransport:
    def __init__(self, owner, tracker=None):
        self.owner = owner
        self.tracker = tracker

    def get_pull_request(self, repository, pull_request):
        owner = self.owner
        owner._guard()
        if canonical_json_bytes([repository, pull_request]) != canonical_json_bytes(
            [owner._parameters["repository"], owner._parameters["pull_request"]]
        ):
            raise SessionError("transport parameters differ")
        if self.tracker is not None:
            self.tracker.set("preflight_transport")
        result = owner._transport.get_pull_request(repository, pull_request)
        if self.tracker is not None:
            self.tracker.set("preflight_returned")
        return result

    def merge_pull_request(self, **parameters):
        owner = self.owner
        # Companion has consumed by this point. A failure here is caught by
        # companion and recorded as one uncertain attempt, with no actual PUT.
        if self.tracker is not None:
            self.tracker.set("mutation_guard")
        owner._guard()
        expected = {key: owner._parameters[key] for key in (
            "repository", "pull_request", "expected_head_sha", "merge_method"
        )}
        if canonical_json_bytes(parameters) != canonical_json_bytes(expected):
            raise SessionError("transport parameters differ")
        if self.tracker is not None:
            self.tracker.set("mutation_transport")
        result = owner._transport.merge_pull_request(**parameters)
        if self.tracker is not None:
            self.tracker.set("mutation_returned")
        return result


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
        tracker = _DiagnosticTracker("review_validation")
        try:
            retained = _detach(response)
            checked = validate_review_response(self._action, self._request, retained,
                                               current_host_context=_detach(self._provider()))
            with self._lock:
                if self._canceled:
                    raise SessionError("session canceled")
            tracker.set("decision_record")
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
            raise SessionError("session failed", _diagnostic=tracker.diagnostic()) from None

    def execute(self, parameters) -> dict:
        self._claim("approved", "executing")
        tracker = _DiagnosticTracker("execution_validation")
        try:
            if canonical_json_bytes(parameters) != canonical_json_bytes(self._parameters):
                raise SessionError("execution parameters differ")
            self._guard()
            tracker.enter_companion()
            result = execute_action_merge_pr(self._authority_path, self._attempts_path,
                                             self._action, self._decision["event_id"],
                                             _GuardedTransport(self, tracker))
            tracker.set("receipt_build")
            receipt = build_external_action_receipt(
                result["attempt_started"], result["attempt_finished"],
                expected_action_id=self._request["action"]["action_id"],
                expected_action_sha256=self._request["action_sha256"],
                expected_consume_event_id=result["consume_event"]["event_id"],
                executor_ref=self._executor_ref)
            tracker.set("result_export")
            with self._lock:
                self._state = "finished"
            return _detach({**result, "request": self._request, "response": self._response,
                            "decision": self._decision, "receipt": receipt, "verification": None})
        except Exception:
            self._fail()
            raise SessionError("session failed", _diagnostic=tracker.diagnostic()) from None

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
