from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from frontdoor.route import route
from orchestration.lib.contracts import validate_contract
from orchestration.lib.errors import ContractError
from orchestration.lib.registry import load_registry


ROOT = Path(__file__).resolve().parents[1]


def task(**extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "0.1.0",
        "task_id": "task-1",
        "caller_id": "caller-1",
        "invocation_id": "invoke-1",
        "requested_action": "advisory",
        "risk_class": "low",
        "mutation_class": "none",
        "required_capabilities": ["read-only"],
        "cost_ceiling_usd_micros": 0,
        "context_files": [],
        "max_context_files": 1,
        "max_context_bytes": 1,
        "max_attempts": 1,
        "retry": {"enabled": False},
        "fallback": {"enabled": False},
        "prompt_file": "prompt.txt",
    }
    value.update(extra)
    return value


def registry() -> dict[str, object]:
    return {
        "claude-code-agent": {
            "adapter_id": "claude-code-agent",
            "state": "staged",
            "capabilities": ["read-only", "advisory"],
        },
        "codex-cli": {
            "adapter_id": "codex-cli",
            "state": "staged",
            "capabilities": ["read-only", "advisory"],
        },
        "ollama-local": {
            "adapter_id": "ollama-local",
            "state": "staged",
            "capabilities": ["read-only", "advisory"],
            "model_alias": "friend-core-advisory",
        },
    }


class FrontdoorTests(unittest.TestCase):
    def assert_closed(self, result: dict[str, object]) -> None:
        self.assertEqual(
            {
                "schema_version",
                "task_id",
                "invocation_id",
                "status",
                "recommended_alias",
                "selected_alias",
                "actual_alias",
                "authority_effect",
            },
            set(result),
        )
        self.assertIsNone(result["selected_alias"])
        self.assertIsNone(result["actual_alias"])
        self.assertEqual("none", result["authority_effect"])
        self.assertEqual(result, validate_contract("decision", result))

    def test_real_registry_positive_path_is_fully_unspied(self) -> None:
        # Bypassing real registry eligibility or lexical ordering must make this fail.
        real_registry = load_registry(ROOT / "orchestration/config/executors.json")
        result = route(task(), real_registry)
        self.assertEqual("recommended", result["status"])
        self.assertEqual("claude-code-agent", result["recommended_alias"])
        self.assertTrue(result["recommended_alias"])
        self.assert_closed(result)

    def test_validated_objects_reach_eligibility_and_result_is_lexical(self) -> None:
        # Passing raw inputs or trusting an unsorted eligibility tuple must make this fail.
        checked_task = validate_contract("task", task())
        checked_registry = validate_contract("executor-registry", registry())
        with patch("frontdoor.route.eligible_aliases", return_value=("zulu", "alpha")) as eligible:
            result = route(task(), registry())
        eligible.assert_called_once_with(checked_task, checked_registry)
        self.assertEqual("recommended", result["status"])
        self.assertEqual("alpha", result["recommended_alias"])
        self.assert_closed(result)

    def test_no_eligible_high_and_unknown_results_are_closed(self) -> None:
        # Recommending an alias for unavailable or elevated work must make this fail.
        unavailable = task(required_capabilities=["not-installed"])
        result = route(unavailable, registry())
        self.assertEqual("no_eligible_alias", result["status"])
        self.assertIsNone(result["recommended_alias"])
        self.assert_closed(result)
        for risk in ("high", "unknown"):
            with self.subTest(risk=risk):
                result = route(task(risk_class=risk), registry())
                self.assertEqual("human_review_required", result["status"])
                self.assertIsNone(result["recommended_alias"])
                self.assert_closed(result)

    def test_invalid_task_and_registry_stop_before_eligibility(self) -> None:
        # Calling eligibility after either real validator rejects must make this fail.
        cases = (
            (task(risk_class="invalid"), registry()),
            (task(), {**registry(), "codex-cli": {"state": "ready"}}),
        )
        for task_value, registry_value in cases:
            with self.subTest(task_value=task_value, registry_value=registry_value):
                with patch("frontdoor.route.eligible_aliases") as eligible:
                    with self.assertRaises(ContractError):
                        route(task_value, registry_value)
                eligible.assert_not_called()

    def test_route_has_no_process_network_write_exec_or_authority_effect(self) -> None:
        # Adding any execution, network, filesystem-write, or shell surface must make this fail.
        forbidden = AssertionError("forbidden route side effect")
        with (
            patch.object(subprocess, "run", side_effect=forbidden),
            patch.object(subprocess, "Popen", side_effect=forbidden),
            patch.object(socket, "socket", side_effect=forbidden),
            patch.object(os, "write", side_effect=forbidden),
            patch.object(os, "mkdir", side_effect=forbidden),
            patch.object(os, "unlink", side_effect=forbidden),
            patch.object(os, "system", side_effect=forbidden),
            patch.object(os, "execv", side_effect=forbidden),
        ):
            result = route(task(), registry())
        self.assert_closed(result)
        flattened = repr(result).lower()
        for positive in ("allow", "approved", "authorized"):
            self.assertNotIn(positive, flattened)


if __name__ == "__main__":
    unittest.main()
