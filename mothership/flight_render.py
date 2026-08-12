"""Pure, privacy-preserving projections and Markdown rendering for Flight records."""

from __future__ import annotations

import unicodedata

from .flight_io import FlightBundle
from .flight_verify import FlightEvaluation


def replay_document(bundle: FlightBundle, evaluation: FlightEvaluation) -> dict[str, object]:
    """Return a detached causal timeline projection without performing I/O."""

    timeline: list[dict[str, object]] = []
    for event in bundle.events:
        timeline.append(
            {
                "event_id": event["event_id"],
                "stage": event["stage"],
                "event_type": event["event_type"],
                "occurred_at": event["occurred_at"],
                "predecessor_event_ids": list(event["predecessor_event_ids"]),  # type: ignore[arg-type]
                "action_class": event["action_class"],
                "outcome_status": event["outcome_status"],
                "subject_sha256": event["subject"]["sha256"],  # type: ignore[index]
            }
        )
    return {
        "schema_version": "mothership.flight-replay.v1",
        "run_id": bundle.index["run_id"],
        "verdict": evaluation.verdict,
        "timeline": timeline,
        "authority_effect": False,
        "execution_effect": False,
    }


def _safe(value: object) -> str:
    text = "None" if value is None else str(value)
    escaped: list[str] = []
    for char in text:
        code = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == "|":
            escaped.append("\\|")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\n":
            escaped.append("\\n")
        elif unicodedata.category(char) == "Cc":
            escaped.append(f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}")
        else:
            escaped.append(char)
    return "".join(escaped)


def _prefix(value: object) -> str:
    return _safe(value)[:12] if value is not None else "None"


def render_markdown_report(bundle: FlightBundle, evaluation: FlightEvaluation) -> str:
    """Render supplied records as deterministic, non-authoritative Markdown."""

    approvals = tuple(event for event in bundle.events if event["stage"] == "approval")
    approval = approvals[0] if approvals else None
    approval_action = approval["action_class"] if approval is not None else None
    approval_scope = approval["scope_sha256"] if approval is not None else None
    required = len(evaluation.required_stages)
    present = len(evaluation.present_stages)
    lines = [
        "# Mothership Flight Report",
        "## Verdict",
        f"- Verdict: {_safe(evaluation.verdict)}",
        f"- Run ID: {_safe(evaluation.run_id)}",
        f"- Stages: required={required}, present={present} ({present}/{required} required stages present)",
        "## Authority",
        f"- Approval: {_safe(approval_action)} / {_prefix(approval_scope)}",
        "- Authority effect: False",
        "- Execution effect: False",
        "## Timeline",
        "| Event | Stage | Type | Occurred | Predecessors | Action | Outcome | Subject |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for event in bundle.events:
        predecessors = ", ".join(_safe(item) for item in event["predecessor_event_ids"])  # type: ignore[union-attr]
        lines.append(
            "| " + " | ".join(
                (
                    _safe(event["event_id"]),
                    _safe(event["stage"]),
                    _safe(event["event_type"]),
                    _safe(event["occurred_at"]),
                    predecessors,
                    _safe(event["action_class"]),
                    _safe(event["outcome_status"]),
                    _prefix(event["subject"]["sha256"]),  # type: ignore[index]
                )
            ) + " |"
        )
    lines.extend(("## Findings",))
    if not evaluation.findings:
        lines.append("- None.")
    else:
        for finding in evaluation.findings:
            lines.append(f"- {_safe(finding.rule_id)} ({_safe(finding.event_id)}): {_safe(finding.detail)}")
    lines.extend(
        (
            "## Evidence boundary",
            "This report verifies supplied records; it does not grant authority or prove unobserved real-world actions.",
        )
    )
    return "\n".join(lines) + "\n"


__all__ = ("replay_document", "render_markdown_report")
