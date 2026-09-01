from __future__ import annotations

import copy
import unittest

from orchestration.lib.contracts import validate_contract
from orchestration.lib.canonical import canonical_json_sha256
from orchestration.lib.errors import ContractError


ACTION_SHA256 = "a" * 64
STATE_SHA256 = "b" * 64


def evidence_ref(ref_id: str = "evidence:github-pr-42") -> dict[str, object]:
    return {"ref_id": ref_id, "sha256": "c" * 64}


def consequence_proposal(
    *, policy_disposition: str = "ELIGIBLE"
) -> dict[str, object]:
    return {
        "schema_version": "consequence-proposal.v0",
        "proposal_id": "prop-github-merge-42",
        "operation": "github.merge_pr",
        "target": {
            "repository": "UMEBOSHIISAN/mothership",
            "pull_request": 42,
        },
        "expected_preconditions": {
            "expected_head_sha": "d" * 40,
            "expected_base": "main",
            "state_sha256": STATE_SHA256,
        },
        "expected_consequence": {"merge_method": "merge"},
        "evidence_refs": [evidence_ref()],
        "unknowns": [],
        "policy_disposition": policy_disposition,
        "policy_evidence_refs": [evidence_ref("policy:merge-protection")],
        "identity_evidence_refs": [evidence_ref("identity:caller-attestation")],
        "role_evidence_refs": [evidence_ref("role:repository-maintainer")],
        "authority_effect": False,
        "execution_effect": False,
        "delegation_effect": False,
    }


def external_action_receipt(*, status: str = "SUCCESS") -> dict[str, object]:
    return {
        "schema_version": "external-action-receipt.v0",
        "action_id": "act-merge-pr-42",
        "action_sha256": ACTION_SHA256,
        "executor_ref": evidence_ref("executor:bounded-github-merge"),
        "started_at": "2026-09-01T04:00:00Z",
        "finished_at": "2026-09-01T04:00:01Z",
        "status": status,
        "executor_observation_ref": evidence_ref("observation:executor-result-42"),
    }


def external_action_verification(
    *, status: str = "CONFIRMED", receipt: dict[str, object] | None = None
) -> dict[str, object]:
    receipt = external_action_receipt() if receipt is None else receipt
    return {
        "schema_version": "external-action-verification.v0",
        "action_id": "act-merge-pr-42",
        "action_sha256": ACTION_SHA256,
        "verification_method": "read_only_external_observation",
        "observed_state": {
            "summary": "The pull request is merged.",
            "state_sha256": "e" * 64,
        },
        "evidence_refs": [evidence_ref("observation:github-pr-42-readback")],
        "observed_at": "2026-09-01T04:00:02Z",
        "status": status,
        "receipt_ref": {
            "ref_id": f"receipt:{receipt['action_id']}",
            "sha256": canonical_json_sha256(receipt),
        },
    }


class ExternalActionSchemaTests(unittest.TestCase):
    def test_three_exact_contracts_validate(self) -> None:
        cases = (
            ("consequence-proposal.v0", consequence_proposal()),
            ("external-action-receipt.v0", external_action_receipt()),
            ("external-action-verification.v0", external_action_verification()),
        )
        for kind, value in cases:
            with self.subTest(kind=kind):
                self.assertEqual(value, validate_contract(kind, value))

    def test_proposal_is_closed_non_authorizing_and_non_delegating(self) -> None:
        proposal = consequence_proposal()
        invalid_values = []
        for field in ("authority_effect", "execution_effect", "delegation_effect"):
            invalid_values.append({**proposal, field: True})
        for field in (
            "authority_token",
            "approval_token",
            "credential",
            "credentials",
            "shell_command",
            "command",
            "worker_selection",
            "delegated_to",
        ):
            invalid_values.append({**proposal, field: "not-permitted"})
        for invalid in invalid_values:
            with self.subTest(fields=tuple(sorted(set(invalid) - set(proposal)))):
                with self.assertRaises(ContractError):
                    validate_contract("consequence-proposal.v0", invalid)

    def test_proposal_preserves_hard_policy_disposition_without_authority(self) -> None:
        for disposition in ("ELIGIBLE", "DENY", "UNKNOWN"):
            with self.subTest(disposition=disposition):
                proposal = validate_contract(
                    "consequence-proposal.v0",
                    consequence_proposal(policy_disposition=disposition),
                )
                self.assertEqual(disposition, proposal["policy_disposition"])
                self.assertIs(False, proposal["authority_effect"])
                self.assertIs(False, proposal["execution_effect"])
                self.assertIs(False, proposal["delegation_effect"])

    def test_proposal_rejects_state_target_and_reference_drift(self) -> None:
        proposal = consequence_proposal()
        cases = (
            {**proposal, "operation": "shell.command"},
            {**proposal, "target": {**proposal["target"], "unknown": True}},
            {
                **proposal,
                "expected_preconditions": {
                    **proposal["expected_preconditions"],
                    "state_sha256": "not-a-digest",
                },
            },
            {**proposal, "expected_consequence": {"merge_method": "squash"}},
            {**proposal, "evidence_refs": [{"ref_id": "evidence:unbound"}]},
            {**proposal, "policy_disposition": "APPROVED"},
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractError):
                    validate_contract("consequence-proposal.v0", invalid)

    def test_proposal_unknowns_are_bounded_evidence_records(self) -> None:
        proposal = consequence_proposal()
        proposal["unknowns"] = [evidence_ref("unknown:merge-state")]
        self.assertEqual(proposal, validate_contract("consequence-proposal.v0", proposal))
        for unknowns in (
            ["shell_command=git push"],
            ["credential=secret"],
            [{"ref_id": "unknown:unbound"}],
        ):
            with self.subTest(unknowns=unknowns):
                with self.assertRaises(ContractError):
                    validate_contract(
                        "consequence-proposal.v0",
                        {**proposal, "unknowns": unknowns},
                    )

    def test_receipt_is_closed_and_status_is_bounded(self) -> None:
        receipt = external_action_receipt()
        for status in ("SUCCESS", "FAILED", "UNKNOWN"):
            with self.subTest(status=status):
                value = {**receipt, "status": status}
                self.assertEqual(value, validate_contract("external-action-receipt.v0", value))
        invalid_values = (
            {**receipt, "status": "CONFIRMED"},
            {**receipt, "action_sha256": "not-a-digest"},
            {**receipt, "authority_effect": True},
            {**receipt, "retry_authorized": True},
            {**receipt, "verification_status": "CONFIRMED"},
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractError):
                    validate_contract("external-action-receipt.v0", invalid)

    def test_verification_is_closed_read_only_and_preserves_status(self) -> None:
        verification = external_action_verification()
        for status in ("CONFIRMED", "MISMATCH", "UNKNOWN"):
            with self.subTest(status=status):
                value = {**verification, "status": status}
                result = validate_contract("external-action-verification.v0", value)
                self.assertEqual(status, result["status"])
        invalid_values = (
            {**verification, "status": "SUCCESS"},
            {**verification, "action_sha256": "not-a-digest"},
            {**verification, "authority_effect": True},
            {**verification, "mutation_effect": True},
            {**verification, "retry_authorized": True},
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractError):
                    validate_contract("external-action-verification.v0", invalid)

    def test_every_nested_object_is_closed(self) -> None:
        mutations = []
        proposal = consequence_proposal()
        for field in ("target", "expected_preconditions", "expected_consequence"):
            invalid = copy.deepcopy(proposal)
            invalid[field]["unknown"] = True
            mutations.append(("consequence-proposal.v0", invalid))
        receipt = external_action_receipt()
        invalid_receipt = copy.deepcopy(receipt)
        invalid_receipt["executor_ref"]["unknown"] = True
        mutations.append(("external-action-receipt.v0", invalid_receipt))
        verification = external_action_verification()
        invalid_verification = copy.deepcopy(verification)
        invalid_verification["observed_state"]["unknown"] = True
        mutations.append(("external-action-verification.v0", invalid_verification))
        for kind, invalid in mutations:
            with self.subTest(kind=kind):
                with self.assertRaises(ContractError):
                    validate_contract(kind, invalid)


class ExternalActionBindingTests(unittest.TestCase):
    def external_action_api(self):
        try:
            from orchestration.lib.external_action import (
                validate_consequence_proposal,
                validate_external_action_receipt,
                validate_external_action_verification,
                validate_receipt_verification_binding,
            )
        except ImportError as error:
            self.fail(f"external-action contract API is missing: {error}")
        return (
            validate_consequence_proposal,
            validate_external_action_receipt,
            validate_external_action_verification,
            validate_receipt_verification_binding,
        )

    def test_pure_validators_preserve_their_closed_objects(self) -> None:
        validate_proposal, validate_receipt, validate_verification, _ = (
            self.external_action_api()
        )
        proposal = consequence_proposal(policy_disposition="DENY")
        receipt = external_action_receipt(status="UNKNOWN")
        verification = external_action_verification(status="MISMATCH")
        self.assertEqual(proposal, validate_proposal(proposal))
        self.assertEqual(receipt, validate_receipt(receipt))
        self.assertEqual(verification, validate_verification(verification))

    def test_each_validator_rejects_a_different_contract_kind(self) -> None:
        validate_proposal, validate_receipt, validate_verification, _ = (
            self.external_action_api()
        )
        cases = (
            (validate_proposal, external_action_receipt()),
            (validate_receipt, consequence_proposal()),
            (validate_verification, external_action_receipt()),
        )
        for validator, value in cases:
            with self.subTest(validator=validator.__name__):
                with self.assertRaises(ContractError):
                    validator(value)

    def test_success_receipt_does_not_satisfy_verification(self) -> None:
        _, _, validate_verification, _ = self.external_action_api()
        with self.assertRaises(ContractError):
            validate_verification(external_action_receipt(status="SUCCESS"))

    def test_unknown_and_mismatch_verification_are_not_promoted(self) -> None:
        _, _, validate_verification, _ = self.external_action_api()
        unknown = external_action_verification(status="UNKNOWN")
        unknown["observed_state"] = {
            "summary": "The external state could not be read.",
            "state_sha256": None,
        }
        mismatch = external_action_verification(status="MISMATCH")
        self.assertEqual("UNKNOWN", validate_verification(unknown)["status"])
        self.assertEqual("MISMATCH", validate_verification(mismatch)["status"])

    def test_confirmed_or_mismatch_requires_an_observed_state_digest(self) -> None:
        _, _, validate_verification, _ = self.external_action_api()
        for status in ("CONFIRMED", "MISMATCH"):
            verification = external_action_verification(status=status)
            verification["observed_state"] = {
                "summary": "No readable state was returned.",
                "state_sha256": None,
            }
            with self.subTest(status=status):
                with self.assertRaises(ContractError):
                    validate_verification(verification)

    def test_conclusive_verification_requires_independent_evidence(self) -> None:
        _, _, validate_verification, _ = self.external_action_api()
        for status in ("CONFIRMED", "MISMATCH"):
            with self.subTest(status=status):
                with self.assertRaises(ContractError):
                    validate_verification(
                        {
                            **external_action_verification(status=status),
                            "evidence_refs": [],
                        }
                    )
        unknown = external_action_verification(status="UNKNOWN")
        unknown["evidence_refs"] = []
        unknown["observed_state"] = {
            "summary": "The external state could not be read.",
            "state_sha256": None,
        }
        self.assertEqual("UNKNOWN", validate_verification(unknown)["status"])

    def test_binding_requires_the_exact_action_identity(self) -> None:
        _, _, _, validate_binding = self.external_action_api()
        receipt = external_action_receipt()
        verification = external_action_verification(receipt=receipt)
        expected = {
            "expected_action_id": receipt["action_id"],
            "expected_action_sha256": receipt["action_sha256"],
        }
        self.assertEqual(
            (receipt, verification), validate_binding(receipt, verification, **expected)
        )
        mismatches = (
            {**verification, "action_id": "act-merge-pr-43"},
            {**verification, "action_sha256": "f" * 64},
        )
        for mismatch in mismatches:
            with self.subTest(mismatch=mismatch):
                with self.assertRaises(ContractError):
                    validate_binding(receipt, mismatch, **expected)

    def test_binding_rejects_a_matching_pair_for_a_different_action(self) -> None:
        _, _, _, validate_binding = self.external_action_api()
        receipt = {**external_action_receipt(), "action_id": "act-merge-pr-99"}
        verification = external_action_verification(receipt=receipt)
        with self.assertRaises(ContractError):
            validate_binding(
                receipt,
                verification,
                expected_action_id="act-merge-pr-42",
                expected_action_sha256=ACTION_SHA256,
            )

    def test_binding_requires_a_matching_canonical_receipt_reference(self) -> None:
        _, _, _, validate_binding = self.external_action_api()
        receipt = external_action_receipt()
        expected = {
            "expected_action_id": receipt["action_id"],
            "expected_action_sha256": receipt["action_sha256"],
        }
        verification = external_action_verification(receipt=receipt)
        self.assertEqual(
            (receipt, verification), validate_binding(receipt, verification, **expected)
        )
        without_receipt_ref = dict(verification)
        without_receipt_ref.pop("receipt_ref")
        with self.assertRaises(ContractError):
            validate_binding(receipt, without_receipt_ref, **expected)
        for receipt_ref in (
            {
                "ref_id": "receipt:act-merge-pr-other",
                "sha256": canonical_json_sha256(receipt),
            },
            {
                "ref_id": "receipt:act-merge-pr-42",
                "sha256": "f" * 64,
            },
        ):
            with self.subTest(receipt_ref=receipt_ref):
                with self.assertRaises(ContractError):
                    validate_binding(
                        receipt,
                        {**verification, "receipt_ref": receipt_ref},
                        **expected,
                    )

    def test_binding_validates_both_inputs_before_comparing_identity(self) -> None:
        _, _, _, validate_binding = self.external_action_api()
        receipt = external_action_receipt()
        verification = external_action_verification()
        with self.assertRaises(ContractError):
            validate_binding(
                {**receipt, "retry_authorized": True},
                verification,
                expected_action_id=receipt["action_id"],
                expected_action_sha256=receipt["action_sha256"],
            )
        with self.assertRaises(ContractError):
            validate_binding(
                receipt,
                {**verification, "mutation_effect": True},
                expected_action_id=receipt["action_id"],
                expected_action_sha256=receipt["action_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
