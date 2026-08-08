from __future__ import annotations

import json
from pathlib import Path
import unittest

from orchestration.lib.contracts import validate_contract
from safety.policy import assess


REASONS = {
    "invalid_mode",
    "invalid_call_depth",
    "unsupported_risk_class",
    "elevated_risk_execute_blocked",
    "elevated_risk_human_review",
    "mutation_not_none",
    "missing_selected_alias_for_execute",
    "call_depth_exceeds_maximum",
    "retry_enabled",
    "fallback_enabled",
    "max_attempts_not_one",
    "missing_scope_for_execute",
    "read_only_capability_required",
    "no_authority_effect",
}
DEFAULT_TASK = object()


def safe_task(**extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": "task-1",
        "invocation_id": "invoke-1",
        "risk_class": "low",
        "mutation_class": "none",
        "required_capabilities": ["read-only"],
        "max_attempts": 1,
        "retry": {"enabled": False},
        "fallback": {"enabled": False},
        "max_call_depth": 1,
    }
    value.update(extra)
    return value


class SafetyTests(unittest.TestCase):
    def output(
        self,
        task_value: object = DEFAULT_TASK,
        mode: object = "dry-run",
        alias: object = None,
        depth: object = 0,
        scope: object = None,
    ) -> dict[str, object]:
        selected = safe_task() if task_value is DEFAULT_TASK else task_value
        return assess(selected, mode, alias, depth, scope)  # type: ignore[arg-type]

    def assert_closed(self, result: dict[str, object]) -> None:
        # Returning unrecognized fields, reasons, or authority must make this fail.
        self.assertEqual(
            {
                "schema_version",
                "task_id",
                "invocation_id",
                "classification",
                "reason_codes",
                "authority_effect",
            },
            set(result),
        )
        self.assertEqual("0.1.0", result["schema_version"])
        self.assertIn(result["classification"], {"blocked", "human-review-required", "unclassified"})
        self.assertTrue(result["reason_codes"])
        self.assertTrue(set(result["reason_codes"]) <= REASONS)  # type: ignore[arg-type]
        self.assertEqual(sorted(set(result["reason_codes"])), result["reason_codes"])  # type: ignore[arg-type]
        self.assertEqual("none", result["authority_effect"])
        self.assertEqual(result, validate_contract("assessment", result))
        flattened = repr(result).lower()
        for positive in ("allow", "approved", "authorized"):
            self.assertNotIn(positive, flattened)

    def test_schema_exact_catalog_and_safe_dry_run(self) -> None:
        # Opening the schema or inventing a safe authority must make this fail.
        schema = json.loads(
            (Path(__file__).parents[1] / "safety/contracts/assessment.schema.json").read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(REASONS, set(schema["properties"]["reason_codes"]["items"]["enum"]))
        result = self.output()
        self.assertEqual("unclassified", result["classification"])
        self.assertEqual(["no_authority_effect"], result["reason_codes"])
        self.assert_closed(result)

    def test_literal_none_task_and_malformed_identities_are_total_and_opaque(self) -> None:
        # Reusing the default fixture for explicit None or echoing bad identities must make this fail.
        cases = (
            None,
            [],
            "bad",
            7,
            {"task_id": 1, "invocation_id": []},
            {"task_id": "", "invocation_id": None},
        )
        for value in cases:
            with self.subTest(value=repr(value)):
                result = self.output(value)
                self.assertEqual("blocked", result["classification"])
                self.assert_closed(result)
        result = self.output(None)
        self.assertEqual("invalid-task", result["task_id"])
        self.assertEqual("invalid-invocation", result["invocation_id"])

    def test_every_scalar_and_unhashable_risk_is_total(self) -> None:
        # Letting a malformed risk value reach set membership must make this fail.
        for risk in (None, [], {}, True, False, 0, 1.5, object()):
            with self.subTest(risk=repr(risk)):
                result = self.output(safe_task(risk_class=risk))
                self.assertEqual("blocked", result["classification"])
                self.assertIn("unsupported_risk_class", result["reason_codes"])
                self.assert_closed(result)

    def test_only_malformed_call_depth_is_structural(self) -> None:
        # Treating bool, scalar, or negative call depth as advisory must make this fail.
        for depth in (True, False, None, "0", 1.0, -1):
            with self.subTest(depth=repr(depth)):
                result = self.output(depth=depth)
                self.assertEqual("blocked", result["classification"])
                self.assertIn("invalid_call_depth", result["reason_codes"])
                self.assert_closed(result)
        for mode in (None, "", "bad", 1, True, []):
            with self.subTest(mode=repr(mode)):
                result = self.output(mode=mode)
                self.assertEqual("blocked", result["classification"])
                self.assertIn("invalid_mode", result["reason_codes"])
                self.assert_closed(result)

    def test_over_depth_is_execute_only(self) -> None:
        # Structurally blocking numeric over-depth during dry-run must make this fail.
        for risk, expected in (
            ("low", "unclassified"),
            ("medium", "unclassified"),
            ("high", "human-review-required"),
            ("unknown", "human-review-required"),
        ):
            for depth, maximum in ((2, 1), (1, 0)):
                with self.subTest(risk=risk, depth=depth, maximum=maximum):
                    dry = self.output(safe_task(risk_class=risk, max_call_depth=maximum), depth=depth)
                    self.assertEqual(expected, dry["classification"])
                    self.assertNotIn("call_depth_exceeds_maximum", dry["reason_codes"])
                    self.assert_closed(dry)
        execute = self.output(safe_task(), "execute", "alias", 2, object())
        self.assertEqual("blocked", execute["classification"])
        self.assertIn("call_depth_exceeds_maximum", execute["reason_codes"])
        self.assert_closed(execute)

    def test_all_four_dry_run_risks_ignore_every_execute_only_blocker(self) -> None:
        # Moving any execute-only check before dry-run precedence must make this fail.
        blockers = (
            {"mutation_class": "write"},
            {"required_capabilities": []},
            {"retry": {"enabled": True}},
            {"retry": {}},
            {"fallback": {"enabled": True}},
            {"fallback": False},
            {"max_attempts": 2},
            {"max_call_depth": 0},
        )
        for risk, expected in (
            ("low", "unclassified"),
            ("medium", "unclassified"),
            ("high", "human-review-required"),
            ("unknown", "human-review-required"),
        ):
            for blocker in ({}, *blockers):
                with self.subTest(risk=risk, blocker=blocker):
                    result = self.output(safe_task(risk_class=risk, **blocker), "dry-run", None, 1, None)
                    self.assertEqual(expected, result["classification"])
                    expected_reason = "elevated_risk_human_review" if risk in {"high", "unknown"} else "no_authority_effect"
                    self.assertEqual([expected_reason], result["reason_codes"])
                    self.assert_closed(result)

    def test_every_exact_execute_blocker_is_independent(self) -> None:
        # Ignoring or misreading any exact nested execute field must make this fail.
        valid_scope = object()
        cases = (
            (safe_task(risk_class="high"), "alias", 0, valid_scope, "elevated_risk_execute_blocked"),
            (safe_task(mutation_class="write"), "alias", 0, valid_scope, "mutation_not_none"),
            (safe_task(), None, 0, valid_scope, "missing_selected_alias_for_execute"),
            (safe_task(), "", 0, valid_scope, "missing_selected_alias_for_execute"),
            (safe_task(), "alias", 0, None, "missing_scope_for_execute"),
            (safe_task(retry={"enabled": True}), "alias", 0, valid_scope, "retry_enabled"),
            (safe_task(retry={}), "alias", 0, valid_scope, "retry_enabled"),
            (safe_task(retry=False), "alias", 0, valid_scope, "retry_enabled"),
            (safe_task(fallback={"enabled": True}), "alias", 0, valid_scope, "fallback_enabled"),
            (safe_task(fallback={}), "alias", 0, valid_scope, "fallback_enabled"),
            (safe_task(fallback=False), "alias", 0, valid_scope, "fallback_enabled"),
            (safe_task(max_attempts=True), "alias", 0, valid_scope, "max_attempts_not_one"),
            (safe_task(max_attempts=0), "alias", 0, valid_scope, "max_attempts_not_one"),
            (safe_task(max_attempts=2), "alias", 0, valid_scope, "max_attempts_not_one"),
            (safe_task(required_capabilities=[]), "alias", 0, valid_scope, "read_only_capability_required"),
            (safe_task(required_capabilities="read-only"), "alias", 0, valid_scope, "read_only_capability_required"),
        )
        for value, alias, depth, scope, reason in cases:
            with self.subTest(reason=reason, value=value):
                result = self.output(value, "execute", alias, depth, scope)
                self.assertEqual("blocked", result["classification"])
                self.assertIn(reason, result["reason_codes"])
                self.assert_closed(result)

    def test_valid_safe_execute_is_unclassified_and_non_authorizing(self) -> None:
        # Blocking a complete safe execute or granting authority must make this fail.
        result = self.output(safe_task(), "execute", "exact-alias", 1, object())
        self.assertEqual("unclassified", result["classification"])
        self.assertEqual(["no_authority_effect"], result["reason_codes"])
        self.assert_closed(result)

    def test_exact_fields_override_legacy_compatibility_inputs(self) -> None:
        # Allowing flattened compatibility fields to override exact fields must make this fail.
        value = safe_task(
            mutation="write",
            capabilities=[],
            retry_enabled=True,
            fallback_enabled=True,
        )
        result = self.output(value, "execute", "alias", 0, object())
        self.assertEqual("unclassified", result["classification"])
        self.assertEqual(["no_authority_effect"], result["reason_codes"])
        self.assert_closed(result)

    def test_reasons_are_sorted_unique_and_nonempty(self) -> None:
        # Returning duplicate, unsorted, or empty reasons must make this fail.
        result = self.output(
            safe_task(
                risk_class="high",
                mutation_class="write",
                required_capabilities=[],
                retry={"enabled": True},
                fallback={"enabled": True},
                max_attempts=2,
            ),
            "execute",
            None,
            3,
            None,
        )
        self.assertEqual(sorted(set(result["reason_codes"])), result["reason_codes"])
        self.assertGreater(len(result["reason_codes"]), 1)
        self.assert_closed(result)


if __name__ == "__main__":
    unittest.main()
