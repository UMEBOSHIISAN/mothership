"""Closed authority-action ledger, durability, and contention tests."""

from __future__ import annotations

import copy
import datetime
import importlib
import inspect
import json
import multiprocessing
import os
import pathlib
import re
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from unittest import mock

from orchestration.lib import action_authority, canonical, contracts, jsonio


_TMP_ROOT = pathlib.Path(tempfile.gettempdir()).resolve() / "mothership-action-ledger-tests"
_EPOCH = datetime.datetime(2026, 8, 22, 10, 0, 0, tzinfo=datetime.UTC)
_PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}


def _load_ledger():
    try:
        return importlib.import_module("orchestration.lib.action_authority_ledger")
    except ModuleNotFoundError:
        return None


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain(item) for item in value]
    return value


def _consume_worker(ledger_path, approval_event_id, action_id, digest, result_path, barrier):
    ledger = importlib.import_module("orchestration.lib.action_authority_ledger")
    barrier.wait()
    try:
        ledger.consume_action(
            pathlib.Path(ledger_path), approval_event_id, action_id, digest
        )
        outcome = "ok"
    except ledger.ActionAuthorityLedgerError as exc:
        outcome = "rejected:" + type(exc).__name__
    pathlib.Path(result_path).write_text(outcome, encoding="utf-8")


class AuthorityActionLedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.ledger = _load_ledger()
        if self.ledger is None:
            self.fail("action_authority_ledger module is not implemented")
        _TMP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(_TMP_ROOT, 0o700)
        self._temporary = tempfile.TemporaryDirectory(dir=_TMP_ROOT)
        self.workdir = pathlib.Path(self._temporary.name)
        self.authority_dir = self.workdir / "authority-action"
        self.authority_dir.mkdir(mode=0o700)
        self.path = self.authority_dir / "events.jsonl"

    def tearDown(self):
        temporary = getattr(self, "_temporary", None)
        if temporary is not None:
            temporary.cleanup()
            _TMP_ROOT.rmdir()

    def freeze(
        self,
        *,
        action_id: str = "act-merge-pr-001",
        frozen_at: datetime.datetime = _EPOCH,
    ) -> action_authority.FrozenAction:
        with mock.patch.object(action_authority, "_utc_now", return_value=frozen_at):
            return action_authority.freeze_action(
                action_id,
                "github.merge_pr",
                copy.deepcopy(_PARAMETERS),
            )

    def record(
        self,
        frozen: action_authority.FrozenAction | None = None,
        *,
        decision: str = "approve",
        recorded_at: datetime.datetime = _EPOCH + datetime.timedelta(seconds=1),
    ) -> dict[str, object]:
        frozen = frozen or self.freeze()
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=recorded_at),
            mock.patch.object(self.ledger, "_utc_now", return_value=recorded_at),
        ):
            return self.ledger.record_action_decision(
                self.path,
                frozen,
                decision,
                frozen.action["action_id"],
                frozen.action_sha256,
            )

    def consume(
        self,
        approval: dict[str, object],
        *,
        consumed_at: datetime.datetime = _EPOCH + datetime.timedelta(seconds=2),
    ):
        with mock.patch.object(self.ledger, "_utc_now", return_value=consumed_at):
            return self.ledger.consume_action(
                self.path,
                approval["event_id"],
                approval["action"]["action_id"],
                approval["action_sha256"],
            )

    def read_events(self, path: pathlib.Path | None = None) -> list[dict[str, object]]:
        target = path or self.path
        if not target.exists() or not target.read_bytes():
            return []
        return [jsonio.loads_strict(line) for line in target.read_bytes().splitlines()]

    def write_events(self, events: list[dict[str, object]]) -> None:
        self.path.write_bytes(b"".join(canonical.canonical_json_bytes(event) + b"\n" for event in events))
        os.chmod(self.path, 0o600)

    def run_two(self, approval: dict[str, object]) -> tuple[str, str]:
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        result_a = self.workdir / "result-a.txt"
        result_b = self.workdir / "result-b.txt"
        args = (
            str(self.path),
            approval["event_id"],
            approval["action"]["action_id"],
            approval["action_sha256"],
        )
        process_a = context.Process(
            target=_consume_worker, args=(*args, str(result_a), barrier)
        )
        process_b = context.Process(
            target=_consume_worker, args=(*args, str(result_b), barrier)
        )
        process_a.start()
        process_b.start()
        try:
            process_a.join(15)
            process_b.join(15)
            self.assertFalse(process_a.is_alive(), "first child exceeded visible join cap")
            self.assertFalse(process_b.is_alive(), "second child exceeded visible join cap")
            self.assertEqual(0, process_a.exitcode)
            self.assertEqual(0, process_b.exitcode)
            return (
                result_a.read_text(encoding="utf-8"),
                result_b.read_text(encoding="utf-8"),
            )
        finally:
            for process in (process_a, process_b):
                if process.is_alive():
                    process.terminate()
                    process.join(5)


class DecisionRecordingTests(AuthorityActionLedgerTestCase):
    def test_recording_approve_and_reject_creates_only_closed_durable_events(self):
        frozen = self.freeze()
        approved = self.record(frozen, decision="approve")
        rejected = self.record(frozen, decision="reject")

        self.assertEqual(["approve", "reject"], [approved["decision"], rejected["decision"]])
        self.assertEqual([approved, rejected], self.read_events())
        for event in (approved, rejected):
            self.assertEqual(
                event,
                contracts.validate_contract("authority-action-approval", event),
            )
            self.assertRegex(event["event_id"], r"\Aevent-[0-9a-f]{32}\Z")
            self.assertRegex(event["action"]["action_id"], r"\Aact-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
        self.assertEqual(0o600, self.path.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.authority_dir.stat().st_mode & 0o777)

    def test_rejection_is_durable_but_never_consumable(self):
        rejection = self.record(decision="reject")
        before = self.path.read_bytes()
        with self.assertRaises(self.ledger.RejectedApprovalError):
            self.consume(rejection)
        self.assertEqual(before, self.path.read_bytes())

    def test_transport_binding_is_validated_before_any_event_append(self):
        frozen = self.freeze()
        invalid = (
            ("proceed", frozen.action["action_id"], frozen.action_sha256),
            ("approve", "act-merge-pr-stale", frozen.action_sha256),
            ("approve", frozen.action["action_id"], "f" * 64),
        )
        for decision, action_id, digest in invalid:
            with self.subTest(decision=decision, action_id=action_id, digest=digest):
                with (
                    mock.patch.object(action_authority, "_utc_now", return_value=_EPOCH),
                    mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH),
                    self.assertRaises(action_authority.ActionBindingError),
                ):
                    self.ledger.record_action_decision(
                        self.path, frozen, decision, action_id, digest
                    )
                self.assertEqual([], self.read_events())

    def test_approval_copies_core_owned_deadline_and_api_cannot_accept_expiry_or_now(self):
        frozen = self.freeze()
        event = self.record(frozen)
        self.assertEqual(frozen.expires_at, event["expires_at"])
        self.assertEqual(
            ("ledger_path", "frozen_action", "decision", "action_id", "action_sha256"),
            tuple(inspect.signature(self.ledger.record_action_decision).parameters),
        )
        with self.assertRaises(TypeError):
            self.ledger.record_action_decision(
                self.path,
                frozen,
                "approve",
                frozen.action["action_id"],
                frozen.action_sha256,
                expires_at="2099-01-01T00:00:00Z",
            )
        with self.assertRaises(TypeError):
            self.ledger.record_action_decision(
                self.path,
                frozen,
                "approve",
                frozen.action["action_id"],
                frozen.action_sha256,
                now=_EPOCH,
            )

    def test_record_revalidates_display_digest_deadline_and_policy_window(self):
        cases: list[tuple[str, object, type[Exception]]] = []
        altered_display = self.freeze()
        object.__setattr__(
            altered_display,
            "action",
            {
                **_plain(altered_display.action),
                "display": {
                    **_plain(altered_display.action["display"]),
                    "target": "safe-looking other target",
                },
            },
        )
        cases.append(("display", altered_display, action_authority.MalformedActionError))
        altered_digest = self.freeze()
        object.__setattr__(altered_digest, "action_sha256", "f" * 64)
        cases.append(("digest", altered_digest, action_authority.MalformedActionError))
        expired = self.freeze()
        cases.append(("expired", expired, action_authority.ExpiredActionError))
        too_long = self.freeze()
        object.__setattr__(too_long, "expires_at", "2026-08-22T10:10:01Z")
        cases.append(("policy-window", too_long, action_authority.MalformedActionError))

        for name, frozen, error in cases:
            now = _EPOCH + datetime.timedelta(minutes=11) if name == "expired" else _EPOCH
            with (
                self.subTest(name=name),
                mock.patch.object(action_authority, "_utc_now", return_value=now),
                mock.patch.object(self.ledger, "_utc_now", return_value=now),
                self.assertRaises(error),
            ):
                self.ledger.record_action_decision(
                    self.path,
                    frozen,
                    "approve",
                    frozen.action["action_id"],
                    frozen.action_sha256,
                )
            self.assertEqual([], self.read_events())

    def test_returned_approval_is_a_defensive_copy(self):
        frozen = self.freeze()
        returned = self.record(frozen)
        returned["decision"] = "reject"
        returned["action"]["execution_parameters"]["repository"] = "attacker/repository"
        stored = self.read_events()[0]
        self.assertEqual("approve", stored["decision"])
        self.assertEqual("UMEBOSHIISAN/mothership", stored["action"]["execution_parameters"]["repository"])
        self.assertEqual("UMEBOSHIISAN/mothership", frozen.action["execution_parameters"]["repository"])


class ConsumeTests(AuthorityActionLedgerTestCase):
    def test_consume_returns_exact_action_and_one_durable_closed_consume_event(self):
        approval = self.record()
        consume_event, action = self.consume(approval)
        events = self.read_events()

        self.assertEqual(consume_event, events[-1])
        self.assertEqual(approval["action"], action)
        self.assertEqual(
            consume_event,
            contracts.validate_contract("authority-action-consume", consume_event),
        )
        self.assertEqual(approval["event_id"], consume_event["approval_event_id"])
        self.assertEqual(approval["expires_at"], consume_event["expires_at"])
        self.assertEqual(approval["action_sha256"], consume_event["action_sha256"])
        self.assertEqual(1, sum(row["event_type"] == "authority_action_consume" for row in events))

    def test_returned_consume_event_and_action_are_defensive_copies(self):
        approval = self.record()
        consume_event, action = self.consume(approval)
        consume_event["action_id"] = "act-mutated"
        action["execution_parameters"]["repository"] = "attacker/repository"
        stored = self.read_events()
        self.assertEqual("act-merge-pr-001", stored[-1]["action_id"])
        self.assertEqual("UMEBOSHIISAN/mothership", stored[0]["action"]["execution_parameters"]["repository"])

    def test_missing_approval_and_mismatched_action_or_digest_fail_without_append(self):
        frozen = self.freeze()
        with self.assertRaises(self.ledger.MissingApprovalError):
            with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH):
                self.ledger.consume_action(
                    self.path,
                    "event-" + "a" * 32,
                    frozen.action["action_id"],
                    frozen.action_sha256,
                )
        approval = self.record(frozen)
        before = self.path.read_bytes()
        for action_id, digest in (
            ("act-merge-pr-other", frozen.action_sha256),
            (frozen.action["action_id"], "f" * 64),
        ):
            with self.subTest(action_id=action_id, digest=digest):
                with self.assertRaises(self.ledger.ApprovalMismatchError):
                    with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH):
                        self.ledger.consume_action(
                            self.path, approval["event_id"], action_id, digest
                        )
                self.assertEqual(before, self.path.read_bytes())

    def test_expiry_uses_core_time_and_caller_has_no_now_parameter(self):
        approval = self.record()
        self.assertEqual(
            ("ledger_path", "approval_event_id", "action_id", "action_sha256"),
            tuple(inspect.signature(self.ledger.consume_action).parameters),
        )
        expiry = datetime.datetime.strptime(
            approval["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=datetime.UTC)
        before = self.path.read_bytes()
        with mock.patch.object(self.ledger, "_utc_now", return_value=expiry):
            with self.assertRaises(self.ledger.ExpiredApprovalError):
                self.ledger.consume_action(
                    self.path,
                    approval["event_id"],
                    approval["action"]["action_id"],
                    approval["action_sha256"],
                )
        with self.assertRaises(TypeError):
            self.ledger.consume_action(
                self.path,
                approval["event_id"],
                approval["action"]["action_id"],
                approval["action_sha256"],
                now=_EPOCH,
            )
        self.assertEqual(before, self.path.read_bytes())

    def test_second_consume_is_typed_approval_replay_and_appends_nothing(self):
        approval = self.record()
        self.consume(approval)
        before = self.path.read_bytes()
        with self.assertRaises(self.ledger.ApprovalReplayError):
            self.consume(approval)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(1, sum(row["event_type"] == "authority_action_consume" for row in self.read_events()))

    def test_two_approvals_for_one_action_id_allow_only_one_action_consume(self):
        frozen = self.freeze()
        first = self.record(frozen)
        second = self.record(frozen)
        self.consume(first)
        before = self.path.read_bytes()
        with self.assertRaises(self.ledger.ActionReplayError):
            self.consume(second)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(1, sum(row["event_type"] == "authority_action_consume" for row in self.read_events()))

    def test_fsync_failure_returns_no_authority_and_is_not_retried(self):
        approval = self.record()
        calls = 0

        def fail(_descriptor):
            nonlocal calls
            calls += 1
            raise OSError("private")

        with mock.patch.object(self.ledger, "_fsync", side_effect=fail):
            with self.assertRaises(self.ledger.LedgerIOError):
                self.consume(approval)
        self.assertEqual(1, calls)

    def test_lock_covers_read_time_replay_checks_append_flush_and_fsync(self):
        approval = self.record()
        trace: list[str] = []
        originals = {
            "flock": self.ledger._flock,
            "read": self.ledger._read_locked,
            "append": self.ledger._append_on_locked_fd,
            "flush": self.ledger._flush,
            "fsync": self.ledger._fsync,
        }

        def flock(descriptor, operation):
            trace.append("lock" if operation == self.ledger.fcntl.LOCK_EX else "unlock")
            return originals["flock"](descriptor, operation)

        def read(descriptor):
            trace.append("read")
            return originals["read"](descriptor)

        def now():
            trace.append("now")
            return _EPOCH + datetime.timedelta(seconds=2)

        def append(descriptor, handle, events, event):
            trace.append("append")
            return originals["append"](descriptor, handle, events, event)

        def flush(handle):
            trace.append("flush")
            return originals["flush"](handle)

        def fsync(descriptor):
            trace.append("fsync")
            return originals["fsync"](descriptor)

        with (
            mock.patch.object(self.ledger, "_flock", side_effect=flock),
            mock.patch.object(self.ledger, "_read_locked", side_effect=read),
            mock.patch.object(self.ledger, "_utc_now", side_effect=now),
            mock.patch.object(self.ledger, "_append_on_locked_fd", side_effect=append),
            mock.patch.object(self.ledger, "_flush", side_effect=flush),
            mock.patch.object(self.ledger, "_fsync", side_effect=fsync),
        ):
            self.ledger.consume_action(
                self.path,
                approval["event_id"],
                approval["action"]["action_id"],
                approval["action_sha256"],
            )
        self.assertEqual(
            ["lock", "read", "now", "append", "flush", "fsync", "unlock"],
            trace,
        )

    def test_legacy_deploy_authority_is_neither_emitted_nor_accepted(self):
        frozen = self.freeze()
        with (
            mock.patch.object(action_authority, "_utc_now", return_value=_EPOCH),
            mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH),
            self.assertRaises(action_authority.ActionBindingError),
        ):
            self.ledger.record_action_decision(
                self.path,
                frozen,
                "DEPLOY_APPROVED:production",
                frozen.action["action_id"],
                frozen.action_sha256,
            )
        approval = self.record(frozen)
        with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH):
            with self.assertRaises(self.ledger.ApprovalMismatchError):
                self.ledger.consume_action(
                    self.path,
                    approval["event_id"],
                    "DEPLOY_APPROVED:production",
                    approval["action_sha256"],
                )
        consume_event, action = self.consume(approval)
        emitted = json.dumps([approval, consume_event, action], sort_keys=True)
        self.assertNotIn("DEPLOY_APPROVED", emitted)


class LedgerStateValidationTests(AuthorityActionLedgerTestCase):
    def test_malformed_empty_truncated_utf8_duplicate_mixed_and_unknown_rows_fail_closed(self):
        frozen = self.freeze()
        legacy = {
            "schema_version": "0.1.0",
            "event_type": "approval_granted",
            "event_id": "event-" + "1" * 32,
        }
        unknown = {
            "schema_version": "authority-action-diagnostic.v0",
            "event_type": "diagnostic",
            "event_id": "event-" + "2" * 32,
        }
        states = {
            "malformed-json": b"{not-json}\n",
            "empty-object": b"{}\n",
            "empty-line": b"\n",
            "truncated": b"{}",
            "invalid-utf8": b"{\"x\":\"\xff\"}\n",
            "duplicate-key": b'{"schema_version":"authority-action-approval.v0","schema_version":"authority-action-approval.v0"}\n',
            "mixed-schema": canonical.canonical_json_bytes(legacy) + b"\n",
            "unknown-event": canonical.canonical_json_bytes(unknown) + b"\n",
            "partial-final-line": b"{}\n{",
        }
        for name, raw in states.items():
            with self.subTest(name=name):
                self.path.write_bytes(raw)
                os.chmod(self.path, 0o600)
                with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH):
                    with self.assertRaises(self.ledger.MalformedLedgerStateError):
                        self.ledger.consume_action(
                            self.path,
                            "event-" + "a" * 32,
                            frozen.action["action_id"],
                            frozen.action_sha256,
                        )

    def test_malformed_action_and_invalid_event_or_action_ids_fail_closed(self):
        approval = self.record()
        variants = []
        malformed_action = copy.deepcopy(approval)
        malformed_action["action"]["display"]["target"] = "PR #999 -> main"
        variants.append(malformed_action)
        invalid_event_id = copy.deepcopy(approval)
        invalid_event_id["event_id"] = "event-not-closed"
        variants.append(invalid_event_id)
        invalid_action_id = copy.deepcopy(approval)
        invalid_action_id["action"]["action_id"] = "DEPLOY_APPROVED:production"
        variants.append(invalid_action_id)

        for event in variants:
            with self.subTest(event=event):
                self.write_events([event])
                with self.assertRaises(self.ledger.MalformedLedgerStateError):
                    self.ledger.consume_action(
                        self.path,
                        approval["event_id"],
                        approval["action"]["action_id"],
                        approval["action_sha256"],
                    )

    def test_cross_event_mismatched_expiry_digest_action_and_relationships_fail_closed(self):
        approval = self.record()
        consume_event, _ = self.consume(approval)
        variants = []
        for field, value in (
            ("expires_at", "2026-08-22T10:09:59Z"),
            ("action_sha256", "f" * 64),
            ("action_id", "act-merge-pr-other"),
            ("approval_event_id", "event-" + "f" * 32),
        ):
            changed = copy.deepcopy(consume_event)
            changed[field] = value
            variants.append(changed)
        duplicate_id = copy.deepcopy(consume_event)
        duplicate_id["event_id"] = approval["event_id"]
        variants.append(duplicate_id)

        for event in variants:
            with self.subTest(event=event):
                self.write_events([approval, event])
                with self.assertRaises(self.ledger.MalformedLedgerStateError):
                    self.ledger.consume_action(
                        self.path,
                        approval["event_id"],
                        approval["action"]["action_id"],
                        approval["action_sha256"],
                    )


class LocalFileSafetyTests(AuthorityActionLedgerTestCase):
    def test_path_must_be_one_explicit_normalized_absolute_path(self):
        frozen = self.freeze()
        invalid = (
            pathlib.Path("relative/events.jsonl"),
            str(self.path),
            pathlib.Path(os.path.sep),
            pathlib.Path(os.fspath(self.workdir) + "/authority-action/../events.jsonl"),
        )
        for path in invalid:
            with self.subTest(path=path):
                with self.assertRaises(self.ledger.LedgerIOError):
                    self.ledger.record_action_decision(
                        path,
                        frozen,
                        "approve",
                        frozen.action["action_id"],
                        frozen.action_sha256,
                    )

    def test_parent_directory_must_be_real_directory_mode_0700(self):
        frozen = self.freeze()
        os.chmod(self.authority_dir, 0o755)
        with self.assertRaises(self.ledger.LedgerIOError):
            self.ledger.record_action_decision(
                self.path,
                frozen,
                "approve",
                frozen.action["action_id"],
                frozen.action_sha256,
            )

        real = self.workdir / "real-authority-action"
        real.mkdir(mode=0o700)
        linked = self.workdir / "linked-authority-action"
        linked.symlink_to(real, target_is_directory=True)
        with self.assertRaises(self.ledger.LedgerIOError):
            self.ledger.record_action_decision(
                linked / "events.jsonl",
                frozen,
                "approve",
                frozen.action["action_id"],
                frozen.action_sha256,
            )

    def test_ledger_must_be_regular_non_symlink_file_mode_0600(self):
        frozen = self.freeze()
        self.path.write_text("", encoding="utf-8")
        os.chmod(self.path, 0o644)
        with self.assertRaises(self.ledger.LedgerIOError):
            self.record(frozen)

        self.path.unlink()
        backing = self.authority_dir / "backing.jsonl"
        backing.write_text("", encoding="utf-8")
        os.chmod(backing, 0o600)
        self.path.symlink_to(backing)
        with self.assertRaises(self.ledger.LedgerIOError):
            self.record(frozen)

        self.path.unlink()
        os.mkfifo(self.path, mode=0o600)
        with self.assertRaises(self.ledger.LedgerIOError):
            self.record(frozen)


class ProcessContentionTests(AuthorityActionLedgerTestCase):
    def test_two_spawned_consumers_produce_one_success_and_one_typed_replay(self):
        frozen = action_authority.freeze_action(
            "act-concurrent-001",
            "github.merge_pr",
            copy.deepcopy(_PARAMETERS),
        )
        approval = self.ledger.record_action_decision(
            self.path,
            frozen,
            "approve",
            frozen.action["action_id"],
            frozen.action_sha256,
        )
        outcome_a, outcome_b = self.run_two(approval)
        self.assertEqual(1, [outcome_a, outcome_b].count("ok"))
        self.assertEqual(
            1,
            [outcome_a, outcome_b].count("rejected:ApprovalReplayError"),
        )
        self.assertEqual(
            1,
            sum(
                event["event_type"] == "authority_action_consume"
                for event in self.read_events()
            ),
        )


if __name__ == "__main__":
    unittest.main()
