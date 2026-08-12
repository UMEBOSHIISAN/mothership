"""Pure deterministic evaluation for validated Flight bundles."""

from __future__ import annotations

from dataclasses import dataclass

from .flight_contracts import REQUIRED_STAGES
from .flight_io import FlightBundle


PRECEDENCE = {"COMPLETE": 0, "INCOMPLETE": 1, "DRIFTED": 2, "INVALID": 3}


@dataclass(frozen=True, order=True)
class Finding:
    rule_id: str
    event_id: str | None
    detail: str


@dataclass(frozen=True)
class FlightEvaluation:
    run_id: str
    verdict: str
    required_stages: tuple[str, ...]
    present_stages: tuple[str, ...]
    findings: tuple[Finding, ...]


def _finding_verdict(rule_id: str) -> str:
    if ".INVALID." in rule_id:
        return "INVALID"
    if ".DRIFT." in rule_id:
        return "DRIFTED"
    if ".INCOMPLETE." in rule_id:
        return "INCOMPLETE"
    raise ValueError("unknown Flight finding rule")


def _event_id(event: dict[str, object]) -> str:
    return event["event_id"]  # type: ignore[return-value]


def _stage_events(events: tuple[dict[str, object], ...], stage: str) -> tuple[dict[str, object], ...]:
    return tuple(event for event in events if event["stage"] == stage)


def _subjects_match(left: dict[str, object], right: dict[str, object]) -> bool:
    return left["subject"]["sha256"] == right["subject"]["sha256"]  # type: ignore[index]


def evaluate_flight(bundle: FlightBundle) -> FlightEvaluation:
    """Evaluate only the supplied validated bundle, without side effects."""

    index = bundle.index
    events = bundle.events
    run_id = index["run_id"]  # type: ignore[assignment]
    required_stages = tuple(index["required_stages"])  # type: ignore[arg-type]
    present_stages = tuple(stage for stage in REQUIRED_STAGES if any(event["stage"] == stage for event in events))
    findings: list[Finding] = []

    def add(rule_id: str, event_id: str | None, detail: str) -> None:
        findings.append(Finding(rule_id, event_id, detail))

    event_ids = tuple(_event_id(event) for event in events)
    index_event_ids = tuple(index["event_ids"])  # type: ignore[arg-type]
    if index_event_ids != event_ids:
        add("FLIGHT.INVALID.IDENTITY", None, "index event identifiers do not match transport order")
    if len(set(event_ids)) != len(event_ids):
        add("FLIGHT.INVALID.IDENTITY", None, "event identifiers are not unique")
    for event in events:
        if event["run_id"] != run_id:
            add("FLIGHT.INVALID.IDENTITY", _event_id(event), "event run identifier does not match index")

    positions = {event_id: position for position, event_id in enumerate(event_ids)}
    event_by_id = {event_id: event for event_id, event in zip(event_ids, events)}
    for position, event in enumerate(events):
        event_id = _event_id(event)
        predecessors = event["predecessor_event_ids"]  # type: ignore[assignment]
        if event["stage"] != "intent" and not predecessors:
            add("FLIGHT.INVALID.GRAPH", event_id, "non-intent event has no predecessor")
        for predecessor_id in predecessors:
            predecessor_position = positions.get(predecessor_id)
            if predecessor_position is None or predecessor_position >= position:
                add("FLIGHT.INVALID.GRAPH", event_id, "predecessor is missing or not earlier")
                continue
            predecessor = event_by_id[predecessor_id]
            if event["occurred_at"] < predecessor["occurred_at"]:
                add("FLIGHT.INVALID.GRAPH", event_id, "event timestamp precedes predecessor")
    for stage in required_stages:
        if not any(event["stage"] == stage for event in events):
            add("FLIGHT.INCOMPLETE.STAGE", None, "required stage is absent")

    scopes = _stage_events(events, "scope")
    approvals = _stage_events(events, "approval")
    executions = _stage_events(events, "execution")
    if not approvals:
        add("FLIGHT.INCOMPLETE.APPROVAL", None, "approval is absent")
    else:
        for approval in approvals:
            if approval["outcome_status"] != "approved":
                add("FLIGHT.INCOMPLETE.APPROVAL", _event_id(approval), "approval outcome is not approved")
            if approval["authority_effect"] is not True and executions:
                add("FLIGHT.DRIFT.AUTHORITY", _event_id(approval), "execution lacks authority-effect approval")
        if scopes and executions:
            scope_digests = {event["scope_sha256"] for event in scopes}
            approval_digests = {event["scope_sha256"] for event in approvals}
            execution_digests = {event["scope_sha256"] for event in executions}
            if None in scope_digests or not (scope_digests == approval_digests == execution_digests):
                add("FLIGHT.DRIFT.SCOPE", None, "scope digests differ across scope approval and execution")
            scope_actions = {event["action_class"] for event in scopes}
            approval_actions = {event["action_class"] for event in approvals}
            execution_actions = {event["action_class"] for event in executions}
            if (
                "none" in scope_actions
                or not (scope_actions == approval_actions == execution_actions)
            ):
                add("FLIGHT.DRIFT.ACTION_CLASS", None, "action classes differ across scope approval and execution")
            if (
                max(event["occurred_at"] for event in scopes) > min(event["occurred_at"] for event in approvals)
                or max(event["occurred_at"] for event in approvals) > min(event["occurred_at"] for event in executions)
            ):
                add("FLIGHT.DRIFT.AUTHORITY", None, "approval does not occur between scope and execution")

    results = _stage_events(events, "result")
    verifications = _stage_events(events, "verification")
    persistences = _stage_events(events, "persistence")
    for execution in executions:
        if execution["execution_effect"] is not True:
            add("FLIGHT.INCOMPLETE.EVIDENCE", _event_id(execution), "execution has no execution effect")
    failed_executions = tuple(event for event in executions if event["outcome_status"] == "failed")
    successful_results = tuple(event for event in results if event["outcome_status"] == "succeeded")
    if failed_executions and successful_results:
        add("FLIGHT.DRIFT.FALSE_SUCCESS", _event_id(successful_results[0]), "result claims success after failed execution")
    if not successful_results:
        event_id = _event_id(executions[0]) if executions else None
        add("FLIGHT.INCOMPLETE.EVIDENCE", event_id, "successful execution lacks result evidence")
    if not verifications or not any(event["outcome_status"] == "verified" for event in verifications):
        add("FLIGHT.INCOMPLETE.VERIFICATION", _event_id(results[0]) if results else None, "result lacks verification")
    if not persistences or not any(event["outcome_status"] == "persisted" for event in persistences):
        add("FLIGHT.INCOMPLETE.PERSISTENCE", _event_id(verifications[0]) if verifications else None, "verification lacks persistence proof")
    if successful_results and verifications:
        for verification in verifications:
            if verification["outcome_status"] == "verified" and not any(
                _subjects_match(result, verification) for result in successful_results
            ):
                add("FLIGHT.DRIFT.RESULT", _event_id(verification), "result and verification digests disagree")
    verified = tuple(event for event in verifications if event["outcome_status"] == "verified")
    persisted = tuple(event for event in persistences if event["outcome_status"] == "persisted")
    if verified and persisted:
        for persistence in persisted:
            if not any(_subjects_match(verification, persistence) for verification in verified):
                add("FLIGHT.DRIFT.PERSISTENCE", _event_id(persistence), "verification and persistence digests disagree")

    evidence_verdict = max(("COMPLETE", *(_finding_verdict(item.rule_id) for item in findings)), key=PRECEDENCE.__getitem__)
    declared_verdict = index["declared_verdict"]
    if declared_verdict is not None and declared_verdict != evidence_verdict:
        add("FLIGHT.DRIFT.DECLARED_VERDICT", None, "declared verdict differs from evidence")
    ordered_findings = tuple(sorted(findings, key=lambda item: (item.rule_id, item.event_id or "", item.detail)))
    verdict = max(("COMPLETE", *(_finding_verdict(item.rule_id) for item in ordered_findings)), key=PRECEDENCE.__getitem__)
    return FlightEvaluation(run_id, verdict, required_stages, present_stages, ordered_findings)


def evaluation_document(evaluation: FlightEvaluation) -> dict[str, object]:
    """Return the closed, detached verdict projection for one evaluation."""

    return {
        "schema_version": "mothership.flight-verdict.v1",
        "run_id": evaluation.run_id,
        "verdict": evaluation.verdict,
        "required_stages": list(evaluation.required_stages),
        "present_stages": list(evaluation.present_stages),
        "findings": [
            {"rule_id": item.rule_id, "event_id": item.event_id, "detail": item.detail}
            for item in evaluation.findings
        ],
        "authority_effect": False,
        "execution_effect": False,
    }


__all__ = ("Finding", "FlightEvaluation", "evaluate_flight", "evaluation_document")
