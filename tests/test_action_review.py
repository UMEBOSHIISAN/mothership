from __future__ import annotations

import copy
import datetime
import unittest
from unittest.mock import patch

from mothership.action_review import (
    ActionReviewError,
    build_review_request,
    validate_review_response,
)
from orchestration.lib.action_authority import (
    ActionBindingError,
    ExpiredActionError,
    FrozenAction,
    freeze_action,
)
from orchestration.lib.canonical import canonical_json_sha256
from orchestration.lib.contracts import ContractError, validate_contract


EXECUTION_PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}
HOST_CONTEXT = {
    "host_id": "dots-host-001",
    "session_id": "session-001",
    "actor_id": "actor-001",
    "runtime_generation": "runtime-001",
    "scope": ["github.merge_pr"],
}
NOW = datetime.datetime(2026, 10, 5, 12, 0, tzinfo=datetime.UTC)


class ActionReviewTests(unittest.TestCase):
    def freeze(self, *, action_id: str = "act-review-001") -> FrozenAction:
        return freeze_action(action_id, "github.merge_pr", copy.deepcopy(EXECUTION_PARAMETERS))

    def issue(self, *, action_id: str = "act-review-001", context: dict[str, object] | None = None):
        with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
            frozen = self.freeze(action_id=action_id)
            request = build_review_request(
                frozen,
                request_id="review-001",
                host_context=copy.deepcopy(context or HOST_CONTEXT),
            )
        return frozen, request

    @staticmethod
    def response(frozen: FrozenAction, request: dict[str, object], decision: str = "approve"):
        return {
            "schema_version": "authority-action-review-response.v0",
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "action_id": frozen.action["action_id"],
            "action_sha256": frozen.action_sha256,
            "decision": decision,
        }

    def test_error_is_a_public_action_binding_error(self) -> None:
        self.assertTrue(issubclass(ActionReviewError, ActionBindingError))

    def test_builds_exact_detached_request_with_canonical_digest(self) -> None:
        frozen, request = self.issue()

        self.assertEqual(
            {
                "schema_version",
                "request_id",
                "action",
                "action_sha256",
                "expires_at",
                "host_context",
                "request_sha256",
            },
            set(request),
        )
        unsigned = {key: value for key, value in request.items() if key != "request_sha256"}
        self.assertEqual(request["request_sha256"], canonical_json_sha256(unsigned))
        self.assertEqual(frozen.action_sha256, request["action_sha256"])
        self.assertEqual(frozen.expires_at, request["expires_at"])
        self.assertIsNot(request["action"], frozen.action)
        self.assertIsNot(request["host_context"], HOST_CONTEXT)
        self.assertEqual(request, validate_contract("authority-action-review-request", request))

        request["action"]["execution_parameters"]["pull_request"] = 99
        request["host_context"]["scope"].append("future.operation")
        self.assertEqual(5, frozen.action["execution_parameters"]["pull_request"])
        self.assertEqual(["github.merge_pr"], HOST_CONTEXT["scope"])

    def test_same_inputs_are_deterministic_and_new_action_ids_remain_distinct(self) -> None:
        first, first_request = self.issue(action_id="act-review-deterministic")
        second, second_request = self.issue(action_id="act-review-deterministic")
        self.assertEqual(first_request, second_request)
        self.assertEqual(first_request["request_sha256"], second_request["request_sha256"])

        _, distinct_request = self.issue(action_id="act-review-distinct")
        self.assertNotEqual(first_request["action"]["action_id"], distinct_request["action"]["action_id"])
        self.assertNotEqual(first_request["action_sha256"], distinct_request["action_sha256"])

    def test_approve_and_reject_return_the_existing_transport_shape(self) -> None:
        frozen, request = self.issue()
        with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
            for decision in ("approve", "reject"):
                with self.subTest(decision=decision):
                    self.assertEqual(
                        {
                            "decision": decision,
                            "action_id": "act-review-001",
                            "action_sha256": frozen.action_sha256,
                        },
                        validate_review_response(
                            frozen,
                            request,
                            self.response(frozen, request, decision),
                            current_host_context=copy.deepcopy(HOST_CONTEXT),
                        ),
                    )

    def test_empty_scope_is_preserved_and_only_reject_is_valid(self) -> None:
        frozen, request = self.issue(context={**HOST_CONTEXT, "scope": []})
        reject = self.response(frozen, request, "reject")
        approve = self.response(frozen, request, "approve")
        with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
            self.assertEqual("reject", validate_review_response(
                frozen, request, reject, current_host_context={**HOST_CONTEXT, "scope": []}
            )["decision"])
            with self.assertRaises(ActionReviewError):
                validate_review_response(
                    frozen, request, approve, current_host_context={**HOST_CONTEXT, "scope": []}
                )

    def test_context_drift_rejects_both_decisions_before_transport_validation(self) -> None:
        frozen, request = self.issue()
        for field, value in (
            ("host_id", "other-host"),
            ("session_id", "other-session"),
            ("actor_id", "other-actor"),
            ("runtime_generation", "runtime-002"),
            ("scope", ["other.operation", "github.merge_pr"]),
        ):
            changed = copy.deepcopy(HOST_CONTEXT)
            changed[field] = value
            with self.subTest(field=field):
                with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
                    for decision in ("approve", "reject"):
                        with self.subTest(decision=decision):
                            with self.assertRaises(ActionReviewError):
                                validate_review_response(
                                    frozen,
                                    request,
                                    self.response(frozen, request, decision),
                                    current_host_context=changed,
                                )

    def test_context_scope_order_is_part_of_the_canonical_binding(self) -> None:
        context = {**HOST_CONTEXT, "scope": ["other.operation", "github.merge_pr"]}
        frozen, request = self.issue(context=context)
        changed = {**context, "scope": ["github.merge_pr", "other.operation"]}
        with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
            with self.assertRaises(ActionReviewError):
                validate_review_response(
                    frozen,
                    request,
                    self.response(frozen, request, "reject"),
                    current_host_context=changed,
                )

    def test_context_has_closed_strict_types_ids_and_scope(self) -> None:
        invalid_contexts = (
            {**HOST_CONTEXT, "unknown": "field"},
            {**HOST_CONTEXT, "host_id": True},
            {**HOST_CONTEXT, "session_id": ""},
            {**HOST_CONTEXT, "actor_id": "ümlaut"},
            {**HOST_CONTEXT, "runtime_generation": "x" * 129},
            {**HOST_CONTEXT, "scope": ["github.merge_pr", "github.merge_pr"]},
            {**HOST_CONTEXT, "scope": ["Github.merge_pr"]},
            {**HOST_CONTEXT, "scope": ["x" * 129]},
            {**HOST_CONTEXT, "scope": [f"operation.{index}" for index in range(65)]},
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
                    frozen = self.freeze()
                    with self.assertRaises(ActionReviewError):
                        build_review_request(frozen, request_id="review-001", host_context=context)

        with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
            frozen = self.freeze()
            for request_id in ("", "review id", "ümlaut", "x" * 129, True):
                with self.subTest(request_id=request_id):
                    with self.assertRaises(ActionReviewError):
                        build_review_request(frozen, request_id=request_id, host_context=HOST_CONTEXT)

    def test_response_and_request_shapes_are_closed_and_correlated(self) -> None:
        frozen, request = self.issue()
        valid_response = self.response(frozen, request)
        invalid_responses = (
            {**valid_response, "extra": "field"},
            {**valid_response, "decision": "proceed"},
            {**valid_response, "request_id": "review-other"},
            {**valid_response, "request_sha256": "0" * 64},
            {**valid_response, "action_id": "act-other"},
            {**valid_response, "action_sha256": "0" * 64},
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
                    with self.assertRaises(ActionReviewError):
                        validate_review_response(
                            frozen,
                            request,
                            response,
                            current_host_context=HOST_CONTEXT,
                        )

        with self.assertRaises(ContractError):
            validate_contract("authority-action-review-response", {**valid_response, "extra": "field"})

    def test_tampered_and_rehashed_action_or_expiry_does_not_become_expected(self) -> None:
        frozen, request = self.issue()
        for field, value in (
            ("action", {**request["action"], "action_id": "act-tampered"}),
            ("expires_at", "2026-10-05T12:20:00Z"),
        ):
            tampered = copy.deepcopy(request)
            tampered[field] = value
            unsigned = {key: item for key, item in tampered.items() if key != "request_sha256"}
            tampered["request_sha256"] = canonical_json_sha256(unsigned)
            with self.subTest(field=field):
                with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
                    with self.assertRaises(ActionReviewError):
                        validate_review_response(
                            frozen,
                            tampered,
                            self.response(frozen, tampered),
                            current_host_context=HOST_CONTEXT,
                        )

    def test_reconstructed_action_is_not_a_live_issuance(self) -> None:
        frozen, request = self.issue()
        reconstructed = object.__new__(FrozenAction)
        object.__setattr__(reconstructed, "action", frozen.action)
        object.__setattr__(reconstructed, "action_sha256", frozen.action_sha256)
        object.__setattr__(reconstructed, "expires_at", frozen.expires_at)
        with patch("orchestration.lib.action_authority._utc_now", return_value=NOW):
            with self.assertRaises(ActionReviewError):
                validate_review_response(
                    reconstructed,
                    request,
                    self.response(frozen, request),
                    current_host_context=HOST_CONTEXT,
                )

    def test_expiry_rejects_approve_and_reject_and_preserves_core_expiry_error(self) -> None:
        frozen, request = self.issue()
        for decision in ("approve", "reject"):
            with self.subTest(decision=decision):
                with patch(
                    "orchestration.lib.action_authority._utc_now",
                    return_value=NOW + datetime.timedelta(minutes=10),
                ):
                    with self.assertRaises(ExpiredActionError):
                        validate_review_response(
                            frozen,
                            request,
                            self.response(frozen, request, decision),
                            current_host_context=HOST_CONTEXT,
                        )

    def test_repeated_validation_has_no_ledger_or_external_side_effect(self) -> None:
        frozen, request = self.issue()
        response = self.response(frozen, request, "reject")
        with (
            patch("orchestration.lib.action_authority._utc_now", return_value=NOW),
            patch("orchestration.lib.action_authority_ledger.record_action_decision") as record,
            patch("orchestration.lib.action_authority_ledger.consume_action") as consume,
            patch("urllib.request.urlopen") as opener,
        ):
            first = validate_review_response(
                frozen, request, response, current_host_context=HOST_CONTEXT
            )
            second = validate_review_response(
                frozen, request, response, current_host_context=HOST_CONTEXT
            )
        record.assert_not_called()
        consume.assert_not_called()
        opener.assert_not_called()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
