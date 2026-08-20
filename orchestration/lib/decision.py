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

from .canonical import canonical_json_sha256
from .contracts import validate_contract
from .errors import ContractError


class DecisionBindingError(ContractError):
    """Card and Approval do not match or one fails contract validation."""


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
