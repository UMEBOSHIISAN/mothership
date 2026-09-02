from __future__ import annotations

import copy
import inspect
from pathlib import Path
import unittest

import orchestration.lib.canonical as canonical_module
import orchestration.lib.contracts as contracts_module
import orchestration.lib.jsonio as jsonio_module
import orchestration.lib.registry as registry_module
from orchestration.lib.canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_bytes,
    sha256_file,
)
from orchestration.lib.contracts import _validate_schema, validate_contract
from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import load_strict, loads_strict
from orchestration.lib.registry import eligible_aliases, load_registry


ROOT = Path(__file__).resolve().parents[1]
LOWER_SHA256 = "a" * 64


def task_contract() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "task_id": "task-001",
        "caller_id": "friend-user",
        "invocation_id": "invocation-001",
        "requested_action": "advisory",
        "risk_class": "low",
        "mutation_class": "none",
        "required_capabilities": ["read-only", "advisory"],
        "cost_ceiling_usd_micros": 250_000,
        "context_files": ["README.md", "docs/guide.md"],
        "max_context_files": 2,
        "max_context_bytes": 4096,
        "max_attempts": 1,
        "retry": {"enabled": False},
        "fallback": {"enabled": False},
        "prompt_file": "prompts/task.md",
    }


def decision_contract() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "task_id": "task-001",
        "invocation_id": "invocation-001",
        "status": "recommended",
        "recommended_alias": "codex-cli",
        "selected_alias": None,
        "actual_alias": None,
        "authority_effect": "none",
    }


def assessment_contract() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "task_id": "task-001",
        "invocation_id": "invocation-001",
        "classification": "unclassified",
        "reason_codes": ["no_authority_effect"],
        "authority_effect": "none",
    }


def invocation_contract() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "invocation_id": "invocation-001",
        "task_ref": "tasks/task-001.json",
        "task_sha256": LOWER_SHA256,
        "registry_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "scope_sha256": "d" * 64,
        "selected_alias": "codex-cli",
        "execute": False,
        "task_root": "workspace/task-001",
        "run_root": "runs/invocation-001",
    }


def approval_event_contract() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "event_id": "event-" + "1" * 32,
        "event_type": "approval_granted",
        "alias": "codex-cli",
        "invocation_id": "invocation-001",
        "registry_sha256": "1" * 64,
        "task_sha256": "2" * 64,
        "prompt_sha256": "3" * 64,
        "scope_sha256": "4" * 64,
        "invocation_sha256": "5" * 64,
        "recorded_at": "2026-08-02T10:00:00Z",
        "expires_at": "2026-08-02T10:15:00Z",
    }


class ContractTestCase(unittest.TestCase):
    def test_version_and_fixed_function_signatures_are_exact(self) -> None:
        self.assertEqual(b"0.4.0\n", (ROOT / "VERSION").read_bytes())
        expected_parameters = (
            (loads_strict, ("raw",)),
            (load_strict, ("path",)),
            (canonical_json_bytes, ("value",)),
            (sha256_bytes, ("raw",)),
            (sha256_file, ("path",)),
            (canonical_json_sha256, ("value",)),
            (validate_contract, ("kind", "value")),
            (load_registry, ("path",)),
            (eligible_aliases, ("task", "registry")),
        )
        for function, names in expected_parameters:
            with self.subTest(function=function.__name__):
                parameters = inspect.signature(function).parameters
                self.assertEqual(names, tuple(parameters))
                self.assertTrue(
                    all(parameter.default is inspect.Parameter.empty for parameter in parameters.values())
                )

    def test_task_accepts_exact_sixteen_fields_and_rejects_shape_type_and_enums(self) -> None:
        task = task_contract()
        self.assertEqual(task, validate_contract("task", task))
        self.assertEqual(16, len(task))
        for field in task:
            with self.subTest(missing=field):
                missing = dict(task)
                del missing[field]
                with self.assertRaises(ContractError):
                    validate_contract("task", missing)
        invalid_values = (
            dict(task, unknown=True),
            dict(task, task_id=1),
            dict(task, requested_action="approve"),
            dict(task, risk_class="trusted"),
            dict(task, required_capabilities="read-only"),
            dict(task, cost_ceiling_usd_micros=True),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("task", value)

    def test_task_rejects_duplicate_and_unsafe_context_and_prompt_paths(self) -> None:
        task = task_contract()
        invalid_contexts = (
            ["README.md", "README.md"],
            ["/absolute/file"],
            ["../outside/file"],
            ["src\\main.py"],
        )
        for context_files in invalid_contexts:
            with self.subTest(context_files=context_files):
                with self.assertRaises(ContractError):
                    validate_contract("task", dict(task, context_files=context_files))
        for prompt_file in ("/absolute/prompt.md", "../prompt.md", "prompts\\task.md"):
            with self.subTest(prompt_file=prompt_file):
                with self.assertRaises(ContractError):
                    validate_contract("task", dict(task, prompt_file=prompt_file))

    def test_task_enforces_mutation_attempt_retry_fallback_and_context_budgets(self) -> None:
        task = task_contract()
        invalid_values = (
            dict(task, mutation_class="write"),
            dict(task, max_attempts=2),
            dict(task, retry={"enabled": True}),
            dict(task, fallback={"enabled": True}),
            dict(task, retry={"enabled": False, "attempts": 1}),
            dict(task, fallback=False),
            dict(task, max_context_files=0),
            dict(task, max_context_files=33),
            dict(task, max_context_bytes=0),
            dict(task, max_context_bytes=1_048_577),
            dict(task, max_context_files=1),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("task", value)

    def test_decision_is_advisory_only_and_rejects_task_02r_authority_fields(self) -> None:
        decision = decision_contract()
        self.assertEqual(decision, validate_contract("decision", decision))
        no_alias = dict(decision, status="no_eligible_alias", recommended_alias=None)
        human_review = dict(decision, status="human_review_required", recommended_alias=None)
        self.assertEqual(no_alias, validate_contract("decision", no_alias))
        self.assertEqual(human_review, validate_contract("decision", human_review))
        invalid_values = (
            dict(decision, verdict="APPROVE"),
            dict(decision, rationale="approved"),
            dict(decision, status="APPROVE"),
            dict(decision, selected_alias="codex-cli"),
            dict(decision, actual_alias="codex-cli"),
            dict(decision, authority_effect="execute"),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("decision", value)

    def test_invocation_request_has_exact_closed_fields_and_lowercase_digests(self) -> None:
        invocation = invocation_contract()
        self.assertEqual(invocation, validate_contract("invocation-request", invocation))
        self.assertEqual(11, len(invocation))
        for field in invocation:
            with self.subTest(missing=field):
                missing = dict(invocation)
                del missing[field]
                with self.assertRaises(ContractError):
                    validate_contract("invocation-request", missing)
        for value in (
            dict(invocation, task_sha256="A" * 64),
            dict(invocation, prompt_sha256="a" * 63),
            dict(invocation, execute="false"),
            dict(invocation, publication_authority=False),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("invocation-request", value)

    def test_approval_event_is_registered_and_accepts_each_closed_schema_shape(self) -> None:
        base = approval_event_contract()
        values = (
            base,
            dict(base, event_type="confirmation_failed", confirmation_result="mismatch"),
            dict(
                base,
                event_type="attempt_started",
                approval_event_id="event-" + "2" * 32,
                approval_sha256="6" * 64,
            ),
            dict(
                base,
                event_type="attempt_finished",
                attempt_started_event_id="event-" + "3" * 32,
                exit_class="timeout",
                exit_code=None,
            ),
        )
        for value in values:
            with self.subTest(event_type=value["event_type"]):
                self.assertEqual(value, validate_contract("approval-event", value))

    def test_approval_event_rejects_missing_extra_and_invalid_primitive_values(self) -> None:
        base = approval_event_contract()
        self.assertEqual(base, validate_contract("approval-event", base))
        missing = dict(base)
        del missing["event_id"]
        invalid_values = (
            missing,
            dict(base, prompt_text="private"),
            dict(base, schema_version="0.2.0"),
            dict(base, event_id="event-short"),
            dict(base, alias="gemma"),
            dict(base, invocation_id="bad invocation"),
            dict(base, registry_sha256="A" * 64),
            dict(base, task_sha256="2" * 63),
            dict(base, recorded_at="2026-08-02T10:00:00+00:00"),
            dict(base, expires_at="2026-08-02T10:15:00Z\n"),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("approval-event", value)

    def test_approval_event_exit_code_schema_accepts_integer_or_null_but_not_bool(self) -> None:
        base = dict(
            approval_event_contract(),
            event_type="attempt_finished",
            attempt_started_event_id="event-" + "3" * 32,
            exit_class="nonzero-exit",
        )
        for exit_code in (-9, 0, 7, None):
            with self.subTest(exit_code=exit_code):
                value = dict(base, exit_code=exit_code)
                self.assertEqual(value, validate_contract("approval-event", value))
        with self.assertRaises(ContractError):
            validate_contract("approval-event", dict(base, exit_code=True))

    def test_registry_has_exact_staged_entries_and_eligible_aliases_never_select(self) -> None:
        path = ROOT / "orchestration/config/executors.json"
        registry = load_registry(path)
        self.assertEqual(
            ["claude-code-agent", "codex-cli", "ollama-local"],
            sorted(registry),
        )
        for alias in ("claude-code-agent", "codex-cli", "ollama-local"):
            with self.subTest(alias=alias):
                self.assertEqual(alias, registry[alias]["adapter_id"])
                self.assertEqual("staged", registry[alias]["state"])
                self.assertEqual(["read-only", "advisory"], registry[alias]["capabilities"])
        self.assertNotIn("model_alias", registry["claude-code-agent"])
        self.assertNotIn("model_alias", registry["codex-cli"])
        self.assertEqual("friend-core-advisory", registry["ollama-local"]["model_alias"])
        task = task_contract()
        self.assertEqual(
            ("claude-code-agent", "codex-cli", "ollama-local"),
            eligible_aliases(task, registry),
        )
        unavailable = dict(task, required_capabilities=["not-installed"])
        self.assertEqual((), eligible_aliases(unavailable, registry))

    def test_registry_rejects_arrays_alias_drift_nested_extras_and_nonstaged_entries(self) -> None:
        registry = load_registry(ROOT / "orchestration/config/executors.json")
        without_ollama = {key: value for key, value in registry.items() if key != "ollama-local"}
        invalid_values = (
            [],
            {**registry, "codex": registry["codex-cli"]},
            without_ollama,
            {**registry, "codex-cli": {**registry["codex-cli"], "state": "enabled"}},
            {**registry, "codex-cli": {**registry["codex-cli"], "adapter_id": "codex"}},
            {**registry, "codex-cli": {**registry["codex-cli"], "capabilities": ["read-only"]}},
            {**registry, "codex-cli": {**registry["codex-cli"], "executable": "codex"}},
            {**registry, "codex-cli": {**registry["codex-cli"], "model_alias": "friend-core-advisory"}},
            {**registry, "ollama-local": {key: value for key, value in registry["ollama-local"].items() if key != "model_alias"}},
            {**registry, "ollama-local": {**registry["ollama-local"], "model_alias": "other"}},
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_contract("executor-registry", copy.deepcopy(value))

    def test_schema_subset_uses_json_numeric_equality_and_supports_declared_keywords(self) -> None:
        self.assertEqual(1.0, _validate_schema(1.0, {"const": 1}))
        self.assertEqual(1.0, _validate_schema(1.0, {"enum": [1]}))
        for schema in ({"const": 1}, {"enum": [1]}):
            with self.subTest(schema=schema):
                with self.assertRaises(ContractError):
                    _validate_schema(True, schema)
        with self.assertRaises(ContractError):
            _validate_schema([1, 1.0], {"type": "array", "uniqueItems": True})
        self.assertEqual(
            [1, True],
            _validate_schema([1, True], {"type": "array", "uniqueItems": True}),
        )
        nullable_integer_map = {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 4}},
            "required": ["name"],
            "additionalProperties": {"type": ["integer", "null"], "minimum": 1, "maximum": 2},
        }
        value = {"name": "core", "count": 1.0, "other": None}
        self.assertEqual(value, _validate_schema(value, nullable_integer_map))
        with self.assertRaises(ContractError):
            _validate_schema({"name": "core", "count": True}, nullable_integer_map)

    def test_pattern_requires_a_full_string_match(self) -> None:
        # Replacing fullmatch with prefix-only search must make this fail.
        self.assertEqual("abc", _validate_schema("abc", {"type": "string", "pattern": "^[a-z]+$"}))
        with self.assertRaises(ContractError):
            _validate_schema("abc\n", {"type": "string", "pattern": "^[a-z]+$"})

    def test_assessment_is_a_public_bundled_contract_kind(self) -> None:
        # Removing the assessment schema map entry must make this fail.
        assessment = assessment_contract()
        self.assertEqual(assessment, validate_contract("assessment", assessment))
        for invalid in (
            dict(assessment, authority_effect="execute"),
            dict(assessment, reason_codes=[]),
            dict(assessment, reason_codes=["unknown"]),
            dict(assessment, extra=True),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractError):
                    validate_contract("assessment", invalid)

    def test_all_bundled_schemas_are_recursive_closed_draft_2020_12_documents(self) -> None:
        paths = (
            "evidence/contracts/approval-event.schema.json",
            "evidence/contracts/authority-action-approval.v0.schema.json",
            "evidence/contracts/authority-action-consume.v0.schema.json",
            "frontdoor/contracts/decision.schema.json",
            "frontdoor/contracts/task.schema.json",
            "orchestration/contracts/executor-registry.schema.json",
            "orchestration/contracts/invocation-request.schema.json",
            "safety/contracts/assessment.schema.json",
        )

        def assert_recursive_closure(node: object) -> None:
            if type(node) is dict:
                declared_type = node.get("type")
                declares_object = declared_type == "object" or (
                    type(declared_type) is list and "object" in declared_type
                )
                if declares_object:
                    self.assertIs(node.get("additionalProperties"), False)
                for nested in node.values():
                    assert_recursive_closure(nested)
            elif type(node) is list:
                for nested in node:
                    assert_recursive_closure(nested)

        for relative in paths:
            with self.subTest(relative=relative):
                schema = load_strict(ROOT / relative)
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                schema_id = schema["$id"]
                self.assertTrue(
                    "://" not in schema_id or schema_id.startswith("https://example.invalid/"),
                    schema_id,
                )
                assert_recursive_closure(schema)

    def test_task_02r_alternate_public_api_names_are_not_retained_as_aliases(self) -> None:
        alternates = (
            (canonical_module, ("canonical_sha256",)),
            (jsonio_module, ("load_json",)),
            (
                contracts_module,
                (
                    "validate_schema",
                    "validate_decision",
                    "validate_task",
                    "validate_invocation_request",
                    "validate_executor_registry",
                ),
            ),
            (registry_module, ("lookup_executor",)),
        )
        for module, names in alternates:
            for name in names:
                with self.subTest(module=module.__name__, name=name):
                    self.assertFalse(hasattr(module, name))

    def test_unknown_contract_kind_is_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_contract("executor", {})


class TestDecisionApprovalBinding(unittest.TestCase):
    def _card(self):
        return {
            "schema_version": "decision-card.v0",
            "decision_id": "dc-001",
            "task_id": "task-001",
            "question": "Should we proceed?",
            "recommendation": "Yes.",
            "reasons": ["tests pass"],
            "evidence_refs": [],
            "unknowns": [],
            "risk": "low",
            "authority_required": "human",
            "consequence_if_approved": "Task becomes eligible for Router input.",
            "authority_effect": False,
            "execution_effect": False,
        }

    def _approval(self, card):
        from orchestration.lib.canonical import canonical_json_sha256
        from orchestration.lib.contracts import validate_contract
        validated = validate_contract("decision-card", card)
        digest = canonical_json_sha256(validated)
        return {
            "schema_version": "decision-approval.v0",
            "approval_id": "ap-001",
            "decision_id": "dc-001",
            "decision_card_sha256": digest,
            "approver_class": "human",
            "event": "approve",
            "recorded_at": "2026-08-20T12:00:00Z",
            "expires_at": "2026-08-20T13:00:00Z",
        }

    def test_binding_passes_for_matching_card_and_approval(self):
        from orchestration.lib.decision import validate_decision_approval_binding
        card = self._card()
        approval = self._approval(card)
        validated_card, validated_approval = validate_decision_approval_binding(card, approval)
        assert validated_card["decision_id"] == "dc-001"
        assert validated_approval["approval_id"] == "ap-001"

    def test_binding_fails_when_card_content_changes_after_approval(self):
        from orchestration.lib.decision import DecisionBindingError, validate_decision_approval_binding
        card = self._card()
        approval = self._approval(card)
        # Mutate the card AFTER approval was issued
        mutated_card = {**card, "question": "A completely different question?"}
        with self.assertRaisesRegex(DecisionBindingError, "mismatch"):
            validate_decision_approval_binding(mutated_card, approval)

    def test_binding_fails_for_wrong_digest(self):
        from orchestration.lib.decision import DecisionBindingError, validate_decision_approval_binding
        card = self._card()
        bad_approval = {**self._approval(card), "decision_card_sha256": "b" * 64}
        with self.assertRaisesRegex(DecisionBindingError, "mismatch"):
            validate_decision_approval_binding(card, bad_approval)

    def test_binding_fails_for_decision_id_mismatch(self):
        from orchestration.lib.decision import DecisionBindingError, validate_decision_approval_binding
        card = self._card()
        approval = self._approval(card)
        mismatched = {**approval, "decision_id": "dc-WRONG"}
        with self.assertRaisesRegex(DecisionBindingError, "decision_id mismatch"):
            validate_decision_approval_binding(card, mismatched)

    def test_key_ordering_does_not_affect_binding(self):
        from orchestration.lib.decision import validate_decision_approval_binding
        card = self._card()
        card_reordered = dict(reversed(list(card.items())))
        approval = self._approval(card)
        # Both orderings must produce the same digest and pass binding
        validate_decision_approval_binding(card, approval)
        validate_decision_approval_binding(card_reordered, approval)

    def test_binding_is_not_execution_authority(self):
        """Binding returns (card, approval); neither has authority or execution effect."""
        from orchestration.lib.decision import validate_decision_approval_binding
        card = self._card()
        approval = self._approval(card)
        validated_card, validated_approval = validate_decision_approval_binding(card, approval)
        assert validated_card["authority_effect"] is False
        assert validated_card["execution_effect"] is False
        # decision-approval schema has no authority_effect/execution_effect fields by design
        assert "authority_effect" not in validated_approval
        assert "execution_effect" not in validated_approval


def _valid_decision_card():
    return {
        "schema_version": "decision-card.v0",
        "decision_id": "dc-001",
        "task_id": "task-001",
        "question": "Should we proceed?",
        "recommendation": "Yes, proceed with low-risk path.",
        "reasons": ["tests pass", "scope is narrow"],
        "evidence_refs": ["ev-001", "ev-002"],
        "unknowns": ["portability on friend-PC"],
        "risk": "low",
        "authority_required": "human",
        "consequence_if_approved": "The task-card becomes eligible to be passed to the Router as input.",
        "authority_effect": False,
        "execution_effect": False,
    }


def _valid_decision_approval():
    return {
        "schema_version": "decision-approval.v0",
        "approval_id": "ap-001",
        "decision_id": "dc-001",
        "decision_card_sha256": "a" * 64,
        "approver_class": "human",
        "event": "approve",
        "recorded_at": "2026-08-19T12:00:00Z",
        "expires_at": "2026-08-19T13:00:00Z",
    }


class TestDecisionPlaneContracts(unittest.TestCase):
    def test_decision_card_accept_cases(self):
        from orchestration.lib.contracts import validate_contract

        card = _valid_decision_card()
        assert validate_contract("decision-card", card) == card

        high_risk = {**card, "recommendation": None, "risk": "high"}
        assert validate_contract("decision-card", high_risk) == high_risk

        empty_arrays = {**card, "reasons": [], "evidence_refs": [], "unknowns": []}
        assert validate_contract("decision-card", empty_arrays) == empty_arrays

        max_consequence = {**card, "consequence_if_approved": "x" * 1024}
        assert validate_contract("decision-card", max_consequence) == max_consequence

    def test_decision_card_reject_cases(self):
        from orchestration.lib.contracts import ContractError, validate_contract

        card = _valid_decision_card()
        required = [
            "schema_version",
            "decision_id",
            "task_id",
            "question",
            "recommendation",
            "reasons",
            "evidence_refs",
            "unknowns",
            "risk",
            "authority_required",
            "consequence_if_approved",
            "authority_effect",
            "execution_effect",
        ]
        for field in required:
            candidate = {key: value for key, value in card.items() if key != field}
            with self.assertRaises(ContractError):
                validate_contract("decision-card", candidate)

        invalid_values = [
            {"authority_effect": True},
            {"execution_effect": True},
            {"authority_required": "agent"},
            {"risk": "critical"},
            {"decision_id": "-dc-001"},
            {"evidence_refs": ["ev/001"]},
            {"consequence_if_approved": ""},
            {"consequence_if_approved": "x" * 1025},
            {"approved": True},
            {"recommendation": 42},
        ]
        for change in invalid_values:
            with self.assertRaises(ContractError):
                validate_contract("decision-card", {**card, **change})

        for field in (
            "approved",
            "rejected",
            "execution_status",
            "worker",
            "selected_model",
            "retry_count",
        ):
            with self.assertRaises(ContractError):
                validate_contract("decision-card", {**card, field: True})

    def test_decision_approval_accept_case(self):
        from orchestration.lib.contracts import validate_contract

        approval = _valid_decision_approval()
        assert validate_contract("decision-approval", approval) == approval

    def test_decision_approval_reject_cases(self):
        from orchestration.lib.contracts import ContractError, validate_contract

        approval = _valid_decision_approval()
        for change in (
            {"approver_class": "agent"},
            {"event": "deny"},
            {"decision_card_sha256": "A" * 64},
            {"decision_card_sha256": "abc"},
            {"extra": True},
        ):
            with self.assertRaises(ContractError):
                validate_contract("decision-approval", {**approval, **change})

        for field in approval:
            candidate = {key: value for key, value in approval.items() if key != field}
            with self.assertRaises(ContractError):
                validate_contract("decision-approval", candidate)

    def test_decision_card_digest_binding_invariant(self):
        from orchestration.lib.canonical import canonical_json_sha256

        card_a = _valid_decision_card()
        card_b = {**card_a, "question": "Should we NOT proceed?"}
        card_reordered = dict(reversed(list(card_a.items())))

        assert canonical_json_sha256(card_a) != canonical_json_sha256(card_b)
        assert canonical_json_sha256(card_a) == canonical_json_sha256(card_reordered)


if __name__ == "__main__":
    unittest.main()
