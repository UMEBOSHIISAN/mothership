from __future__ import annotations

import copy
import datetime
import inspect
import unittest
from unittest.mock import patch

from orchestration.lib.canonical import canonical_json_sha256
from orchestration.lib.action_authority import (
    ActionBindingError,
    FrozenAction,
    MalformedActionError,
    UnsupportedOperationError,
    action_sha256,
    freeze_action,
    validate_decision_transport,
)


EXECUTION_PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}

EXPECTED_DISPLAY = {
    "target": "PR #5 -> main",
    "scope": (
        "repository=UMEBOSHIISAN/mothership; "
        "expected_head_sha=e2161c0c27af68221ad507a05583a5fbdaecefe1; "
        "expected_base=main; merge_method=merge"
    ),
    "excluded_operations": ["squash", "rebase", "force_push", "branch_delete"],
    "consequence_if_approved": "PR #5 changes will be integrated into main.",
}


class ActionAuthorityTests(unittest.TestCase):
    def freeze(self, *, action_id: str = "act-merge-pr-001", parameters: dict[str, object] | None = None) -> FrozenAction:
        return freeze_action(
            action_id,
            "github.merge_pr",
            copy.deepcopy(parameters if parameters is not None else EXECUTION_PARAMETERS),
        )

    def test_freeze_accepts_only_executable_action_inputs_and_derives_exact_display(self) -> None:
        self.assertEqual(
            ["action_id", "operation", "execution_parameters"],
            list(inspect.signature(freeze_action).parameters),
        )
        frozen = self.freeze()
        display = frozen.action["display"]
        self.assertEqual(EXPECTED_DISPLAY["target"], display["target"])
        self.assertEqual(EXPECTED_DISPLAY["scope"], display["scope"])
        self.assertEqual(EXPECTED_DISPLAY["excluded_operations"], list(display["excluded_operations"]))
        self.assertEqual(EXPECTED_DISPLAY["consequence_if_approved"], display["consequence_if_approved"])
        with self.assertRaises(TypeError):
            freeze_action("act-merge-pr-001", "github.merge_pr", EXECUTION_PARAMETERS, EXPECTED_DISPLAY)  # type: ignore[call-arg]

    def test_each_valid_executable_parameter_change_changes_display_and_digest(self) -> None:
        original = self.freeze()
        changes = {
            "repository": "UMEBOSHIISAN/other-repository",
            "pull_request": 6,
            "expected_head_sha": "f" * 40,
            "expected_base": "release",
        }
        for name, value in changes.items():
            with self.subTest(name=name):
                parameters = {**EXECUTION_PARAMETERS, name: value}
                changed = self.freeze(parameters=parameters)
                self.assertNotEqual(original.action["display"], changed.action["display"])
                self.assertNotEqual(original.action_sha256, changed.action_sha256)

    def test_frozen_action_is_defensive_and_caller_cannot_inject_display_or_governance(self) -> None:
        parameters = copy.deepcopy(EXECUTION_PARAMETERS)
        frozen = freeze_action("act-merge-pr-001", "github.merge_pr", parameters)
        original_digest = frozen.action_sha256
        parameters["repository"] = "attacker/repository"
        self.assertEqual("UMEBOSHIISAN/mothership", frozen.action["execution_parameters"]["repository"])
        self.assertEqual(original_digest, frozen.action_sha256)
        with self.assertRaises(TypeError):
            frozen.action["display"]["target"] = "safe-looking target"  # type: ignore[index]
        for field in ("display", "recommendation", "risk", "human_gate", "authority"):
            with self.subTest(field=field):
                with self.assertRaises(MalformedActionError):
                    self.freeze(parameters={**EXECUTION_PARAMETERS, field: "injected"})

    def test_reconstructed_or_altered_frozen_actions_are_revalidated(self) -> None:
        frozen = self.freeze()
        altered = {
            "action_id": "act-merge-pr-001",
            "operation": "github.merge_pr",
            "execution_parameters": copy.deepcopy(EXECUTION_PARAMETERS),
            "display": copy.deepcopy(EXPECTED_DISPLAY),
        }
        altered["display"] = {**EXPECTED_DISPLAY, "excluded_operations": ["squash", "squash", "rebase", "force_push"]}
        with self.assertRaises(TypeError):
            FrozenAction(altered, frozen.action_sha256, frozen.expires_at)

    def test_action_digest_is_canonical_sha256_of_the_exact_action_not_expiry(self) -> None:
        action = {
            "action_id": "act-merge-pr-001",
            "operation": "github.merge_pr",
            "execution_parameters": copy.deepcopy(EXECUTION_PARAMETERS),
            "display": copy.deepcopy(EXPECTED_DISPLAY),
        }
        self.assertEqual(canonical_json_sha256(action), action_sha256(action))
        self.assertRegex(action_sha256(action), r"\A[0-9a-f]{64}\Z")
        with self.assertRaises(MalformedActionError):
            action_sha256({**action, "expires_at": "2030-01-01T00:00:00Z"})

    def test_freeze_generates_fixed_ten_minute_deadline_excluded_from_digest(self) -> None:
        before = datetime.datetime.now(datetime.UTC)
        frozen = self.freeze()
        after = datetime.datetime.now(datetime.UTC)
        deadline = datetime.datetime.strptime(frozen.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
        self.assertLessEqual(deadline, after + datetime.timedelta(minutes=10))
        self.assertGreaterEqual(deadline, before + datetime.timedelta(minutes=9, seconds=58))
        with self.assertRaises(TypeError):
            FrozenAction(frozen.action, frozen.action_sha256, "2099-01-01T00:00:00Z")

    def test_public_constructor_cannot_renew_an_expired_action_within_a_new_policy_window(self) -> None:
        frozen_at = datetime.datetime(2026, 8, 22, 10, 0, tzinfo=datetime.UTC)
        with patch("orchestration.lib.action_authority._utc_now", return_value=frozen_at):
            frozen = self.freeze()
        after_original_expiry = frozen_at + datetime.timedelta(minutes=11)
        replacement_expiry = after_original_expiry + datetime.timedelta(minutes=10)
        original_expiry = datetime.datetime.strptime(frozen.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
        self.assertLess(original_expiry, after_original_expiry)
        self.assertLessEqual(replacement_expiry, after_original_expiry + datetime.timedelta(minutes=10))
        with self.assertRaises(TypeError):
            FrozenAction(
                frozen.action,
                frozen.action_sha256,
                replacement_expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

    def test_validate_transport_returns_only_bound_approve_or_reject_decisions(self) -> None:
        frozen = self.freeze()
        for decision in ("approve", "reject"):
            with self.subTest(decision=decision):
                self.assertEqual(
                    {
                        "decision": decision,
                        "action_id": "act-merge-pr-001",
                        "action_sha256": frozen.action_sha256,
                    },
                    validate_decision_transport(frozen, decision, "act-merge-pr-001", frozen.action_sha256),
                )

    def test_validate_transport_rejects_unbound_natural_language_stale_ids_and_bad_digests(self) -> None:
        frozen = self.freeze()
        for decision, action_id, digest in (
            ("進めて", None, None),
            ("proceed", None, None),
            ("approve", None, None),
            ("承認", None, None),
            ("approve", "", frozen.action_sha256),
            ("approve", 5, frozen.action_sha256),
            ("approve", "act-merge-pr-other", frozen.action_sha256),
            ("approve", "act-merge-pr-001", None),
            ("approve", "act-merge-pr-001", 5),
            ("approve", "act-merge-pr-001", "a" * 63),
            ("approve", "act-merge-pr-001", "b" * 64),
        ):
            with self.subTest(decision=decision, action_id=action_id, digest=digest):
                with self.assertRaises(ActionBindingError):
                    validate_decision_transport(frozen, decision, action_id, digest)

    def test_closed_action_profile_rejects_unsupported_and_malformed_inputs(self) -> None:
        invalid_profiles = (
            ("shell.command", EXECUTION_PARAMETERS, UnsupportedOperationError),
            ("github.close_issue", EXECUTION_PARAMETERS, UnsupportedOperationError),
            ("github.merge_pr", {"repository": "UMEBOSHIISAN/mothership"}, MalformedActionError),
            ("github.merge_pr", ["not", "a", "dict"], MalformedActionError),  # type: ignore[arg-type]
            ("github.merge_pr", {**EXECUTION_PARAMETERS, "merge_method": "rebase"}, MalformedActionError),
        )
        for operation, parameters, error in invalid_profiles:
            with self.subTest(operation=operation, parameters=parameters):
                with self.assertRaises(error):
                    freeze_action("act-merge-pr-001", operation, parameters)  # type: ignore[arg-type]

    def test_closed_action_profile_rejects_invalid_action_ids_and_non_mapping_display(self) -> None:
        for action_id in ("", "merge-pr-001", "act-bad action", 5):
            with self.subTest(action_id=action_id):
                with self.assertRaises(MalformedActionError):
                    freeze_action(action_id, "github.merge_pr", EXECUTION_PARAMETERS)  # type: ignore[arg-type]
        frozen = self.freeze()
        with self.assertRaises(TypeError):
            FrozenAction(
                {
                    "action_id": "act-merge-pr-001",
                    "operation": "github.merge_pr",
                    "execution_parameters": copy.deepcopy(EXECUTION_PARAMETERS),
                    "display": ["not", "a", "mapping"],
                },
                frozen.action_sha256,
                frozen.expires_at,
            )


if __name__ == "__main__":
    unittest.main()
