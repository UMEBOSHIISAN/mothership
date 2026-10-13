from __future__ import annotations

import copy
import datetime
import io
import json
from types import MappingProxyType
from urllib.error import HTTPError
import unittest
from unittest import mock

from mothership.contracts import (
    ContractError,
    canonical_json_sha256,
    validate_receipt_verification_binding,
)
from mothership.action_authority import freeze_action


_OBSERVED_AT = "2026-09-27T00:00:10Z"
_RECEIPT_STARTED = "2026-09-27T00:00:01Z"
_RECEIPT_FINISHED = "2026-09-27T00:00:02Z"
_HEAD = "a" * 40
_BASE = "b" * 40
_MERGE = "c" * 40


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, payload: object, *, url: str):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.url = url
        self.headers = {}

    def geturl(self) -> str:
        return self.url


class ReadBackOpener:
    def __init__(self, payloads: list[object]):
        self.payloads = [copy.deepcopy(item) for item in payloads]
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        if not self.payloads:
            raise AssertionError("unexpected third GET")
        payload = self.payloads.pop(0)
        return FakeResponse(payload, url=request.full_url)


class RawOpener:
    def __init__(self, bodies: list[bytes], *, status: int = 200):
        self.bodies = list(bodies)
        self.status = status
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        body = self.bodies.pop(0)
        response = io.BytesIO(body)
        response.status = self.status
        response.headers = {}
        return response


def _action(action_id: str = "act-readback"):
    with mock.patch(
        "orchestration.lib.action_authority._utc_now",
        return_value=datetime.datetime(2026, 9, 27, tzinfo=datetime.UTC),
    ):
        return freeze_action(
            action_id,
            "github.merge_pr",
            {
                "repository": "owner/repo",
                "pull_request": 7,
                "expected_head_sha": _HEAD,
                "expected_base": "main",
                "merge_method": "merge",
            },
        )


def _pr_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "url": "https://api.github.com/repos/owner/repo/pulls/7",
        "number": 7,
        "title": "synthetic title is not retained",
        "state": "closed",
        "closed": True,
        "merged": True,
        "merged_at": "2026-09-27T00:00:05Z",
        "updated_at": "2026-09-27T00:00:06Z",
        "draft": False,
        "head": {"sha": _HEAD, "ref": "feature"},
        "base": {
            "ref": "main",
            "repo": {"full_name": "OWNER/REPO"},
        },
        "merge_commit_sha": _MERGE,
        "body": "secret body must not be retained",
        "user": {"login": "private-user", "email": "private@example.test"},
    }
    payload.update(changes)
    return payload


def _commit_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "sha": _MERGE,
        "url": "https://api.github.com/repos/owner/repo/git/commits/" + _MERGE,
        "parents": [{"sha": _BASE}, {"sha": _HEAD}],
        "commit": {"message": "secret commit message", "author": {"email": "hidden"}},
    }
    payload.update(changes)
    return payload


def _receipt(action) -> dict[str, object]:
    result = {
        "schema_version": "external-action-receipt.v0",
        "action_id": action.action["action_id"],
        "action_sha256": action.action_sha256,
        "executor_ref": {"ref_id": "executor:synthetic", "sha256": "d" * 64},
        "started_at": _RECEIPT_STARTED,
        "finished_at": _RECEIPT_FINISHED,
        "status": "SUCCESS",
        "executor_observation_ref": {
            "ref_id": "observation:synthetic",
            "sha256": "e" * 64,
        },
    }
    return result


def _plain_json(value: object) -> object:
    if isinstance(value, MappingProxyType):
        return {key: _plain_json(item) for key, item in value.items()}
    if type(value) is dict:
        return {key: _plain_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_plain_json(item) for item in value]
    if type(value) is list:
        return [_plain_json(item) for item in value]
    return value


class VerificationProducerTests(unittest.TestCase):
    def import_api(self):
        try:
            from mothership_github.verification import verify_merge_pr
        except ImportError as error:
            self.fail(f"read-back verifier API is missing: {error}")
        return verify_merge_pr

    def import_recorded_api(self):
        try:
            from mothership_github.verification import verify_recorded_merge_pr
        except ImportError as error:
            self.fail(f"recorded read-back verifier API is missing: {error}")
        return verify_recorded_merge_pr

    def test_recorded_action_happy_path_is_caller_attested_and_has_no_effects(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        issued_action = _action()
        recorded_action = _plain_json(issued_action.action)
        receipt = _receipt(issued_action)
        recorded_before = copy.deepcopy(recorded_action)
        receipt_before = copy.deepcopy(receipt)
        opener = ReadBackOpener([_pr_payload(), _commit_payload()])

        with (
            mock.patch(
                "mothership_github.verification.action_authority.freeze_action",
                side_effect=AssertionError("recorded verification must not issue an action"),
            ),
            mock.patch(
                "orchestration.lib.action_authority_ledger.record_action_decision",
                side_effect=AssertionError("recorded verification must not record authority"),
            ),
            mock.patch(
                "orchestration.lib.action_authority_ledger.consume_action",
                side_effect=AssertionError("recorded verification must not consume authority"),
            ),
            mock.patch(
                "mothership_github.executor.execute_action_merge_pr",
                side_effect=AssertionError("recorded verification must not execute an action"),
            ),
            mock.patch(
                "mothership_github.verification._utc_now",
                return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
            ),
        ):
            result = verify_recorded_merge_pr(recorded_action, receipt, opener=opener)

        self.assertEqual("CONFIRMED", result["verification"]["status"])
        self.assertEqual(2, len(opener.requests))
        self.assertEqual(recorded_before, recorded_action)
        self.assertEqual(receipt_before, receipt)
        summary = result["verification"]["observed_state"]["summary"]
        self.assertIn("status=CONFIRMED; reason=merge_confirmed;", summary)
        self.assertLessEqual(len(summary), 256)
        self.assertFalse(any(request.has_header("Authorization") for request, _ in opener.requests))

    def test_recorded_action_validation_and_strict_api_reject_before_network(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        verify_merge_pr = self.import_api()
        issued_action = _action()
        recorded_action = _plain_json(issued_action.action)
        receipt = _receipt(issued_action)

        malformed = copy.deepcopy(recorded_action)
        malformed.pop("display")
        cyclic = copy.deepcopy(recorded_action)
        cyclic["display"]["cycle"] = cyclic

        class HostileDict(dict):
            def items(self):
                raise AssertionError("hostile action hook must not run")

        hostile = copy.deepcopy(recorded_action)
        hostile["display"] = HostileDict(hostile["display"])
        tuple_action = copy.deepcopy(recorded_action)
        tuple_action["display"]["excluded_operations"] = tuple(
            tuple_action["display"]["excluded_operations"]
        )
        foreign_action = _plain_json(_action("act-foreign").action)
        cases = (
            (object(), receipt),
            (malformed, receipt),
            (cyclic, receipt),
            (hostile, receipt),
            (tuple_action, receipt),
            (MappingProxyType(recorded_action), receipt),
            (recorded_action, {**receipt, "action_sha256": "f" * 64}),
            (foreign_action, receipt),
        )
        for candidate_action, candidate_receipt in cases:
            with self.subTest(action_type=type(candidate_action).__name__):
                opener = ReadBackOpener([])
                with self.assertRaises(ContractError) as raised:
                    verify_recorded_merge_pr(candidate_action, candidate_receipt, opener=opener)
                self.assertEqual("invalid GitHub read-back verification input", str(raised.exception))
                self.assertEqual([], opener.requests)

        strict_opener = ReadBackOpener([])
        with self.assertRaises(ContractError):
            verify_merge_pr(recorded_action, receipt, opener=strict_opener)
        self.assertEqual([], strict_opener.requests)

    def test_recorded_plain_json_bounds_reject_before_copy_or_network(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        issued_action = _action("act-bounded-recorded")
        recorded_action = _plain_json(issued_action.action)
        receipt = _receipt(issued_action)

        oversized_issued = _action("act-" + "x" * 300_000)
        oversized_action = _plain_json(oversized_issued.action)
        oversized_action_receipt = _receipt(oversized_issued)
        oversized_receipt = copy.deepcopy(receipt)

        deep_action = copy.deepcopy(recorded_action)
        nested: object = "x"
        for _ in range(24):
            nested = [nested]
        deep_action["display"]["nested"] = nested

        container_action = copy.deepcopy(recorded_action)
        container_action["display"]["entries"] = ["x"] * 1_025

        nodes_action = copy.deepcopy(recorded_action)
        nodes_action["display"]["entries"] = [["x"] * 1_000 for _ in range(9)]

        total_bytes_action = copy.deepcopy(recorded_action)
        total_bytes_action["display"]["entries"] = ["x" * 65_536] * 5

        utf8_bytes_action = copy.deepcopy(recorded_action)
        utf8_bytes_action["display"]["utf8"] = "é" * 40_000

        escaped_bytes_action = copy.deepcopy(recorded_action)
        escaped_bytes_action["display"]["escaped"] = "\x00" * 50_000

        cyclic_action = copy.deepcopy(recorded_action)
        cyclic_action["display"]["cycle"] = cyclic_action

        class HostileDict(dict):
            def items(self):
                raise AssertionError("bounded validation must reject custom mappings first")

        custom_action = copy.deepcopy(recorded_action)
        custom_action["display"] = HostileDict(custom_action["display"])
        tuple_action = copy.deepcopy(recorded_action)
        tuple_action["display"]["tuple"] = ("x",)

        oversized_receipt["unexpected"] = "x" * 300_000
        tuple_receipt = copy.deepcopy(receipt)
        tuple_receipt["executor_ref"] = ("ref_id", "sha256")

        cases = (
            ("oversized_action", oversized_action, oversized_action_receipt),
            ("oversized_receipt", recorded_action, oversized_receipt),
            ("depth", deep_action, receipt),
            ("container_entries", container_action, receipt),
            ("node_count", nodes_action, receipt),
            ("total_bytes", total_bytes_action, receipt),
            ("string_utf8_bytes", utf8_bytes_action, receipt),
            ("escaped_total_bytes", escaped_bytes_action, receipt),
            ("cycle", cyclic_action, receipt),
            ("custom_mapping", custom_action, receipt),
            ("tuple", tuple_action, receipt),
            ("tuple_receipt", recorded_action, tuple_receipt),
        )
        for name, candidate_action, candidate_receipt in cases:
            with self.subTest(case=name):
                opener = ReadBackOpener([])
                snapshot_path = (
                    "mothership_github.verification._snapshot_receipt"
                    if name in {"oversized_receipt", "tuple_receipt"}
                    else "mothership_github.verification._snapshot"
                )
                with mock.patch(
                    snapshot_path,
                    side_effect=AssertionError("bounded input must fail before snapshot"),
                ):
                    with self.assertRaises(ContractError) as raised:
                        verify_recorded_merge_pr(
                            candidate_action, candidate_receipt, opener=opener
                        )
                self.assertEqual(
                    "invalid GitHub read-back verification input", str(raised.exception)
                )
                self.assertEqual([], opener.requests)

    def test_recorded_plain_json_bounds_keep_normal_and_300_char_ids_compatible(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        for action_id in ("act-bounded-normal", "act-" + "x" * 300):
            with self.subTest(action_id_length=len(action_id)):
                issued_action = _action(action_id)
                recorded_action = _plain_json(issued_action.action)
                receipt = _receipt(issued_action)
                opener = ReadBackOpener([_pr_payload(), _commit_payload()])
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_recorded_merge_pr(
                        recorded_action, receipt, opener=opener
                    )
                self.assertEqual("CONFIRMED", result["verification"]["status"])
                self.assertEqual(2, len(opener.requests))

    def test_recorded_canonical_byte_budget_includes_empty_strings_and_escapes(self):
        from mothership_github import verification

        for value in ("", [""], {"": ""}, {"empty": "", "escaped": "\x00\n\\\"", "utf8": "é漢"}):
            size = len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            with self.subTest(value=value):
                with mock.patch.object(verification, "_MAX_ENCODED_BYTES", size):
                    verification._validate_recorded_plain(value)
                with mock.patch.object(verification, "_MAX_ENCODED_BYTES", size - 1):
                    with self.assertRaisesRegex(ContractError, "^invalid GitHub read-back verification input$"):
                        verification._validate_recorded_plain(value)

    def test_recorded_action_summary_has_fixed_reason_and_explanation_for_each_status(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        cases = (
            (
                "confirmed",
                [_pr_payload(body="remote secret"), _commit_payload()],
                "CONFIRMED",
                "merge_confirmed",
            ),
            (
                "mismatch",
                [_pr_payload(head={"sha": "f" * 40, "ref": "feature"})],
                "MISMATCH",
                "head_or_base_mismatch",
            ),
            (
                "unknown",
                [_pr_payload(state="open", closed=False, merged=False, merged_at=None, merge_commit_sha=None)],
                "UNKNOWN",
                "unmerged_pr",
            ),
        )
        for name, payloads, expected_status, expected_reason in cases:
            with self.subTest(status=name):
                issued_action = _action("act-summary-" + name)
                recorded_action = _plain_json(issued_action.action)
                receipt = _receipt(issued_action)
                opener = ReadBackOpener(payloads)
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_recorded_merge_pr(recorded_action, receipt, opener=opener)
                summary = result["verification"]["observed_state"]["summary"]
                self.assertEqual(expected_status, result["verification"]["status"])
                self.assertIn(f"status={expected_status}; reason={expected_reason};", summary)
                self.assertLessEqual(len(summary), 256)
                self.assertNotIn("remote secret", summary)
                self.assertNotIn("synthetic title", summary)

    def test_recorded_action_preserves_receipt_status_and_same_second_timing(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        for receipt_status in ("SUCCESS", "FAILED", "UNKNOWN"):
            with self.subTest(receipt_status=receipt_status):
                issued_action = _action("act-status-recorded-" + receipt_status.lower())
                recorded_action = _plain_json(issued_action.action)
                receipt = _receipt(issued_action)
                receipt["status"] = receipt_status
                before = copy.deepcopy(receipt)
                opener = ReadBackOpener([_pr_payload(), _commit_payload()])
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_recorded_merge_pr(recorded_action, receipt, opener=opener)
                self.assertEqual("CONFIRMED", result["verification"]["status"])
                self.assertEqual(before, receipt)

        issued_action = _action("act-recorded-same-second")
        recorded_action = _plain_json(issued_action.action)
        receipt = _receipt(issued_action)
        opener = ReadBackOpener([_pr_payload(merged_at=_RECEIPT_STARTED)])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_recorded_merge_pr(recorded_action, receipt, opener=opener)
        self.assertEqual("UNKNOWN", result["verification"]["status"])
        self.assertEqual("ambiguous_merge_time", result["evidence"]["reason"])
        self.assertEqual(1, len(opener.requests))

    def test_recorded_action_sanitizes_transport_exception_text(self):
        verify_recorded_merge_pr = self.import_recorded_api()
        issued_action = _action("act-recorded-exception")
        recorded_action = _plain_json(issued_action.action)
        receipt = _receipt(issued_action)

        def failing_opener(request, *, timeout):
            raise RuntimeError("private remote exception must not leak")

        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_recorded_merge_pr(recorded_action, receipt, opener=failing_opener)
        encoded = json.dumps(result, sort_keys=True)
        self.assertEqual("UNKNOWN", result["verification"]["status"])
        self.assertEqual("invalid_pr_observation", result["evidence"]["reason"])
        self.assertNotIn("private remote exception", encoded)
        self.assertNotIn("RuntimeError", encoded)

    def test_happy_path_binds_exact_action_and_receipt_with_two_gets(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(), _commit_payload()])

        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            bundle = verify_merge_pr(action, receipt, opener=opener)

        self.assertEqual({"verification", "evidence"}, set(bundle))
        self.assertEqual("CONFIRMED", bundle["verification"]["status"])
        self.assertEqual("github-merge-readback.v0", bundle["evidence"]["version"])
        self.assertEqual("injected", bundle["evidence"]["transport"])
        self.assertEqual(_OBSERVED_AT, bundle["verification"]["observed_at"])
        self.assertEqual(
            {"repository", "number", "state", "merged", "merged_at", "head_sha", "base_ref", "merge_commit_sha"},
            set(bundle["evidence"]["state"]["pull_request"]),
        )
        self.assertEqual({"sha", "parents"}, set(bundle["evidence"]["state"]["commit"]))
        self.assertEqual(
            canonical_json_sha256(bundle["evidence"]["state"]),
            bundle["verification"]["observed_state"]["state_sha256"],
        )
        evidence_sha = canonical_json_sha256(bundle["evidence"])
        self.assertEqual("github-readback:" + evidence_sha, bundle["verification"]["evidence_refs"][0]["ref_id"])
        self.assertEqual(evidence_sha, bundle["verification"]["evidence_refs"][0]["sha256"])
        self.assertEqual(
            canonical_json_sha256(receipt), bundle["verification"]["receipt_ref"]["sha256"]
        )
        self.assertEqual("receipt:act-readback", bundle["verification"]["receipt_ref"]["ref_id"])
        self.assertEqual("owner/repo", bundle["evidence"]["state"]["pull_request"]["repository"])
        self.assertNotIn("title", json.dumps(bundle, sort_keys=True))
        self.assertNotIn("private@example.test", json.dumps(bundle, sort_keys=True))

        validated_receipt, validated_verification = validate_receipt_verification_binding(
            receipt,
            bundle["verification"],
            expected_action_id="act-readback",
            expected_action_sha256=action.action_sha256,
        )
        self.assertEqual(receipt, validated_receipt)
        self.assertEqual(bundle["verification"], validated_verification)
        self.assertEqual(2, len(opener.requests))
        self.assertEqual(
            [
                "https://api.github.com/repos/owner/repo/pulls/7",
                "https://api.github.com/repos/owner/repo/git/commits/" + _MERGE,
            ],
            [request.full_url for request, _ in opener.requests],
        )
        self.assertFalse(any(request.has_header("Authorization") for request, _ in opener.requests))

    def test_long_action_id_does_not_change_evidence_reference_or_fail_schema(self):
        verify_merge_pr = self.import_api()
        action_id = "act-" + "x" * 300
        action = _action(action_id)
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(), _commit_payload()])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual(action_id, result["verification"]["action_id"])
        self.assertEqual("github-readback:" + canonical_json_sha256(result["evidence"]), result["verification"]["evidence_refs"][0]["ref_id"])

    def test_invalid_input_raises_fixed_contract_error_without_network(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        invalid_receipt = copy.deepcopy(receipt)
        invalid_receipt.pop("started_at")
        cases = (
            (object(), receipt),
            (action, {}),
            (action, invalid_receipt),
            (action, {**receipt, "action_id": 7}),
        )
        for frozen_action, candidate_receipt in cases:
            with self.subTest(candidate_receipt=candidate_receipt):
                opener = ReadBackOpener([])
                with self.assertRaises(ContractError) as raised:
                    verify_merge_pr(frozen_action, candidate_receipt, opener=opener)
                self.assertEqual("invalid GitHub read-back verification input", str(raised.exception))
                self.assertEqual([], opener.requests)
        with self.assertRaises(ContractError) as raised:
            verify_merge_pr(action, receipt, opener=object())
        self.assertEqual("invalid GitHub read-back verification input", str(raised.exception))

    def test_unmerged_observation_is_unknown_after_one_get(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        payload = _pr_payload(state="open", closed=False, merged=False, merged_at=None, merge_commit_sha=None)
        opener = ReadBackOpener([payload])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("UNKNOWN", result["verification"]["status"])
        self.assertIsNotNone(result["evidence"]["state"]["pull_request"])
        self.assertIsNone(result["evidence"]["state"]["commit"])
        self.assertEqual(1, len(opener.requests))

    def test_real_github_pr_shape_without_closed_boolean_is_accepted(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        payload = _pr_payload()
        payload.pop("closed")
        opener = ReadBackOpener([payload, _commit_payload()])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("CONFIRMED", result["verification"]["status"])
        self.assertEqual(2, len(opener.requests))

    def test_pr_identity_types_and_target_mismatch_are_classified_before_commit_get(self):
        verify_merge_pr = self.import_api()
        cases = (
            ("bool_number", {"number": True}, "UNKNOWN", "invalid_pr_observation"),
            ("string_number", {"number": "7"}, "UNKNOWN", "invalid_pr_observation"),
            ("missing_merged", {"_remove": "merged"}, "UNKNOWN", "invalid_pr_observation"),
            ("false_looking_merged", {"merged": "true"}, "UNKNOWN", "invalid_pr_observation"),
            (
                "wrong_base",
                {"base": {"ref": "develop", "repo": {"full_name": "owner/repo"}}},
                "MISMATCH",
                "head_or_base_mismatch",
            ),
        )
        for name, mutation, expected_status, expected_reason in cases:
            with self.subTest(case=name):
                action = _action("act-pr-types-" + name)
                receipt = _receipt(action)
                payload = _pr_payload()
                if mutation.get("_remove") is not None:
                    payload.pop(mutation["_remove"])
                else:
                    payload.update(mutation)
                opener = ReadBackOpener([payload])
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual(expected_status, result["verification"]["status"])
                self.assertEqual(expected_reason, result["evidence"]["reason"])
                self.assertEqual(1, len(opener.requests))

    def test_wrong_head_or_base_is_mismatch_without_commit_get(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(head={"sha": "f" * 40, "ref": "feature"})])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("MISMATCH", result["verification"]["status"])
        self.assertEqual("head_or_base_mismatch", result["evidence"]["reason"])
        self.assertEqual(1, len(opener.requests))

    def test_wrong_resource_identity_and_internal_pr_contradiction_are_unknown(self):
        verify_merge_pr = self.import_api()
        cases = (
            (_pr_payload(url="https://api.github.com/repos/other/repo/pulls/7"), "pr_identity_mismatch"),
            (_pr_payload(base={"ref": "main", "repo": {"full_name": "other/repo"}}), "pr_identity_mismatch"),
            (_pr_payload(state="open", merged=True, merged_at="2026-09-27T00:00:05Z"), "contradictory_pr_state"),
            (_pr_payload(merged=True, merged_at="2026-09-27T00:00:11Z"), "future_merged_at"),
        )
        for payload, expected_reason in cases:
            with self.subTest(expected_reason=expected_reason):
                action = _action("act-pr-" + expected_reason)
                receipt = _receipt(action)
                opener = ReadBackOpener([payload])
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual("UNKNOWN", result["verification"]["status"])
                self.assertEqual(expected_reason, result["evidence"]["reason"])
                self.assertEqual(1, len(opener.requests))

    def test_preexisting_merge_is_unknown_and_does_not_fetch_commit(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(merged_at="2026-09-27T00:00:00Z")])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("UNKNOWN", result["verification"]["status"])
        self.assertEqual("preexisting_merge", result["evidence"]["reason"])
        self.assertIsNone(result["evidence"]["state"]["pull_request"])
        self.assertEqual(1, len(opener.requests))

    def test_merge_time_before_equal_and_after_receipt_start_has_distinct_boundaries(self):
        verify_merge_pr = self.import_api()
        cases = (
            ("before", "2026-09-27T00:00:00Z", "UNKNOWN", "preexisting_merge", 1),
            ("equal", _RECEIPT_STARTED, "UNKNOWN", "ambiguous_merge_time", 1),
            ("after", "2026-09-27T00:00:05Z", "CONFIRMED", "merge_confirmed", 2),
        )
        for name, merged_at, expected_status, expected_reason, expected_gets in cases:
            with self.subTest(boundary=name):
                action = _action("act-merge-time-" + name)
                receipt = _receipt(action)
                opener = ReadBackOpener(
                    [_pr_payload(merged_at=merged_at), _commit_payload()]
                )
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual(expected_status, result["verification"]["status"])
                self.assertEqual(expected_reason, result["evidence"]["reason"])
                self.assertEqual(expected_gets, len(opener.requests))

    def test_parent_topology_mismatch_is_distinct_from_malformed_parent_data(self):
        verify_merge_pr = self.import_api()
        for parents, expected_status, expected_reason in (
            ([], "MISMATCH", "merge_topology_mismatch"),
            ([{"sha": _BASE}], "MISMATCH", "merge_topology_mismatch"),
            ([{"sha": _BASE}, {"sha": "d" * 40}], "MISMATCH", "merge_topology_mismatch"),
            ([{"sha": _BASE}, {"sha": _HEAD}, {"sha": "d" * 40}], "MISMATCH", "merge_topology_mismatch"),
            ([{"sha": _BASE}, {"sha": _HEAD}, {"sha": _HEAD}], "UNKNOWN", "duplicate_parent_sha"),
            ([{"sha": _BASE}, {"sha": _BASE}], "UNKNOWN", "duplicate_parent_sha"),
            ([{"sha": _BASE}, {"sha": "not-a-sha"}], "UNKNOWN", "invalid_parent_shape"),
        ):
            with self.subTest(parents=parents):
                action = _action("act-parent-" + str(len(parents)))
                receipt = _receipt(action)
                opener = ReadBackOpener([_pr_payload(), _commit_payload(parents=parents)])
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual(expected_status, result["verification"]["status"])
                self.assertEqual(expected_reason, result["evidence"]["reason"])
                self.assertEqual(2, len(opener.requests))

    def test_self_parent_commit_is_unknown_for_live_and_recorded_apis(self):
        verify_merge_pr = self.import_api()
        verify_recorded_merge_pr = self.import_recorded_api()
        cases = (
            ([{"sha": _MERGE}, {"sha": _HEAD}], "self_parent_sha"),
            ([{"sha": _BASE}, {"sha": _MERGE}], "self_parent_sha"),
            ([{"sha": _MERGE}, {"sha": _MERGE}], "duplicate_parent_sha"),
        )
        for api_name, verifier in (("live", verify_merge_pr), ("recorded", verify_recorded_merge_pr)):
            for parents, reason in cases:
                with self.subTest(api=api_name, parents=parents):
                    issued_action = _action("act-self-parent-" + api_name)
                    candidate_action = issued_action if api_name == "live" else _plain_json(issued_action.action)
                    receipt = _receipt(issued_action)
                    opener = ReadBackOpener([_pr_payload(), _commit_payload(parents=parents)])
                    with mock.patch(
                        "mothership_github.verification._utc_now",
                        return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                    ):
                        result = verifier(candidate_action, receipt, opener=opener)
                    self.assertEqual("UNKNOWN", result["verification"]["status"])
                    self.assertEqual(reason, result["evidence"]["reason"])
                    self.assertEqual(2, len(opener.requests))

    def test_commit_identity_parent_shape_and_order_edges_are_classified(self):
        verify_merge_pr = self.import_api()
        cases = (
            ("wrong_sha", {"sha": _BASE}, "UNKNOWN", "commit_identity_mismatch"),
            ("parents_mapping", {"parents": {}}, "UNKNOWN", "invalid_parent_shape"),
            ("parent_non_dict", {"parents": [{"sha": _BASE}, []]}, "UNKNOWN", "invalid_parent_shape"),
            (
                "switched_parent_order",
                {"parents": [{"sha": _HEAD}, {"sha": _BASE}]},
                "MISMATCH",
                "merge_topology_mismatch",
            ),
        )
        for name, mutation, expected_status, expected_reason in cases:
            with self.subTest(case=name):
                action = _action("act-commit-edges-" + name)
                receipt = _receipt(action)
                opener = ReadBackOpener([_pr_payload(), _commit_payload(**mutation)])
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual(expected_status, result["verification"]["status"])
                self.assertEqual(expected_reason, result["evidence"]["reason"])
                self.assertEqual(2, len(opener.requests))

    def test_commit_get_failure_keeps_valid_pr_projection_and_is_unknown(self):
        verify_merge_pr = self.import_api()

        class FailingCommitOpener:
            def __init__(self, failure):
                self.failure = failure
                self.requests = []

            def __call__(self, request, *, timeout):
                self.requests.append((request, timeout))
                if len(self.requests) == 1:
                    return FakeResponse(_pr_payload(), url=request.full_url)
                raise self.failure

        for name, failure in (
            ("timeout", TimeoutError("private timeout text")),
            ("http_failure", HTTPError("https://api.github.com", 503, "private error text", {}, None)),
        ):
            with self.subTest(failure=name):
                action = _action("act-commit-failure-" + name)
                receipt = _receipt(action)
                opener = FailingCommitOpener(failure)
                with mock.patch(
                    "mothership_github.verification._utc_now",
                    return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual("UNKNOWN", result["verification"]["status"])
                self.assertEqual("invalid_commit_observation", result["evidence"]["reason"])
                self.assertIsNotNone(result["evidence"]["state"]["pull_request"])
                self.assertIsNone(result["evidence"]["state"]["commit"])
                self.assertEqual(2, len(opener.requests))

    def test_receipt_status_is_independent_from_each_verification_status(self):
        verify_merge_pr = self.import_api()
        observations = (
            ("confirmed", [_pr_payload(), _commit_payload()], "CONFIRMED"),
            ("mismatch", [_pr_payload(head={"sha": "f" * 40, "ref": "feature"})], "MISMATCH"),
            ("unknown", [_pr_payload(state="open", closed=False, merged=False, merged_at=None, merge_commit_sha=None)], "UNKNOWN"),
        )
        for receipt_status in ("SUCCESS", "FAILED", "UNKNOWN"):
            for observation_name, payloads, expected_status in observations:
                with self.subTest(receipt_status=receipt_status, observation=observation_name):
                    action = _action("act-status-" + receipt_status.lower() + "-" + observation_name)
                    receipt = _receipt(action)
                    receipt["status"] = receipt_status
                    before = copy.deepcopy(receipt)
                    opener = ReadBackOpener(payloads)
                    with mock.patch(
                        "mothership_github.verification._utc_now",
                        return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                    ):
                        result = verify_merge_pr(action, receipt, opener=opener)
                    self.assertEqual(expected_status, result["verification"]["status"])
                    self.assertEqual(before, receipt)

    def test_future_receipt_finish_returns_unknown_without_a_get(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        receipt["finished_at"] = "2999-01-01T00:00:00Z"
        opener = ReadBackOpener([])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("UNKNOWN", result["verification"]["status"])
        self.assertEqual("receipt_not_finished", result["evidence"]["reason"])
        self.assertEqual([], opener.requests)

    def test_expired_core_action_can_still_be_read_back(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(), _commit_payload()])
        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 28, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("CONFIRMED", result["verification"]["status"])
        self.assertEqual(2, len(opener.requests))

    def test_default_transport_failures_are_unknown_without_retry_or_auth(self):
        verify_merge_pr = self.import_api()

        def non_200(request, *, timeout):
            response = FakeResponse({}, url=request.full_url)
            response.status = 503
            return response

        def timeout(request, *, timeout):
            raise TimeoutError("synthetic timeout text")

        def redirect(request, *, timeout):
            raise HTTPError(request.full_url, 302, "synthetic redirect text", {}, None)

        for name, default_open in (("non_200", non_200), ("timeout", timeout), ("redirect", redirect)):
            with self.subTest(failure=name):
                action = _action("act-default-" + name)
                receipt = _receipt(action)
                calls = []

                def traced_open(request, *, timeout, default_open=default_open):
                    calls.append(request)
                    return default_open(request, timeout=timeout)

                with (
                    mock.patch("mothership_github.public_observation._default_open", side_effect=traced_open),
                    mock.patch(
                        "mothership_github.verification._utc_now",
                        return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                    ),
                ):
                    result = verify_merge_pr(action, receipt)
                self.assertEqual("UNKNOWN", result["verification"]["status"])
                self.assertEqual("default_tokenless", result["evidence"]["transport"])
                self.assertEqual(1, len(calls))
                self.assertFalse(calls[0].has_header("Authorization"))

    def test_clock_rollback_during_or_between_gets_stays_unknown(self):
        verify_merge_pr = self.import_api()
        cases = (
            (
                "during_pr_get",
                [_pr_payload()],
                [10, 11, 10, 11],
                1,
            ),
            (
                "between_gets",
                [_pr_payload(), _commit_payload()],
                [10, 11, 12, 11, 13, 14],
                2,
            ),
        )
        for name, payloads, seconds, expected_gets in cases:
            with self.subTest(rollback=name):
                action = _action("act-rollback-" + name)
                receipt = _receipt(action)
                opener = ReadBackOpener(payloads)
                times = iter(
                    datetime.datetime(2026, 9, 27, 0, 0, second, tzinfo=datetime.UTC)
                    for second in seconds
                )
                with mock.patch("mothership_github.verification._utc_now", side_effect=times):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual("UNKNOWN", result["verification"]["status"])
                self.assertEqual("clock_rollback", result["evidence"]["reason"])
                self.assertEqual(expected_gets, len(opener.requests))

    def test_readback_does_not_call_authority_ledger_or_executor_paths(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(), _commit_payload()])
        with (
            mock.patch(
                "orchestration.lib.action_authority_ledger.record_action_decision",
                side_effect=AssertionError("read-back must not record authority"),
            ),
            mock.patch(
                "orchestration.lib.action_authority_ledger.consume_action",
                side_effect=AssertionError("read-back must not consume authority"),
            ),
            mock.patch(
                "mothership_github.executor.execute_action_merge_pr",
                side_effect=AssertionError("read-back must not execute an action"),
            ),
            mock.patch(
                "mothership_github.verification._utc_now",
                return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
            ),
        ):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("CONFIRMED", result["verification"]["status"])

    def test_final_clock_rollback_downgrades_a_conclusive_readback(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([_pr_payload(), _commit_payload()])
        times = iter(
            [
                datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                datetime.datetime(2026, 9, 27, 0, 0, 11, tzinfo=datetime.UTC),
                datetime.datetime(2026, 9, 27, 0, 0, 12, tzinfo=datetime.UTC),
                datetime.datetime(2026, 9, 27, 0, 0, 13, tzinfo=datetime.UTC),
                datetime.datetime(2026, 9, 27, 0, 0, 14, tzinfo=datetime.UTC),
                datetime.datetime(2026, 9, 27, 0, 0, 9, tzinfo=datetime.UTC),
            ]
        )
        with mock.patch("mothership_github.verification._utc_now", side_effect=times):
            result = verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual("UNKNOWN", result["verification"]["status"])
        self.assertEqual("clock_rollback", result["evidence"]["reason"])

    def test_invalid_receipt_calendar_and_binding_fail_before_network(self):
        verify_merge_pr = self.import_api()
        action = _action()
        for mutation in (
            {"started_at": "2026-02-30T00:00:00Z"},
            {"started_at": "2026-09-27T00:00:03Z"},
            {"action_sha256": "f" * 64},
        ):
            receipt = _receipt(action)
            receipt.update(mutation)
            opener = ReadBackOpener([])
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                verify_merge_pr(action, receipt, opener=opener)
            self.assertEqual([], opener.requests)

    def test_proxy_wrapped_custom_receipt_is_rejected_before_items_hook_or_network(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        hook_called = []

        class HostileReceipt(dict):
            def items(self):
                hook_called.append(True)
                raise RuntimeError("receipt items hook must not run")

        wrapped = MappingProxyType(HostileReceipt(receipt))
        opener = ReadBackOpener([])
        with self.assertRaises(ContractError) as raised:
            verify_merge_pr(action, wrapped, opener=opener)
        self.assertEqual("invalid GitHub read-back verification input", str(raised.exception))
        self.assertEqual([], hook_called)
        self.assertEqual([], opener.requests)

    def test_cyclic_or_custom_nested_receipt_is_rejected_before_hooks_or_network(self):
        verify_merge_pr = self.import_api()
        action = _action()

        cyclic = _receipt(action)
        cyclic["cycle"] = cyclic
        custom_hook_called = []

        class HostileNested(dict):
            def items(self):
                custom_hook_called.append(True)
                raise RuntimeError("nested receipt items hook must not run")

        custom_nested = _receipt(action)
        custom_nested["executor_ref"] = HostileNested(custom_nested["executor_ref"])
        for name, candidate in (("cyclic", cyclic), ("custom_nested", custom_nested)):
            with self.subTest(receipt=name):
                opener = ReadBackOpener([])
                with self.assertRaises(ContractError) as raised:
                    verify_merge_pr(action, candidate, opener=opener)
                self.assertEqual("invalid GitHub read-back verification input", str(raised.exception))
                self.assertEqual([], opener.requests)
        self.assertEqual([], custom_hook_called)

    def test_receipt_is_snapshotted_before_opener_can_mutate_original(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        before = copy.deepcopy(receipt)
        requests = []
        responses = [_pr_payload(), _commit_payload()]

        def mutating_opener(request, *, timeout):
            requests.append((request, timeout))
            receipt["status"] = "FAILED"
            receipt["executor_ref"]["sha256"] = "f" * 64
            return FakeResponse(responses.pop(0), url=request.full_url)

        with mock.patch(
            "mothership_github.verification._utc_now",
            return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
        ):
            result = verify_merge_pr(action, receipt, opener=mutating_opener)
        self.assertEqual("CONFIRMED", result["verification"]["status"])
        self.assertEqual(canonical_json_sha256(before), result["verification"]["receipt_ref"]["sha256"])
        self.assertEqual("FAILED", receipt["status"])
        self.assertEqual("f" * 64, receipt["executor_ref"]["sha256"])
        self.assertEqual(2, len(requests))

    def test_subclassed_or_tampered_frozen_action_is_rejected_without_network(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        opener = ReadBackOpener([])

        class FakeFrozen(type(action)):
            pass

        forged = object.__new__(FakeFrozen)
        with self.assertRaises(ContractError):
            verify_merge_pr(forged, receipt, opener=opener)
        self.assertEqual([], opener.requests)

        object.__setattr__(action, "action_sha256", "f" * 64)
        with self.assertRaises(ContractError):
            verify_merge_pr(action, receipt, opener=opener)
        self.assertEqual([], opener.requests)

    def test_default_tokenless_transport_uses_existing_opener_seam(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)
        calls = []
        responses = [_pr_payload(), _commit_payload()]

        def default_open(request, *, timeout):
            calls.append((request, timeout))
            return FakeResponse(responses.pop(0), url=request.full_url)

        with (
            mock.patch("mothership_github.public_observation._default_open", side_effect=default_open),
            mock.patch(
                "mothership_github.verification._utc_now",
                return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
            ),
        ):
            result = verify_merge_pr(action, receipt)
        self.assertEqual("CONFIRMED", result["verification"]["status"])
        self.assertEqual(2, len(calls))
        self.assertFalse(any(request.has_header("Authorization") for request, _ in calls))

    def test_falsey_injected_opener_is_used_for_both_gets(self):
        verify_merge_pr = self.import_api()
        action = _action()
        receipt = _receipt(action)

        class BoolFalseOpener:
            def __init__(self):
                self.payloads = [_pr_payload(), _commit_payload()]
                self.requests = []

            def __bool__(self):
                return False

            def __call__(self, request, *, timeout):
                self.requests.append((request, timeout))
                return FakeResponse(self.payloads.pop(0), url=request.full_url)

        class LenZeroOpener:
            def __init__(self):
                self.payloads = [_pr_payload(), _commit_payload()]
                self.requests = []

            def __len__(self):
                return 0

            def __call__(self, request, *, timeout):
                self.requests.append((request, timeout))
                return FakeResponse(self.payloads.pop(0), url=request.full_url)

        for opener_type in (BoolFalseOpener, LenZeroOpener):
            with self.subTest(opener=opener_type.__name__):
                opener = opener_type()
                default_open = mock.Mock(
                    side_effect=AssertionError("falsey injected opener was discarded")
                )
                with (
                    mock.patch(
                        "mothership_github.public_observation._default_open",
                        default_open,
                    ),
                    mock.patch(
                        "mothership_github.verification._utc_now",
                        return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
                    ),
                ):
                    result = verify_merge_pr(action, receipt, opener=opener)
                self.assertEqual("CONFIRMED", result["verification"]["status"])
                self.assertEqual("injected", result["evidence"]["transport"])
                self.assertEqual(2, len(opener.requests))
                self.assertTrue(all(request.get_method() == "GET" for request, _ in opener.requests))
                default_open.assert_not_called()

    def test_timeout_and_malformed_or_duplicate_json_are_unknown_without_retry(self):
        verify_merge_pr = self.import_api()
        for opener in (
            ReadBackOpener([]),
            None,
        ):
            action = _action("act-transport-" + str(id(opener)))
            receipt = _receipt(action)
            if opener is None:
                def timeout_open(request, *, timeout):
                    raise TimeoutError("private timeout text")
                current = timeout_open
            else:
                def timeout_open(request, *, timeout):
                    raise TimeoutError("private timeout text")
                current = timeout_open
            with mock.patch(
                "mothership_github.verification._utc_now",
                return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
            ):
                result = verify_merge_pr(action, receipt, opener=current)
            self.assertEqual("UNKNOWN", result["verification"]["status"])
            self.assertEqual(1, len(result["evidence"]["observations"]))

        for body in (
            b'{"number":7,"number":7}',
            b"x" * (1024 * 1024 + 1),
        ):
            action = _action("act-malformed-" + str(len(body)))
            receipt = _receipt(action)
            opener = RawOpener([body])
            with mock.patch(
                "mothership_github.verification._utc_now",
                return_value=datetime.datetime(2026, 9, 27, 0, 0, 10, tzinfo=datetime.UTC),
            ):
                result = verify_merge_pr(action, receipt, opener=opener)
            self.assertEqual("UNKNOWN", result["verification"]["status"])
            self.assertEqual(1, len(opener.requests))


class ObservationCommitTests(unittest.TestCase):
    def test_commit_request_rejects_invalid_sha_before_network(self):
        from mothership_github.observation import GitHubObservationAdapter

        calls = []

        def opener(request, *, timeout):
            calls.append(request)
            raise AssertionError("network must not be used")

        adapter = GitHubObservationAdapter(opener=opener)
        for sha in ("A" * 40, "a" * 39, "a" * 41, "not-a-sha"):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                adapter.fetch_commit("owner/repo", sha)
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
