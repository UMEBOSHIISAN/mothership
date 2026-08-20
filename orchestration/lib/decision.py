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

from mothership.protocols import ProtocolError, validate_protocol

from .canonical import canonical_json_sha256
from .contracts import validate_contract
from .errors import ContractError


class DecisionBindingError(ContractError):
    """Card and Approval do not match or one fails contract validation."""


class DecisionCardProductionError(ContractError):
    """Required source metadata or explicit Card proposal data is invalid."""


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
