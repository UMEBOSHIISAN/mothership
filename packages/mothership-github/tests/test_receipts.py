"""TDD coverage for the closed GitHub execution-attempt receipt ledger."""

from __future__ import annotations

import copy
import datetime
import inspect
import json
import os
import pathlib
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from orchestration.lib import action_authority, action_authority_ledger, canonical
from mothership_github import receipts


BASE = datetime.datetime(2026, 8, 22, 10, 0, 0, tzinfo=datetime.UTC)
PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}
COMMIT = "c" * 40


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}  # type: ignore[union-attr]
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


class ReceiptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mothership-receipts-")
        self.root = pathlib.Path(self.temp.name)
        self.authority_dir = self.root / "authority"
        self.receipt_dir = self.root / "receipts"
        self.authority_dir.mkdir(mode=0o700)
        self.receipt_dir.mkdir(mode=0o700)
        self.authority = self.authority_dir / "events.jsonl"
        self.receipt = self.receipt_dir / "events.jsonl"
        self.action = self._freeze()
        self.approval = self._approve()
        self.consume_event, self.consumed_action = self._consume()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _freeze(self):
        with mock.patch.object(action_authority, "_utc_now", return_value=BASE):
            return action_authority.freeze_action(
                "act-merge-pr-001", "github.merge_pr", copy.deepcopy(PARAMETERS)
            )

    def _approve(self) -> dict[str, object]:
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=BASE + datetime.timedelta(seconds=1)),
            mock.patch.object(action_authority_ledger, "_utc_now", return_value=BASE + datetime.timedelta(seconds=1)),
        ):
            return action_authority_ledger.record_action_decision(
                self.authority,
                self.action,
                "approve",
                self.action.action["action_id"],
                self.action.action_sha256,
            )

    def _consume(self):
        with mock.patch.object(
            action_authority_ledger, "_utc_now", return_value=BASE + datetime.timedelta(seconds=2)
        ):
            return action_authority_ledger.consume_action(
                self.authority,
                self.approval["event_id"],
                self.action.action["action_id"],
                self.action.action_sha256,
            )

    def _start(self, *, receipt: pathlib.Path | None = None, action: object | None = None,
               consume: object | None = None) -> dict[str, object]:
        with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=3)):
            return receipts.record_attempt_started(
                receipt or self.receipt,
                self.authority,
                consume or self.consume_event,
                action if action is not None else self.action.action,
            )

    def _read(self) -> list[dict[str, object]]:
        if not self.receipt.exists():
            return []
        return [json.loads(line) for line in self.receipt.read_text().splitlines()]

    def test_public_signatures_are_exact_and_rows_are_closed(self) -> None:
        self.assertEqual(
            ("receipt_path", "authority_path", "consume_event", "action"),
            tuple(inspect.signature(receipts.record_attempt_started).parameters),
        )
        self.assertEqual(
            ("receipt_path", "started", "outcome", "observation"),
            tuple(inspect.signature(receipts.record_attempt_finished).parameters),
        )
        started = self._start()
        self.assertEqual(
            {
                "schema_version", "event_type", "event_id", "action_id",
                "action_sha256", "consume_event_id", "recorded_at",
            },
            set(started),
        )
        self.assertEqual("github-execution-attempt.v1", started["schema_version"])
        self.assertEqual("attempt_started", started["event_type"])
        self.assertEqual(self.consume_event["event_id"], started["consume_event_id"])
        self.assertEqual(started, self._read()[0])
        self.assertEqual(0o600, self.receipt.stat().st_mode & 0o777)

    def test_finish_copies_stored_start_and_normalizes_closed_observation(self) -> None:
        started = self._start()
        observation = {"http_status": 200, "merged": True, "merge_commit_sha": COMMIT}
        with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
            finished = receipts.record_attempt_finished(self.receipt, started, "success", observation)
        self.assertEqual("attempt_finished", finished["event_type"])
        self.assertEqual(started["event_id"], finished["attempt_started_event_id"])
        self.assertEqual(started["action_id"], finished["action_id"])
        self.assertEqual(started["action_sha256"], finished["action_sha256"])
        self.assertEqual(started["consume_event_id"], finished["consume_event_id"])
        self.assertEqual(observation, finished["observation"])
        self.assertEqual([started, finished], self._read())

    def test_success_requires_strong_independent_observation(self) -> None:
        started = self._start()
        cases = (
            {"http_status": 200, "merged": True, "merge_commit_sha": None},
            {"http_status": 201, "merged": True, "merge_commit_sha": COMMIT},
            {"http_status": 200, "merged": False, "merge_commit_sha": COMMIT},
            {"http_status": 200, "merged": True, "merge_commit_sha": COMMIT.upper()},
            {"http_status": 200, "merged": True, "merge_commit_sha": COMMIT, "ambiguous": True},
        )
        for observation in cases:
            with self.subTest(observation=observation):
                with self.assertRaises(receipts.ReceiptValidationError):
                    with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
                        receipts.record_attempt_finished(self.receipt, started, "success", observation)
        self.assertEqual([started], self._read())

    def test_failure_rejects_positive_merge_facts_on_append(self) -> None:
        started = self._start()
        before = self.receipt.read_bytes()
        cases = (
            {"http_status": 200, "merged": True, "merge_commit_sha": None},
            {"http_status": 409, "merged": False, "merge_commit_sha": COMMIT},
            {"http_status": 200, "merged": True, "merge_commit_sha": COMMIT},
        )
        for observation in cases:
            with self.subTest(observation=observation):
                self.receipt.write_bytes(before)
                with self.assertRaises(receipts.ReceiptValidationError):
                    with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
                        receipts.record_attempt_finished(self.receipt, started, "failure", observation)
                self.assertEqual(before, self.receipt.read_bytes())

    def test_reconciliation_required_preserves_apparent_success_facts(self) -> None:
        started = self._start()
        observation = {"http_status": 200, "merged": True, "merge_commit_sha": COMMIT}
        with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
            finished = receipts.record_attempt_finished(
                self.receipt, started, "reconciliation_required", observation
            )
        self.assertEqual(observation, finished["observation"])
        self.assertEqual([started, finished], self._read())

    def test_loaded_history_rejects_failure_with_positive_merge_facts(self) -> None:
        started = self._start()
        invalid_finish = {
            "schema_version": "github-execution-attempt.v1",
            "event_type": "attempt_finished",
            "event_id": "event-" + "d" * 32,
            "attempt_started_event_id": started["event_id"],
            "action_id": started["action_id"],
            "action_sha256": started["action_sha256"],
            "consume_event_id": started["consume_event_id"],
            "outcome": "failure",
            "observation": {"http_status": 200, "merged": True, "merge_commit_sha": COMMIT},
            "recorded_at": "2026-08-22T10:00:04Z",
        }
        self.receipt.write_bytes(
            canonical.canonical_json_bytes(started)
            + b"\n"
            + canonical.canonical_json_bytes(invalid_finish)
            + b"\n"
        )
        with self.receipt.open("rb") as handle:
            with self.assertRaises(receipts.MalformedReceiptError):
                receipts._read_history_locked(handle.fileno())

    def test_observation_has_exact_closed_keys_and_status_domain(self) -> None:
        started = self._start()
        for observation in (
            {"http_status": True, "merged": None, "merge_commit_sha": None},
            {"http_status": 99, "merged": None, "merge_commit_sha": None},
            {"http_status": 600, "merged": None, "merge_commit_sha": None},
            {"http_status": 0, "merged": "false", "merge_commit_sha": None},
            {"http_status": 0, "merged": None, "merge_commit_sha": "d" * 39},
            {"http_status": 0, "merged": None, "merge_commit_sha": None, "extra": 1},
        ):
            with self.subTest(observation=observation), self.assertRaises(receipts.ReceiptValidationError):
                with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
                    receipts.record_attempt_finished(self.receipt, started, "failure", observation)

    def test_actual_consume_binding_rejects_forged_missing_and_changed_facts(self) -> None:
        forged_consume = dict(self.consume_event)
        forged_consume["event_id"] = "event-" + "f" * 32
        with self.assertRaises(receipts.ReceiptBindingError):
            self._start(consume=forged_consume)
        with self.assertRaises(receipts.ReceiptBindingError):
            self._start(consume={"event_id": self.consume_event["event_id"]})
        changed_action = _plain(self.action.action)
        changed_action["execution_parameters"]["repository"] = "attacker/repository"  # type: ignore[index]
        with self.assertRaises(receipts.ReceiptBindingError):
            self._start(action=changed_action)
        missing = dict(self.consume_event)
        missing["event_id"] = "event-" + "0" * 32
        with self.assertRaises(receipts.ReceiptBindingError):
            self._start(consume=missing)

    def test_existing_receipt_starts_are_rebound_to_the_captured_authority_snapshot(self) -> None:
        valid_start = self._start()
        self.receipt.write_bytes(b"")
        old = dict(valid_start)
        for mutation in (
            {"consume_event_id": "event-" + "9" * 32},
            {"action_sha256": "f" * 64},
            {"recorded_at": "2026-08-22T10:00:01Z"},
        ):
            with self.subTest(mutation=mutation):
                row = {**old, **mutation}
                self.receipt.write_bytes(canonical.canonical_json_bytes(row) + b"\n")
                with self.assertRaises(receipts.ReceiptBindingError):
                    self._start()
        self.receipt.write_bytes(b"")

    def test_flush_failure_and_rollback_failure_quarantine_without_success(self) -> None:
        started = self._start()
        before = self.receipt.read_bytes()
        with (
            mock.patch.object(receipts, "_flush", side_effect=OSError("synthetic flush")),
            mock.patch.object(receipts, "_fchmod", side_effect=OSError("synthetic mode")),
        ):
            with self.assertRaises(receipts.ReceiptIOError):
                receipts.record_attempt_finished(self.receipt, started, "failure", {
                    "http_status": 500, "merged": False, "merge_commit_sha": None,
                })
        poisoned = self.receipt.read_bytes()
        self.assertEqual(before + b"\x00", poisoned)
        self.assertEqual(0o600, self.receipt.stat().st_mode & 0o777)
        with self.assertRaises(receipts.MalformedReceiptError):
            receipts.record_attempt_finished(self.receipt, started, "failure", {
                "http_status": 500, "merged": False, "merge_commit_sha": None,
            })

    def test_finish_requires_byte_equivalent_stored_start_and_is_one_shot(self) -> None:
        started = self._start()
        changed = dict(started)
        changed["action_id"] = "act-other"
        with self.assertRaises(receipts.ReceiptBindingError):
            receipts.record_attempt_finished(self.receipt, changed, "failure", {
                "http_status": 409, "merged": False, "merge_commit_sha": None,
            })
        with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
            receipts.record_attempt_finished(self.receipt, started, "failure", {
                "http_status": 409, "merged": False, "merge_commit_sha": None,
            })
        with self.assertRaises(receipts.ReceiptReplayError):
            receipts.record_attempt_finished(self.receipt, started, "failure", {
                "http_status": 409, "merged": False, "merge_commit_sha": None,
            })

    def test_history_rejects_duplicate_or_orphan_rebound_unknown_and_truncated_rows(self) -> None:
        started = self._start()
        valid = self.receipt.read_bytes()
        row = json.loads(valid.decode())
        variants = []
        variants.append(valid + valid)
        orphan = dict(row)
        orphan.update(event_type="attempt_finished", attempt_started_event_id="event-" + "1" * 32,
                      outcome="failure", observation={"http_status": 409, "merged": False, "merge_commit_sha": None})
        variants.append(canonical.canonical_json_bytes(orphan) + b"\n")
        rebound = dict(row)
        rebound["consume_event_id"] = "event-" + "2" * 32
        variants.append(canonical.canonical_json_bytes(rebound) + b"\n")
        unknown = dict(row)
        unknown["unexpected"] = True
        variants.append(canonical.canonical_json_bytes(unknown) + b"\n")
        variants.append(valid.rstrip(b"\n"))
        for raw in variants:
            with self.subTest(raw=raw):
                self.receipt.write_bytes(raw)
                with self.assertRaises(receipts.ReceiptError):
                    with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
                        receipts.record_attempt_finished(self.receipt, started, "failure", {
                            "http_status": 409, "merged": False, "merge_commit_sha": None,
                        })
                self.receipt.write_bytes(valid)

    def test_timestamp_ordering_and_invalid_start_times_fail_closed(self) -> None:
        started = self._start()
        raw = json.loads(self.receipt.read_text())
        raw["recorded_at"] = "2026-08-22T09:59:59Z"
        self.receipt.write_bytes(canonical.canonical_json_bytes(raw) + b"\n")
        with self.assertRaises(receipts.ReceiptError):
            with mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)):
                receipts.record_attempt_finished(self.receipt, started, "failure", {
                    "http_status": 409, "merged": False, "merge_commit_sha": None,
                })

    def test_descriptor_identity_rejects_same_path_and_hardlink(self) -> None:
        with self.assertRaises(receipts.ReceiptPathError):
            self._start(receipt=self.authority)
        self._start()
        hardlink = self.receipt_dir / "hardlink.jsonl"
        os.link(self.authority, hardlink)
        with self.assertRaises(receipts.ReceiptPathError):
            self._start(receipt=hardlink)

    def test_short_write_and_fsync_failure_never_return_a_row_and_restore_bytes(self) -> None:
        started = self._start()
        before = self.receipt.read_bytes()
        original = action_authority_ledger._write_chunk
        calls = 0

        def short_then_fail(handle, raw):
            nonlocal calls
            calls += 1
            if calls == 1:
                return original(handle, raw[: max(1, len(raw) // 2)])
            raise OSError("synthetic short write")

        with mock.patch.object(action_authority_ledger, "_write_chunk", side_effect=short_then_fail):
            with self.assertRaises(receipts.ReceiptIOError):
                receipts.record_attempt_finished(self.receipt, started, "failure", {
                    "http_status": 409, "merged": False, "merge_commit_sha": None,
                })
        self.assertEqual(before, self.receipt.read_bytes())

        original_fsync = receipts._fsync
        fsync_calls = 0

        def fail_once(descriptor):
            nonlocal fsync_calls
            fsync_calls += 1
            if fsync_calls == 1:
                raise OSError("synthetic fsync")
            return original_fsync(descriptor)

        with mock.patch.object(receipts, "_fsync", side_effect=fail_once):
            with self.assertRaises(receipts.ReceiptIOError):
                receipts.record_attempt_finished(self.receipt, started, "failure", {
                    "http_status": 409, "merged": False, "merge_commit_sha": None,
                })
        self.assertEqual(before, self.receipt.read_bytes())

    def test_short_positive_writes_are_completed_by_write_all(self) -> None:
        started = self._start()
        original = action_authority_ledger._write_chunk
        calls = 0

        def short(handle, raw):
            nonlocal calls
            calls += 1
            return original(handle, raw[: max(1, len(raw) // 2)])

        with (
            mock.patch.object(action_authority_ledger, "_write_chunk", side_effect=short),
            mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)),
        ):
            finished = receipts.record_attempt_finished(self.receipt, started, "failure", {
                "http_status": 409, "merged": False, "merge_commit_sha": None,
            })
        self.assertEqual("attempt_finished", finished["event_type"])
        self.assertGreater(calls, 1)

    def test_event_id_collision_fails_once_without_retry(self) -> None:
        started = self._start()
        existing = started["event_id"]
        with (
            mock.patch.object(receipts.uuid, "uuid4", return_value=type("UUID", (), {"hex": existing.removeprefix("event-")})()),
            mock.patch.object(receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=4)),
        ):
            with self.assertRaises(receipts.ReceiptIOError):
                receipts.record_attempt_finished(self.receipt, started, "failure", {
                    "http_status": 409, "merged": False, "merge_commit_sha": None,
                })

    def test_concurrent_start_for_one_consume_has_exactly_one_winner(self) -> None:
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            try:
                return receipts.record_attempt_started(
                    self.receipt, self.authority, self.consume_event, self.action.action,
                )
            except Exception as exc:  # pragma: no cover - assertion below classifies it
                return exc

        # Patch the process-global clock once; per-thread patches can restore
        # another thread's mock and leak a stale clock into subsequent tests.
        with mock.patch.object(
            receipts, "_utc_now", return_value=BASE + datetime.timedelta(seconds=3)
        ), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), (1, 2)))
        self.assertEqual(1, sum(isinstance(item, dict) for item in results))
        self.assertEqual(1, sum(isinstance(item, receipts.ReceiptReplayError) for item in results))
        self.assertEqual(1, len(self._read()))


if __name__ == "__main__":
    unittest.main()
