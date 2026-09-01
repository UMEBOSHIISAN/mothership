"""Pure validation for non-executing external-action boundary records."""

from __future__ import annotations

from .canonical import canonical_json_sha256
from .contracts import validate_contract
from .errors import ContractError


def validate_consequence_proposal(value: object) -> dict[str, object]:
    """Validate a proposal that has no authority, execution, or delegation effect."""

    return validate_contract("consequence-proposal.v0", value)


def validate_external_action_receipt(value: object) -> dict[str, object]:
    """Validate one executor-local report without treating it as verification."""

    return validate_contract("external-action-receipt.v0", value)


def validate_external_action_verification(value: object) -> dict[str, object]:
    """Validate one independent read-only external-state observation."""

    verification = validate_contract("external-action-verification.v0", value)
    observed_state = verification["observed_state"]
    if (
        verification["status"] in ("CONFIRMED", "MISMATCH")
        and observed_state["state_sha256"] is None
    ):
        raise ContractError("conclusive verification requires an observed state digest")
    if verification["status"] in ("CONFIRMED", "MISMATCH") and not verification[
        "evidence_refs"
    ]:
        raise ContractError("conclusive verification requires independent evidence")
    return verification


def validate_receipt_verification_binding(
    receipt: object,
    verification: object,
    *,
    expected_action_id: str,
    expected_action_sha256: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Bind receipt and verification to an already-known exact action identity."""

    validated_receipt = validate_external_action_receipt(receipt)
    validated_verification = validate_external_action_verification(verification)
    if validated_receipt["action_id"] != validated_verification["action_id"]:
        raise ContractError("receipt and verification action identifiers differ")
    if validated_receipt["action_sha256"] != validated_verification["action_sha256"]:
        raise ContractError("receipt and verification action digests differ")
    if validated_receipt["action_id"] != expected_action_id:
        raise ContractError("receipt action identifier differs from the expected action")
    if validated_receipt["action_sha256"] != expected_action_sha256:
        raise ContractError("receipt action digest differs from the expected action")
    receipt_ref = validated_verification.get("receipt_ref")
    if receipt_ref is None:
        raise ContractError("receipt/verification binding requires a receipt reference")
    if receipt_ref["ref_id"] != f"receipt:{expected_action_id}":
        raise ContractError("verification receipt reference identifier is invalid")
    if receipt_ref["sha256"] != canonical_json_sha256(validated_receipt):
        raise ContractError("verification receipt reference digest is invalid")
    return validated_receipt, validated_verification


__all__ = (
    "validate_consequence_proposal",
    "validate_external_action_receipt",
    "validate_external_action_verification",
    "validate_receipt_verification_binding",
)
