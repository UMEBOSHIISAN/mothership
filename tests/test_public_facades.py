from __future__ import annotations

import unittest

from orchestration.lib import adapters as old_adapters
from orchestration.lib import canonical, contracts as old_contracts, jsonio, ledger, paths
from orchestration.lib import decision as old_decision
from orchestration.lib import registry as old_registry


class PublicFacadeTests(unittest.TestCase):
    def test_scope_facade_reexports_authoritative_objects(self) -> None:
        from mothership import scope

        expected = (
            "PreparedScope",
            "ScopeFile",
            "open_output_leaf",
            "prepare_scope",
            "validate_relative_path",
        )
        self.assertEqual(expected, scope.__all__)
        for name in expected:
            with self.subTest(name=name):
                self.assertIs(getattr(paths, name), getattr(scope, name))

    def test_approval_facade_reexports_authoritative_objects(self) -> None:
        from mothership import approval

        expected = (
            "AbsentApprovalError",
            "CeremonyIOError",
            "EventValidationError",
            "ExpiredApprovalError",
            "FinishAttemptError",
            "FutureIssuedApprovalError",
            "InvocationBinding",
            "LedgerError",
            "LedgerIOError",
            "MalformedLedgerEntryError",
            "NaiveDatetimeError",
            "ReplayedInvocationError",
            "StaleInvocationDigestError",
            "StalePromptDigestError",
            "StaleRegistryDigestError",
            "StaleScopeDigestError",
            "StaleTaskDigestError",
            "WrongAliasError",
            "append_event",
            "approve_interactively",
            "consume_approval_and_start",
            "finish_attempt",
            "make_binding",
            "validate_event",
        )
        self.assertEqual(expected, approval.__all__)
        for name in expected:
            with self.subTest(name=name):
                self.assertIs(getattr(ledger, name), getattr(approval, name))

    def test_adapter_facade_reexports_authoritative_objects(self) -> None:
        from mothership import adapters

        expected = (
            "AdapterPlan",
            "AdapterPlanPreview",
            "build_adapter_plan",
            "build_adapter_plan_preview",
            "doctor_adapter",
        )
        self.assertEqual(expected, adapters.__all__)
        for name in expected:
            with self.subTest(name=name):
                self.assertIs(getattr(old_adapters, name), getattr(adapters, name))

    def test_contract_facade_reexports_authoritative_objects(self) -> None:
        from mothership import contracts

        expected_sources = {
            "ContractError": old_contracts,
            "DecisionBindingError": old_decision,
            "DecisionCardProductionError": old_decision,
            "build_decision_batch": old_decision,
            "build_decision_card": old_decision,
            "canonical_json_bytes": canonical,
            "canonical_json_sha256": canonical,
            "eligible_aliases": old_registry,
            "format_decision_batch": old_decision,
            "load_registry": old_registry,
            "load_strict": jsonio,
            "loads_strict": jsonio,
            "sha256_bytes": canonical,
            "sha256_file": canonical,
            "validate_contract": old_contracts,
            "validate_decision_approval_binding": old_decision,
        }
        self.assertEqual(tuple(sorted(expected_sources)), contracts.__all__)
        for name, source in expected_sources.items():
            with self.subTest(name=name):
                self.assertIs(getattr(source, name), getattr(contracts, name))

    def test_facades_publish_no_implicit_extra_names(self) -> None:
        from mothership import adapters, approval, contracts, scope

        for module in (adapters, approval, contracts, scope):
            with self.subTest(module=module.__name__):
                public = tuple(sorted(name for name in vars(module) if not name.startswith("_")))
                self.assertEqual(module.__all__, public)


if __name__ == "__main__":
    unittest.main()
