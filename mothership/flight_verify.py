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


def _event_ancestors(events: tuple[dict[str, object], ...]) -> dict[str, frozenset[str]]:
    ancestors: dict[str, frozenset[str]] = {}
    for event in events:
        predecessor_ids = event["predecessor_event_ids"]  # type: ignore[assignment]
        inherited: set[str] = set(predecessor_ids)
        for predecessor_id in predecessor_ids:
            inherited.update(ancestors.get(predecessor_id, ()))
        ancestors[_event_id(event)] = frozenset(inherited)
    return ancestors


def _is_ancestor(
    ancestor: dict[str, object],
    descendant: dict[str, object],
    ancestors: dict[str, frozenset[str]],
) -> bool:
    return _event_id(ancestor) in ancestors.get(_event_id(descendant), ())


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

    ancestors = _event_ancestors(events)
    intents = _stage_events(events, "intent")
    scopes = _stage_events(events, "scope")
    decisions = _stage_events(events, "decision")
    approvals = _stage_events(events, "approval")
    executions = _stage_events(events, "execution")
    if not approvals:
        add("FLIGHT.INCOMPLETE.APPROVAL", None, "approval is absent")
    else:
        for approval in approvals:
            if approval["outcome_status"] != "approved":
                add("FLIGHT.INCOMPLETE.APPROVAL", _event_id(approval), "approval outcome is not approved")
            elif approval["authority_effect"] is not True:
                add("FLIGHT.DRIFT.AUTHORITY", _event_id(approval), "approved record lacks authority effect")
        for execution in executions:
            authority_approvals = tuple(
                approval
                for approval in approvals
                if approval["outcome_status"] == "approved"
                and approval["authority_effect"] is True
                and _is_ancestor(approval, execution, ancestors)
            )
            authority_chains = tuple(
                (scope, approval)
                for approval in authority_approvals
                for decision in decisions
                if _is_ancestor(decision, approval, ancestors)
                for scope in scopes
                if _is_ancestor(scope, decision, ancestors)
                for intent in intents
                if _is_ancestor(intent, scope, ancestors)
                and scope["occurred_at"] < approval["occurred_at"] < execution["occurred_at"]
            )
            if not authority_chains:
                add("FLIGHT.DRIFT.AUTHORITY", _event_id(execution), "execution lacks a strictly ordered authority chain")
                continue
            chain_matches = tuple(
                (
                    scope["scope_sha256"] is not None
                    and scope["scope_sha256"] == approval["scope_sha256"] == execution["scope_sha256"],
                    scope["action_class"] != "none"
                    and scope["action_class"] == approval["action_class"] == execution["action_class"],
                )
                for scope, approval in authority_chains
            )
            if any(scope_matches and action_matches for scope_matches, action_matches in chain_matches):
                continue
            if not any(scope_matches for scope_matches, _action_matches in chain_matches):
                add("FLIGHT.DRIFT.SCOPE", _event_id(execution), "causal authority scope digest differs")
            if not any(action_matches for _scope_matches, action_matches in chain_matches):
                add("FLIGHT.DRIFT.ACTION_CLASS", _event_id(execution), "causal authority action class differs")
            if (
                any(scope_matches for scope_matches, _action_matches in chain_matches)
                and any(action_matches for _scope_matches, action_matches in chain_matches)
            ):
                add("FLIGHT.DRIFT.SCOPE", _event_id(execution), "scope and action match only across different authority chains")
                add("FLIGHT.DRIFT.ACTION_CLASS", _event_id(execution), "scope and action match only across different authority chains")

    results = _stage_events(events, "result")
    verifications = _stage_events(events, "verification")
    persistences = _stage_events(events, "persistence")
    for execution in executions:
        if execution["execution_effect"] is not True:
            add("FLIGHT.INCOMPLETE.EVIDENCE", _event_id(execution), "execution has no execution effect")
    successful_results = tuple(event for event in results if event["outcome_status"] == "succeeded")
    for execution in executions:
        if execution["execution_effect"] is True and not any(
            _is_ancestor(execution, result, ancestors)
            for result in successful_results
        ):
            add("FLIGHT.INCOMPLETE.EVIDENCE", _event_id(execution), "effectful execution lacks a successful result descendant")
    for result in successful_results:
        execution_ancestors = tuple(
            execution
            for execution in executions
            if _is_ancestor(execution, result, ancestors)
        )
        if not execution_ancestors:
            add("FLIGHT.INCOMPLETE.EVIDENCE", _event_id(result), "successful result lacks an execution ancestor")
        if any(execution["outcome_status"] == "failed" for execution in execution_ancestors):
            add("FLIGHT.DRIFT.FALSE_SUCCESS", _event_id(result), "result claims success after causal execution failed")
    verified = tuple(event for event in verifications if event["outcome_status"] == "verified")
    persisted = tuple(event for event in persistences if event["outcome_status"] == "persisted")
    for result in successful_results:
        verification_descendants = tuple(
            verification
            for verification in verified
            if _is_ancestor(result, verification, ancestors)
        )
        if any(_subjects_match(result, verification) for verification in verification_descendants):
            continue
        if verification_descendants:
            add("FLIGHT.DRIFT.RESULT", _event_id(result), "result and descendant verification digests disagree")
        else:
            add("FLIGHT.INCOMPLETE.VERIFICATION", _event_id(result), "successful result lacks a verified descendant")
    for verification in verified:
        result_ancestors = tuple(
            result
            for result in successful_results
            if _is_ancestor(result, verification, ancestors)
        )
        if not any(_subjects_match(result, verification) for result in result_ancestors):
            add("FLIGHT.DRIFT.RESULT", _event_id(verification), "verification lacks matching result ancestry")
        persistence_descendants = tuple(
            persistence
            for persistence in persisted
            if _is_ancestor(verification, persistence, ancestors)
        )
        if any(_subjects_match(verification, persistence) for persistence in persistence_descendants):
            continue
        if persistence_descendants:
            add("FLIGHT.DRIFT.PERSISTENCE", _event_id(verification), "verification and descendant persistence digests disagree")
        else:
            add("FLIGHT.INCOMPLETE.PERSISTENCE", _event_id(verification), "verified record lacks a persisted descendant")
    for persistence in persisted:
        verification_ancestors = tuple(
            verification
            for verification in verified
            if _is_ancestor(verification, persistence, ancestors)
        )
        if verified and not any(_subjects_match(verification, persistence) for verification in verification_ancestors):
            add("FLIGHT.DRIFT.PERSISTENCE", _event_id(persistence), "persistence lacks matching verification ancestry")

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
