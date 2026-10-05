"""Exercise the reference host path with real ledgers and synthetic transport."""

import copy
import datetime
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from examples.portable_action_review import (
    CONTEXT, PARAMETERS, SyntheticTransport, response_for, run_demo, run_reviewed_merge,
)
from mothership.action_authority import ActionAuthorityError, freeze_action
from mothership.action_review import build_review_request


class PortableReviewExampleTests(unittest.TestCase):
    def test_demo_produces_separate_receipt_and_unknown_verification_with_one_put(self):
        with patch("socket.socket", side_effect=AssertionError("offline demo attempted a socket")):
            result = run_demo()
        self.assertTrue(result["simulated_human_response"])
        self.assertEqual("offline", result["mode"])
        self.assertEqual("SUCCESS", result["receipt_status"])
        self.assertEqual("UNKNOWN", result["verification_status"])
        self.assertEqual(1, result["fake_puts"])
        self.assertEqual("blocked", result["replay"])
        self.assertEqual(set(CONTEXT), set(result["context_drift_blocked"]))

    def test_each_changed_context_stops_before_any_ledger_or_transport(self):
        action = freeze_action("act-host-drift", "github.merge_pr", dict(PARAMETERS))
        request = build_review_request(action, request_id="review-drift", host_context=CONTEXT)
        response = response_for(request)
        for field in CONTEXT:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                root.chmod(0o700)
                current = copy.deepcopy(CONTEXT)
                current[field] = [] if field == "scope" else "changed"
                transport = SyntheticTransport()
                with self.assertRaises(ActionAuthorityError):
                    run_reviewed_merge(action, request, response, current,
                                       root / "authority.jsonl", root / "attempts.jsonl", transport)
                self.assertEqual([], list(root.iterdir()))
                self.assertEqual(0, transport.gets)
                self.assertEqual(0, transport.puts)

    def test_expired_resume_stops_before_ledger_or_transport(self):
        at = datetime.datetime(2026, 10, 5, 10, tzinfo=datetime.UTC)
        with patch("orchestration.lib.action_authority._utc_now", return_value=at):
            action = freeze_action("act-expired-review", "github.merge_pr", dict(PARAMETERS))
            request = build_review_request(action, request_id="review-expired", host_context=CONTEXT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            transport = SyntheticTransport()
            with patch("orchestration.lib.action_authority._utc_now", return_value=at + datetime.timedelta(minutes=10)):
                with self.assertRaises(ActionAuthorityError):
                    run_reviewed_merge(action, request, response_for(request), CONTEXT,
                                       root / "authority.jsonl", root / "attempts.jsonl", transport)
            self.assertEqual([], list(root.iterdir()))
            self.assertEqual((0, 0), (transport.gets, transport.puts))


if __name__ == "__main__":
    unittest.main()
