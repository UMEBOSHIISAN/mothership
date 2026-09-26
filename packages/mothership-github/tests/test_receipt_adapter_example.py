from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


class ReceiptAdapterExampleTests(unittest.TestCase):
    def test_offline_example_checks_binding_without_effects(self):
        path = Path(__file__).resolve().parents[3] / "examples/github_receipt_adapter.py"
        self.assertTrue(path.is_file(), "offline receipt adapter example is not implemented")
        spec = importlib.util.spec_from_file_location("receipt_adapter_example", path)
        module = importlib.util.module_from_spec(spec)
        targets = (
            "orchestration.lib.action_authority_ledger.consume_action",
            "orchestration.lib.action_authority_ledger._locked_ledger",
            "mothership_github.executor.execute_action_merge_pr",
            "mothership_github.receipts.record_attempt_started",
            "mothership_github.receipts.record_attempt_finished",
            "urllib.request.urlopen", "socket.socket", "subprocess.Popen",
        )
        with ExitStack() as stack:
            for target in targets:
                stack.enter_context(patch(target, side_effect=AssertionError("unexpected effect")))
            output = io.StringIO()
            with redirect_stdout(output):
                spec.loader.exec_module(module)
                self.assertEqual(0, module.main())
        self.assertEqual([
            "SYNTHETIC ONLY", "binding: accepted", "mismatch: rejected",
            "receipt status: UNKNOWN",
        ], output.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
