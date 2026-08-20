from __future__ import annotations

import unittest

from mothership.contracts import (
    DecisionCardProductionError,
    build_decision_card,
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
    def _build(self, *, router: object | None = None, **kwargs: object) -> dict[str, object] | None:
        frontdoor, handoff = build_inputs(**kwargs)
        return build_decision_card(
            frontdoor,
            handoff,
            decision_id="decision-demo-review-001",
            question="Should this supplied change receive human review?",
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
        self.assertEqual("fictional-code-reviewer", card["recommendation"])
        self.assertEqual(
            [
                "frontdoor.human_gate=CONFIRM",
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


if __name__ == "__main__":
    unittest.main()
