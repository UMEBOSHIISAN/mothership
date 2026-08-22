from __future__ import annotations

import copy
import unittest

from orchestration.lib.contracts import validate_contract
from orchestration.lib.errors import ContractError


EXECUTION_PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}


def frozen_display() -> dict[str, object]:
    parameters = EXECUTION_PARAMETERS
    return {
        "target": f"PR #{parameters['pull_request']} -> {parameters['expected_base']}",
        "scope": (
            f"repository={parameters['repository']}; "
            f"expected_head_sha={parameters['expected_head_sha']}; "
            f"expected_base={parameters['expected_base']}; merge_method=merge"
        ),
        "excluded_operations": ["squash", "rebase", "force_push", "branch_delete"],
        "consequence_if_approved": (
            f"PR #{parameters['pull_request']} changes will be integrated into "
            f"{parameters['expected_base']}."
        ),
    }


def frozen_action() -> dict[str, object]:
    return {
        "action_id": "act-merge-pr-001",
        "operation": "github.merge_pr",
        "execution_parameters": copy.deepcopy(EXECUTION_PARAMETERS),
        "display": frozen_display(),
    }


def approval_event() -> dict[str, object]:
    return {
        "schema_version": "authority-action-approval.v0",
        "event_type": "authority_action_approval",
        "event_id": "event-" + "1" * 32,
        "decision": "approve",
        "approver_class": "human",
        "action": frozen_action(),
        "action_sha256": "a" * 64,
        "recorded_at": "2026-08-22T10:00:00Z",
        "expires_at": "2026-08-22T10:10:00Z",
        "max_uses": 1,
    }


def consume_event() -> dict[str, object]:
    return {
        "schema_version": "authority-action-consume.v0",
        "event_type": "authority_action_consume",
        "event_id": "event-" + "2" * 32,
        "approval_event_id": "event-" + "1" * 32,
        "action_id": "act-merge-pr-001",
        "action_sha256": "a" * 64,
        "consumed_at": "2026-08-22T10:01:00Z",
        "expires_at": "2026-08-22T10:10:00Z",
    }


class AuthorityActionContractTests(unittest.TestCase):
    def test_approve_and_reject_events_validate_with_exact_frozen_action(self) -> None:
        for decision in ("approve", "reject"):
            event = approval_event()
            event["decision"] = decision
            self.assertEqual(event, validate_contract("authority-action-approval", event))
        self.assertEqual("human", approval_event()["approver_class"])
        self.assertEqual(1, approval_event()["max_uses"])

    def test_consume_event_validates_with_exact_closed_fields(self) -> None:
        event = consume_event()
        self.assertEqual(event, validate_contract("authority-action-consume", event))

    def test_unknown_top_level_and_nested_fields_are_rejected(self) -> None:
        approval = approval_event()
        invalid = (
            dict(approval, unknown=True),
            dict(approval, action={**approval["action"], "unknown": True}),
            dict(
                approval,
                action={
                    **approval["action"],
                    "execution_parameters": {
                        **approval["action"]["execution_parameters"],
                        "unknown": True,
                    },
                },
            ),
            dict(
                approval,
                action={
                    **approval["action"],
                    "display": {**approval["action"]["display"], "unknown": True},
                },
            ),
            dict(consume_event(), unknown=True),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract(
                        "authority-action-consume"
                        if value["event_type"] == "authority_action_consume"
                        else "authority-action-approval",
                        value,
                    )

    def test_invalid_ids_digests_timestamps_and_expiry_shapes_are_rejected(self) -> None:
        approval = approval_event()
        invalid_approvals = (
            dict(approval, event_id="event-short"),
            dict(approval, event_id="event-" + "A" * 32),
            dict(approval, action={**approval["action"], "action_id": "bad action"}),
            dict(approval, action_sha256="A" * 64),
            dict(approval, action_sha256="a" * 63),
            dict(approval, recorded_at="2026-08-22T10:00:00+00:00"),
            dict(approval, expires_at="2026-08-22T10:10:00Z\n"),
            dict(approval, expires_at=None),
        )
        for value in invalid_approvals:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("authority-action-approval", value)

        consume = consume_event()
        invalid_consumes = (
            dict(consume, event_id="event-short"),
            dict(consume, approval_event_id="approval-short"),
            dict(consume, action_id="bad action"),
            dict(consume, action_sha256="A" * 64),
            dict(consume, consumed_at="2026-08-22T10:01:00+00:00"),
            dict(consume, expires_at="2026-08-22T10:10:00Z\n"),
            dict(consume, expires_at=None),
        )
        for value in invalid_consumes:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("authority-action-consume", value)

    def test_decision_approver_and_operation_constants_are_closed(self) -> None:
        approval = approval_event()
        for decision in ("approve", "reject"):
            expected = dict(approval, decision=decision)
            self.assertEqual(
                expected,
                validate_contract("authority-action-approval", expected),
            )
        for invalid in (
            dict(approval, decision="execute"),
            dict(approval, approver_class="agent"),
            dict(approval, max_uses=2),
            dict(approval, max_uses=True),
            dict(approval, schema_version="decision-approval.v0"),
            dict(approval, event_type="approval_granted"),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractError):
                    validate_contract("authority-action-approval", invalid)

        action = frozen_action()
        for operation in ("shell.command", "github.close_issue", "github.merge_pr.v1"):
            with self.subTest(operation=operation):
                with self.assertRaises(ContractError):
                    validate_contract(
                        "authority-action-approval",
                        {**approval, "action": {**action, "operation": operation}},
                    )
        for merge_method in ("rebase", "squash"):
            with self.subTest(merge_method=merge_method):
                invalid_action = {
                    **action,
                    "execution_parameters": {
                        **EXECUTION_PARAMETERS,
                        "merge_method": merge_method,
                    },
                }
                with self.assertRaises(ContractError):
                    validate_contract("authority-action-approval", {**approval, "action": invalid_action})

    def test_execution_parameters_and_display_are_strict(self) -> None:
        approval = approval_event()
        action = approval["action"]
        for invalid_action in (
            {**action, "execution_parameters": {**EXECUTION_PARAMETERS, "pull_request": 0}},
            {**action, "execution_parameters": {**EXECUTION_PARAMETERS, "pull_request": True}},
            {
                **action,
                "execution_parameters": {
                    **EXECUTION_PARAMETERS,
                    "expected_head_sha": "not-a-sha",
                },
            },
            {**action, "execution_parameters": {**EXECUTION_PARAMETERS, "repository": "not-a-repo"}},
            {**action, "execution_parameters": {**EXECUTION_PARAMETERS, "extra": True}},
            {**action, "display": {**action["display"], "excluded_operations": ["squash", "squash", "rebase", "force_push", "branch_delete"]}},
            {**action, "display": {**action["display"], "excluded_operations": ["squash", "rebase"]}},
        ):
            with self.subTest(invalid_action=invalid_action):
                with self.assertRaises(ContractError):
                    validate_contract("authority-action-approval", {**approval, "action": invalid_action})

    def test_consume_relationship_mismatches_are_rejected_by_binding_helper(self) -> None:
        approval = approval_event()
        consume = consume_event()

        def validate_consume_binding(
            approval_event_value: dict[str, object], consume_event_value: dict[str, object]
        ) -> None:
            validate_contract("authority-action-approval", approval_event_value)
            validate_contract("authority-action-consume", consume_event_value)
            if consume_event_value["approval_event_id"] != approval_event_value["event_id"]:
                raise ContractError("approval event mismatch")
            if consume_event_value["action_id"] != approval_event_value["action"]["action_id"]:
                raise ContractError("action mismatch")
            if consume_event_value["action_sha256"] != approval_event_value["action_sha256"]:
                raise ContractError("digest mismatch")
            if consume_event_value["expires_at"] != approval_event_value["expires_at"]:
                raise ContractError("expiry mismatch")

        validate_consume_binding(approval, consume)
        for mismatch in (
            dict(consume, approval_event_id="event-" + "3" * 32),
            dict(consume, action_id="act-merge-pr-002"),
            dict(consume, action_sha256="b" * 64),
            dict(consume, expires_at="2026-08-22T10:11:00Z"),
        ):
            with self.subTest(mismatch=mismatch):
                with self.assertRaises(ContractError):
                    validate_consume_binding(approval, mismatch)

    def test_authority_action_events_are_distinct_from_existing_approval_event(self) -> None:
        with self.assertRaises(ContractError):
            validate_contract("approval-event", approval_event())
        with self.assertRaises(ContractError):
            validate_contract("authority-action-approval", {
                **approval_event(),
                "schema_version": "0.1.0",
                "event_type": "approval_granted",
            })
        with self.assertRaises(ContractError):
            validate_contract("authority-action-consume", approval_event())


if __name__ == "__main__":
    unittest.main()
