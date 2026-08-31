from __future__ import annotations

import unittest

from mothership.contracts import (
    DecisionCardProductionError,
    build_decision_batch,
    build_decision_card,
    format_decision_batch,
    validate_decision_approval_binding,
)
from orchestration.lib.canonical import canonical_json_sha256


def frontdoor_task(*, human_gate: str = "CONFIRM", unknowns: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": "intake.v0",
        "request_id": "demo-review-001",
        "human_request": "Review the supplied fictional change",
        "task_class": "CODE_REVIEW",
        "risk_tags": [],
        "allowed_actions": ["read supplied files", "report findings"],
        "forbidden_actions": ["modify files", "execute commands"],
        "required_evidence": ["review findings"],
        "required_manifest": None,
        "human_gate": human_gate,
        "predicted_worker_capability": "code-review",
        "unknowns": [] if unknowns is None else unknowns,
        "assumptions": ["the supplied change is fictional"],
        "next_safe_step": "Inspect the fictional change",
    }


def governance_handoff(*, risk: str = "low", task_id: str = "demo-review-001") -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "task_id": task_id,
        "capability": "code-review",
        "risk": risk,
        "token_budget": 4000,
        "evidence_references": ["evidence:demo-change-v1"],
    }


def router_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": "demo-review-001",
        "capability": "code-review",
        "status": "approval_required",
        "recommended_alias": "fictional-code-reviewer",
        "registry_sha256": "f" * 64,
        "reasons": ["manifest_only", "manual_execution_not_implemented"],
        "authority_effect": False,
        "execution_effect": False,
    }


def build_inputs(**kwargs: object) -> tuple[dict[str, object], dict[str, object]]:
    return frontdoor_task(**kwargs), governance_handoff()


class DecisionDiscoveryTests(unittest.TestCase):
    def _build(
        self,
        *,
        router: object | None = None,
        recommendation: object = None,
        reasons: list[str] | None = None,
        **kwargs: object,
    ) -> dict[str, object] | None:
        frontdoor, handoff = build_inputs(**kwargs)
        return build_decision_card(
            frontdoor,
            handoff,
            decision_id="decision-demo-review-001",
            question="Should this supplied change receive human review?",
            recommendation=recommendation,
            reasons=[] if reasons is None else reasons,
            consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
            router_manifest=router,
        )

    def test_frontdoor_and_wgm_alone_produce_one_valid_card(self) -> None:
        card = self._build()

        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual("decision-card.v0", card["schema_version"])
        self.assertEqual("decision-demo-review-001", card["decision_id"])
        self.assertEqual("demo-review-001", card["task_id"])
        self.assertEqual(["evidence:demo-change-v1"], card["evidence_refs"])
        self.assertEqual("low", card["risk"])
        self.assertEqual([], card["unknowns"])
        self.assertIsNone(card["recommendation"])
        self.assertEqual("frontdoor.human_gate=CONFIRM", card["reasons"][0])
        self.assertEqual("human", card["authority_required"])
        self.assertFalse(card["authority_effect"])
        self.assertFalse(card["execution_effect"])

    def test_router_is_optional_and_advisory(self) -> None:
        card = self._build(router=router_manifest())

        self.assertIsNotNone(card)
        assert card is not None
        self.assertIsNone(card["recommendation"])
        self.assertEqual(
            [
                "frontdoor.human_gate=CONFIRM",
                "router-manifest.status=approval_required",
                "router-manifest.reason=manifest_only",
                "router-manifest.reason=manual_execution_not_implemented",
            ],
            card["reasons"],
        )

    def test_explicit_decision_recommendation_and_reasons_are_preserved(self) -> None:
        card = self._build(
            router=router_manifest(),
            recommendation="DO NOT MERGE AS-IS",
            reasons=[
                "PR branch materially diverged from current main",
                "runtime authority impact remains UNKNOWN",
            ],
        )

        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual("DO NOT MERGE AS-IS", card["recommendation"])
        self.assertEqual(
            [
                "frontdoor.human_gate=CONFIRM",
                "PR branch materially diverged from current main",
                "runtime authority impact remains UNKNOWN",
                "router-manifest.status=approval_required",
                "router-manifest.reason=manifest_only",
                "router-manifest.reason=manual_execution_not_implemented",
            ],
            card["reasons"],
        )

    def test_unknowns_are_copied_without_inference(self) -> None:
        frontdoor, handoff = build_inputs(unknowns=["friend-machine portability is unverified"])

        card = build_decision_card(
            frontdoor,
            handoff,
            decision_id="decision-demo-review-001",
            question="Should this supplied change receive human review?",
            consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
        )

        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(["friend-machine portability is unverified"], card["unknowns"])

    def test_human_gate_none_returns_no_decision_card(self) -> None:
        frontdoor, handoff = build_inputs(human_gate="NONE")

        self.assertIsNone(
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="Should this supplied change receive human review?",
                consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
            )
        )

    def test_high_risk_without_human_gate_fails_closed(self) -> None:
        frontdoor, handoff = build_inputs(human_gate="NONE")
        handoff["risk"] = "high"

        with self.assertRaises(DecisionCardProductionError):
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="Should this supplied change receive human review?",
                consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
            )

    def test_identity_drift_fails_closed(self) -> None:
        frontdoor, handoff = build_inputs()
        handoff["task_id"] = "different-task"

        with self.assertRaises(DecisionCardProductionError):
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="Should this supplied change receive human review?",
                consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
            )

    def test_router_identity_or_effect_drift_fails_closed(self) -> None:
        frontdoor, handoff = build_inputs()
        router = router_manifest()
        router["task_id"] = "different-task"

        with self.assertRaises(DecisionCardProductionError):
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="Should this supplied change receive human review?",
                consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
                router_manifest=router,
            )

        router = router_manifest()
        router["execution_effect"] = True
        with self.assertRaises(DecisionCardProductionError):
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="Should this supplied change receive human review?",
                consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
                router_manifest=router,
            )

    def test_human_facing_synthesis_is_explicit_and_validated(self) -> None:
        frontdoor, handoff = build_inputs()

        with self.assertRaises(DecisionCardProductionError):
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="",
                consequence_if_approved="The reviewed proposal may proceed to the separately owned next boundary.",
            )

        with self.assertRaises(DecisionCardProductionError):
            build_decision_card(
                frontdoor,
                handoff,
                decision_id="decision-demo-review-001",
                question="Should this supplied change receive human review?",
                consequence_if_approved="",
            )

    def test_card_generation_does_not_create_approval_or_execution_effect(self) -> None:
        card = self._build()

        self.assertIsNotNone(card)
        assert card is not None
        self.assertNotIn("approval", card)
        self.assertNotIn("execute", card)
        self.assertNotIn("worker", card)
        self.assertNotIn("model", card)
        self.assertFalse(card["authority_effect"])
        self.assertFalse(card["execution_effect"])

    def test_existing_human_approval_binding_remains_a_separate_step(self) -> None:
        card = self._build()

        self.assertIsNotNone(card)
        assert card is not None
        approval = {
            "schema_version": "decision-approval.v0",
            "approval_id": "approval-demo-review-001",
            "decision_id": card["decision_id"],
            "decision_card_sha256": canonical_json_sha256(card),
            "approver_class": "human",
            "event": "approve",
            "recorded_at": "2026-08-20T12:00:00Z",
            "expires_at": "2026-08-20T13:00:00Z",
        }

        validated_card, validated_approval = validate_decision_approval_binding(card, approval)
        self.assertEqual(card, validated_card)
        self.assertEqual(approval, validated_approval)

    def test_ephemeral_batch_keeps_card_no_card_and_fail_closed_separate(self) -> None:
        card_frontdoor, card_handoff = build_inputs()
        card_router = router_manifest()

        no_card_frontdoor, no_card_handoff = build_inputs(human_gate="NONE")

        failed_frontdoor, failed_handoff = build_inputs(human_gate="NONE")
        failed_handoff["risk"] = "high"

        batch = build_decision_batch(
            [
                {
                    "frontdoor_task": card_frontdoor,
                    "governance_handoff": card_handoff,
                    "question": "Should the supplied change receive human review?",
                    "recommendation": "REVIEW",
                    "reasons": ["explicit batch reason"],
                    "consequence_if_approved": "The separately owned review boundary may proceed.",
                    "router_manifest": card_router,
                },
                {
                    "frontdoor_task": no_card_frontdoor,
                    "governance_handoff": no_card_handoff,
                    "question": "Should the ordinary task receive human review?",
                    "consequence_if_approved": "No automatic action follows.",
                },
                {
                    "frontdoor_task": failed_frontdoor,
                    "governance_handoff": failed_handoff,
                    "question": "Should the high-risk task receive human review?",
                    "consequence_if_approved": "The separately owned boundary may proceed.",
                },
            ]
        )

        self.assertEqual(1, len(batch["decision_cards"]))
        self.assertEqual(1, len(batch["no_cards"]))
        self.assertEqual(1, len(batch["fail_closed"]))
        self.assertEqual("demo-review-001", batch["decision_cards"][0]["input_id"])
        self.assertEqual("REVIEW", batch["decision_cards"][0]["recommendation"])
        self.assertEqual("explicit-decision-input", batch["decision_cards"][0]["recommendation_provenance"])
        self.assertIn("explicit batch reason", batch["decision_cards"][0]["reasons"])
        self.assertEqual("NO_CARD", batch["no_cards"][0]["classification"])
        self.assertEqual("FAIL_CLOSED", batch["fail_closed"][0]["classification"])
        self.assertEqual(
            {"input_count": 3, "decision_card_count": 1, "no_card_count": 1, "fail_closed_count": 1},
            batch["summary"],
        )

    def test_ephemeral_batch_preserves_unknowns_and_near_duplicate_identity(self) -> None:
        first_frontdoor, first_handoff = build_inputs(unknowns=["which files are in scope"])
        second_frontdoor, second_handoff = build_inputs(unknowns=["which records are in scope"])
        second_frontdoor["request_id"] = "demo-review-002"
        second_handoff["task_id"] = "demo-review-002"

        batch = build_decision_batch(
            [
                {
                    "frontdoor_task": first_frontdoor,
                    "governance_handoff": first_handoff,
                    "question": "Which bounded scope should the human select?",
                    "consequence_if_approved": "Only the selected scope may proceed.",
                },
                {
                    "frontdoor_task": second_frontdoor,
                    "governance_handoff": second_handoff,
                    "question": "Which bounded scope should the human select?",
                    "consequence_if_approved": "Only the selected scope may proceed.",
                },
            ]
        )

        cards = batch["decision_cards"]
        self.assertEqual(2, len(cards))
        self.assertEqual(["demo-review-001", "demo-review-002"], [card["input_id"] for card in cards])
        self.assertEqual(["which files are in scope"], cards[0]["unknowns"])
        self.assertEqual(["which records are in scope"], cards[1]["unknowns"])
        self.assertNotEqual(cards[0]["decision_id"], cards[1]["decision_id"])

    def test_ephemeral_batch_malformed_item_fails_closed_without_stopping_other_items(self) -> None:
        frontdoor, handoff = build_inputs()

        batch = build_decision_batch(
            [
                {"frontdoor_task": frontdoor},
                {
                    "frontdoor_task": frontdoor,
                    "governance_handoff": handoff,
                    "question": "Should the supplied change receive human review?",
                    "consequence_if_approved": "The separately owned review boundary may proceed.",
                },
            ]
        )

        self.assertEqual(1, len(batch["decision_cards"]))
        self.assertEqual(1, len(batch["fail_closed"]))
        self.assertEqual("batch_input_invalid", batch["fail_closed"][0]["reason"])

    def test_fail_closed_identifier_rendering_escapes_line_and_terminal_controls(self) -> None:
        hostile_id = "bad\nFAIL_CLOSED (999)\x1b[2J"
        batch = build_decision_batch(
            [{"frontdoor_task": {"request_id": hostile_id}}]
        )

        rendered = format_decision_batch(batch)

        self.assertNotIn(hostile_id, rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertIn(r"bad\nFAIL_CLOSED (999)\u001b[2J", rendered)
        self.assertEqual(1, rendered.count("FAIL_CLOSED (999)"))

    def test_nested_presentation_text_escapes_terminal_and_directional_controls(self) -> None:
        frontdoor, handoff = build_inputs(unknowns=["unsafe\x85line\u202eend"])
        batch = build_decision_batch(
            [
                {
                    "frontdoor_task": frontdoor,
                    "governance_handoff": handoff,
                    "question": "Should the supplied change receive human review?",
                    "consequence_if_approved": "The separately owned review boundary may proceed.",
                }
            ]
        )

        rendered = format_decision_batch(batch)

        self.assertNotIn("\x85", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn(r'unknowns: ["unsafe\u0085line\u202eend"]', rendered)

    def test_ephemeral_batch_formatter_is_human_readable_and_not_prioritized(self) -> None:
        frontdoor, handoff = build_inputs()
        batch = build_decision_batch(
            [
                {
                    "frontdoor_task": frontdoor,
                    "governance_handoff": handoff,
                    "question": "Should the supplied change receive human review?",
                    "consequence_if_approved": "The separately owned review boundary may proceed.",
                }
            ]
        )

        rendered = format_decision_batch(batch)
        self.assertIn("EPHEMERAL DECISION BATCH", rendered)
        self.assertIn("DECISION_CARD (1)", rendered)
        self.assertIn("question:", rendered)
        self.assertIn("evidence_refs:", rendered)
        self.assertIn("authority_effect: false", rendered)
        self.assertIn("execution_effect: false", rendered)
        self.assertNotIn("priority", rendered.lower())
        self.assertNotIn("queue", rendered.lower())


if __name__ == "__main__":
    unittest.main()
