"""Pure, fail-closed Decision Card / Decision Approval binding primitives.

Terminology freeze
──────────────────
decision
    The existing machine/frontdoor recommendation contract (frontdoor/contracts/decision.schema.json).
    Contains: recommended_alias, selected_alias, actual_alias, authority_effect: "none" (string).
    Output of the Agent Frontdoor's advisory routing pass.

decision-card
    A human-facing decision proposition (evidence/contracts/decision-card.v0.schema.json).
    Contains: question, recommendation, unknowns, consequence_if_approved.
    authority_effect: false (boolean). execution_effect: false (boolean).
    No authority. No execution. No status. No worker selection.

decision-approval
    A human judgment bound cryptographically to exactly one Decision Card
    (evidence/contracts/decision-approval.v0.schema.json).
    Binds via SHA-256 digest of the canonical JSON bytes of the Decision Card.
    Does NOT constitute execution authority.
    Separate from approval-event.schema.json (invocation/execution-side evidence).

approval-event
    The existing invocation/execution-side approval evidence
    (evidence/contracts/approval-event.schema.json).
    Binds: alias + registry_sha256 + task_sha256 + prompt_sha256 + scope_sha256.
    Governs the execution chain (attempt_started / attempt_finished).

consequence_if_approved
    A human-readable description field on Decision Card.
    Describes what next stage becomes *eligible* after a matching human approval.
    MUST NOT be consumed as: shell command, executor input, invocation request,
    approval evidence, or execution plan. It is presentation-only.
"""

from __future__ import annotations

import json

from mothership.protocols import ProtocolError, validate_protocol

from .canonical import canonical_json_sha256
from .contracts import validate_contract
from .errors import ContractError


class DecisionBindingError(ContractError):
    """Card and Approval do not match or one fails contract validation."""


class DecisionCardProductionError(ContractError):
    """Required source metadata or explicit Card proposal data is invalid."""


_BATCH_ENTRY_KEYS = frozenset(
    {
        "frontdoor_task",
        "governance_handoff",
        "question",
        "consequence_if_approved",
        "router_manifest",
    }
)
_BATCH_REQUIRED_KEYS = _BATCH_ENTRY_KEYS - {"router_manifest"}


def build_decision_card(
    frontdoor_task: object,
    governance_handoff: object,
    *,
    decision_id: object,
    question: object,
    consequence_if_approved: object,
    router_manifest: object | None = None,
) -> dict[str, object] | None:
    """Build one ephemeral Decision Card from validated companion metadata.

    The function validates each owner-owned input, preserves the existing
    values used by the Card contract, and accepts human-facing synthesis as
    explicit caller input. It never invokes a model, creates an Approval, or
    performs execution. None means the Frontdoor gate says no human decision
    is needed for a non-high-risk handoff.
    """
    try:
        frontdoor = validate_protocol("frontdoor-task", frontdoor_task)
        handoff = validate_protocol("governance-handoff", governance_handoff)
        router = (
            None
            if router_manifest is None
            else validate_protocol("router-manifest", router_manifest)
        )
    except ProtocolError as exc:
        raise DecisionCardProductionError(f"source protocol validation failed: {exc}") from exc

    if frontdoor["request_id"] != handoff["task_id"]:
        raise DecisionCardProductionError(
            "Frontdoor request_id and WGM handoff task_id do not match"
        )

    human_gate = frontdoor["human_gate"]
    risk = handoff["risk"]
    if human_gate == "NONE":
        if risk == "high":
            raise DecisionCardProductionError(
                "high-risk WGM handoff cannot bypass a human Frontdoor gate"
            )
        return None
    if human_gate not in {"CONFIRM", "BLOCKING"}:
        raise DecisionCardProductionError("Frontdoor human_gate is unsupported")

    if router is not None and router["task_id"] != handoff["task_id"]:
        raise DecisionCardProductionError(
            "Router manifest task_id does not match the WGM handoff"
        )

    reasons = [f"frontdoor.human_gate={human_gate}"]
    reasons.extend(f"frontdoor.risk_tag={tag}" for tag in frontdoor["risk_tags"])
    recommendation = None
    if router is not None:
        recommendation = router["recommended_alias"]
        reasons.append(f"router-manifest.status={router['status']}")
        reasons.extend(
            f"router-manifest.reason={reason}" for reason in router["reasons"]
        )

    card = {
        "schema_version": "decision-card.v0",
        "decision_id": decision_id,
        "task_id": handoff["task_id"],
        "question": question,
        "recommendation": recommendation,
        "reasons": reasons,
        "evidence_refs": list(handoff["evidence_references"]),
        "unknowns": list(frontdoor["unknowns"]),
        "risk": risk,
        "authority_required": "human",
        "consequence_if_approved": consequence_if_approved,
        "authority_effect": False,
        "execution_effect": False,
    }
    try:
        return validate_contract("decision-card", card)
    except ContractError as exc:
        raise DecisionCardProductionError(f"Decision Card proposal is invalid: {exc}") from exc


def _batch_input_id(entry: object, index: int) -> str:
    if type(entry) is dict:
        frontdoor = entry.get("frontdoor_task")
        if type(frontdoor) is dict:
            request_id = frontdoor.get("request_id")
            if type(request_id) is str and request_id:
                return request_id
    return f"batch-item-{index}"


def build_decision_batch(entries: object) -> dict[str, object]:
    """Aggregate Decision Discovery outcomes in memory for human inspection.

    The result deliberately contains separate Card, no-Card, and fail-closed
    collections. Input order is preserved within each collection. This
    function has no persistence, deduplication, priority, approval, or
    execution behavior.
    """
    if type(entries) is not list:
        raise DecisionCardProductionError("batch inputs must be a list")

    decision_cards: list[dict[str, object]] = []
    no_cards: list[dict[str, object]] = []
    fail_closed: list[dict[str, object]] = []

    for index, entry in enumerate(entries):
        input_id = _batch_input_id(entry, index)
        if (
            type(entry) is not dict
            or not _BATCH_REQUIRED_KEYS.issubset(entry)
            or set(entry) - _BATCH_ENTRY_KEYS
        ):
            fail_closed.append(
                {
                    "input_id": input_id,
                    "classification": "FAIL_CLOSED",
                    "reason": "batch_input_invalid",
                }
            )
            continue

        try:
            card = build_decision_card(
                entry["frontdoor_task"],
                entry["governance_handoff"],
                decision_id=entry["frontdoor_task"].get("request_id"),
                question=entry["question"],
                consequence_if_approved=entry["consequence_if_approved"],
                router_manifest=entry.get("router_manifest"),
            )
        except (AttributeError, DecisionCardProductionError) as exc:
            fail_closed.append(
                {
                    "input_id": input_id,
                    "classification": "FAIL_CLOSED",
                    "reason": str(exc),
                }
            )
            continue

        if card is None:
            no_cards.append(
                {
                    "input_id": input_id,
                    "classification": "NO_CARD",
                    "reason": "human_decision_not_required",
                }
            )
            continue

        decision_cards.append(
            {
                "schema_version": card["schema_version"],
                "input_id": input_id,
                "decision_id": card["decision_id"],
                "task_id": card["task_id"],
                "question": card["question"],
                "recommendation": card["recommendation"],
                "recommendation_provenance": (
                    "router-manifest.recommended_alias"
                    if entry.get("router_manifest") is not None
                    else None
                ),
                "reasons": list(card["reasons"]),
                "evidence_refs": list(card["evidence_refs"]),
                "unknowns": list(card["unknowns"]),
                "risk": card["risk"],
                "authority_required": card["authority_required"],
                "consequence_if_approved": card["consequence_if_approved"],
                "authority_effect": card["authority_effect"],
                "execution_effect": card["execution_effect"],
            }
        )

    return {
        "decision_cards": decision_cards,
        "no_cards": no_cards,
        "fail_closed": fail_closed,
        "summary": {
            "input_count": len(entries),
            "decision_card_count": len(decision_cards),
            "no_card_count": len(no_cards),
            "fail_closed_count": len(fail_closed),
        },
    }


def format_decision_batch(batch: object) -> str:
    """Render one ephemeral batch result for direct human inspection."""
    if type(batch) is not dict or any(
        key not in batch for key in ("decision_cards", "no_cards", "fail_closed", "summary")
    ):
        raise DecisionCardProductionError("batch result shape is invalid")

    def render_value(value: object) -> str:
        if type(value) is bool:
            return "true" if value else "false"
        if type(value) in (list, dict):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    lines = ["EPHEMERAL DECISION BATCH"]
    cards = batch["decision_cards"]
    lines.append(f"DECISION_CARD ({len(cards)})")
    if not cards:
        lines.append("- none")
    for card in cards:
        lines.append(f"- input_id: {card['input_id']}")
        for field in (
            "decision_id",
            "task_id",
            "question",
            "recommendation",
            "recommendation_provenance",
            "reasons",
            "evidence_refs",
            "unknowns",
            "risk",
            "authority_required",
            "consequence_if_approved",
            "authority_effect",
            "execution_effect",
        ):
            lines.append(f"  {field}: {render_value(card[field])}")

    for title, key in (("NO_CARD", "no_cards"), ("FAIL_CLOSED", "fail_closed")):
        items = batch[key]
        lines.append(f"{title} ({len(items)})")
        if not items:
            lines.append("- none")
        for item in items:
            lines.append(f"- input_id: {item['input_id']}")
            lines.append(f"  classification: {item['classification']}")
            lines.append(f"  reason: {item['reason']}")

    summary = batch["summary"]
    lines.append(
        "SUMMARY: "
        f"inputs={summary['input_count']} "
        f"cards={summary['decision_card_count']} "
        f"no_card={summary['no_card_count']} "
        f"fail_closed={summary['fail_closed_count']}"
    )
    return "\n".join(lines)


def validate_decision_approval_binding(
    card: object,
    approval: object,
) -> tuple[dict[str, object], dict[str, object]]:
    """Validate that *approval* is the human judgment for exactly *card*.

    Steps
    -----
    1. Validate *card* against the ``decision-card`` schema.
    2. Validate *approval* against the ``decision-approval`` schema.
    3. Compute ``canonical_json_sha256(validated_card)``.
    4. Require exact equality with ``approval["decision_card_sha256"]``.
    5. If both objects carry ``decision_id``, require equality.

    Returns
    -------
    (validated_card, validated_approval)
        Both objects as returned by ``validate_contract``.

    Raises
    ------
    DecisionBindingError
        If either object fails its schema, the SHA-256 digests do not match,
        or the ``decision_id`` values disagree.

    Notes
    -----
    This function has no I/O, no side effects, and no network access.
    It does not grant authority or execution permission.
    A valid binding means only that the human reviewed *this exact* Card.
    """
    try:
        validated_card = validate_contract("decision-card", card)
    except ContractError as exc:
        raise DecisionBindingError(f"decision-card validation failed: {exc}") from exc

    try:
        validated_approval = validate_contract("decision-approval", approval)
    except ContractError as exc:
        raise DecisionBindingError(f"decision-approval validation failed: {exc}") from exc

    expected_digest = canonical_json_sha256(validated_card)
    actual_digest = validated_approval["decision_card_sha256"]
    if expected_digest != actual_digest:
        raise DecisionBindingError(
            "decision_card_sha256 mismatch: approval was not issued for this card"
        )

    # Both decision-card and decision-approval schemas have decision_id as required.
    # Always enforce exact equality — no conditional check needed.
    if validated_card["decision_id"] != validated_approval["decision_id"]:
        raise DecisionBindingError(
            f"decision_id mismatch: card={validated_card['decision_id']!r}"
            f" approval={validated_approval['decision_id']!r}"
        )

    return validated_card, validated_approval
