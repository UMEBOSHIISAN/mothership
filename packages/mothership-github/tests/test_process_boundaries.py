"""Process-boundary evidence for the existing companion execution lifecycle."""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mothership.contracts import ContractError
from orchestration.lib.action_authority import freeze_action
from orchestration.lib.action_authority_ledger import (
    ApprovalReplayError,
    record_action_decision,
)
from mothership_github import executor
from mothership_github.external_action import build_external_action_receipt


PARAMETERS = {
    "repository": "owner/repo",
    "pull_request": 7,
    "expected_head_sha": "a" * 40,
    "expected_base": "main",
    "merge_method": "merge",
}
GOOD_OBSERVATION = {
    "http_status": 200,
    "merged": True,
    "merge_commit_sha": "b" * 40,
}
EFFECT_MARKER = b"fake-effect\n"
EXIT_AFTER_CONSUME = 71
EXIT_AFTER_START = 72
EXIT_AFTER_EFFECT = 73


class _LocalTransport:
    def __init__(
        self,
        marker: Path,
        *,
        mode: str,
        barrier: multiprocessing.synchronize.Barrier | None = None,
    ) -> None:
        self.marker = marker
        self.mode = mode
        self.barrier = barrier

    def get_pull_request(self, repository: str, pull_request: int) -> dict[str, object]:
        if repository != PARAMETERS["repository"] or pull_request != PARAMETERS["pull_request"]:
            raise AssertionError("preflight received a changed action target")
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return {
            "http_status": 200,
            "state": "open",
            "merged": False,
            "head_sha": PARAMETERS["expected_head_sha"],
            "base_ref": PARAMETERS["expected_base"],
        }

    def _record_effect(self) -> None:
        with self.marker.open("ab") as handle:
            handle.write(EFFECT_MARKER)
            handle.flush()
            os.fsync(handle.fileno())

    def merge_pull_request(self, **kwargs: object) -> dict[str, object]:
        expected = {
            "repository": PARAMETERS["repository"],
            "pull_request": PARAMETERS["pull_request"],
            "expected_head_sha": PARAMETERS["expected_head_sha"],
            "merge_method": PARAMETERS["merge_method"],
        }
        if kwargs != expected:
            raise AssertionError("mutation received a changed action target")
        if self.mode in {"effect-and-exit", "success"}:
            self._record_effect()
        if self.mode == "effect-and-exit":
            os._exit(EXIT_AFTER_EFFECT)
        if self.mode == "success":
            return dict(GOOD_OBSERVATION)
        raise AssertionError("unknown local transport mode")


def _child_after_consume(
    authority_path: str,
    receipt_path: str,
    action: object,
    approval_event_id: str,
    marker: str,
) -> None:
    transport = _LocalTransport(Path(marker), mode="success")

    def stop_before_start(*_args: object, **_kwargs: object) -> None:
        os._exit(EXIT_AFTER_CONSUME)

    with mock.patch.object(executor, "record_attempt_started", stop_before_start):
        executor.execute_action_merge_pr(
            Path(authority_path),
            Path(receipt_path),
            action,
            approval_event_id,
            transport,
        )


def _child_after_start(
    authority_path: str,
    receipt_path: str,
    action: object,
    approval_event_id: str,
    marker: str,
) -> None:
    transport = _LocalTransport(Path(marker), mode="success")
    original_start = executor.record_attempt_started

    def start_then_exit(*args: object, **kwargs: object) -> None:
        original_start(*args, **kwargs)
        os._exit(EXIT_AFTER_START)

    with mock.patch.object(executor, "record_attempt_started", start_then_exit):
        executor.execute_action_merge_pr(
            Path(authority_path),
            Path(receipt_path),
            action,
            approval_event_id,
            transport,
        )


def _child_after_effect(
    authority_path: str,
    receipt_path: str,
    action: object,
    approval_event_id: str,
    marker: str,
) -> None:
    transport = _LocalTransport(Path(marker), mode="effect-and-exit")
    executor.execute_action_merge_pr(
        Path(authority_path),
        Path(receipt_path),
        action,
        approval_event_id,
        transport,
    )


def _race_worker(
    authority_path: str,
    receipt_path: str,
    action: object,
    approval_event_id: str,
    marker: str,
    barrier: multiprocessing.synchronize.Barrier,
    result_path: str,
) -> None:
    transport = _LocalTransport(Path(marker), mode="success", barrier=barrier)
    try:
        result = executor.execute_action_merge_pr(
            Path(authority_path),
            Path(receipt_path),
            action,
            approval_event_id,
            transport,
        )
    except ApprovalReplayError:
        Path(result_path).write_text("rejected:ApprovalReplayError\n", encoding="utf-8")
        return
    if result.get("status") != "success":
        raise AssertionError("successful race child returned a non-success result")
    Path(result_path).write_text("success\n", encoding="utf-8")


class ProcessBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        if "fork" not in multiprocessing.get_all_start_methods():
            self.skipTest("POSIX fork is required for issuance-lineage evidence")
        self.context = multiprocessing.get_context("fork")
        self.temporary = tempfile.TemporaryDirectory(prefix="mothership-process-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.authority = self.root / "authority.jsonl"
        self.attempts = self.root / "attempts.jsonl"
        self.marker = self.root / "effects.log"
        self.action = freeze_action("act-process-boundary", "github.merge_pr", dict(PARAMETERS))
        self.approval = record_action_decision(
            self.authority,
            self.action,
            "approve",
            self.action.action["action_id"],
            self.action.action_sha256,
        )

    @staticmethod
    def _rows(path: Path) -> list[dict[str, object]]:
        if not path.exists() or not path.read_bytes():
            return []
        return [json.loads(line) for line in path.read_bytes().splitlines()]

    def _join_one(self, process: multiprocessing.process.BaseProcess, expected_exit: int) -> None:
        started = False
        try:
            process.start()
            started = True
            process.join(10)
            self.assertFalse(process.is_alive(), "child exceeded the bounded join timeout")
            self.assertEqual(expected_exit, process.exitcode)
        finally:
            if started and process.is_alive():
                process.terminate()
            if started:
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                self.assertFalse(process.is_alive(), "child could not be cleaned up")

    def _join_race(self, processes: tuple[multiprocessing.process.BaseProcess, ...]) -> None:
        started: list[multiprocessing.process.BaseProcess] = []
        try:
            for process in processes:
                process.start()
                started.append(process)
            for process in started:
                process.join(10)
                self.assertFalse(process.is_alive(), "race child exceeded the bounded join timeout")
                self.assertEqual(0, process.exitcode)
        finally:
            for process in started:
                if process.is_alive():
                    process.terminate()
            for process in started:
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
            for process in started:
                self.assertFalse(process.is_alive(), "race child could not be cleaned up")

    def _assert_authority(self) -> dict[str, object]:
        rows = self._rows(self.authority)
        self.assertEqual(2, len(rows))
        self.assertEqual(self.approval, rows[0])
        consume = rows[1]
        self.assertEqual("authority-action-consume.v0", consume["schema_version"])
        self.assertEqual("authority_action_consume", consume["event_type"])
        self.assertEqual(self.approval["event_id"], consume["approval_event_id"])
        self.assertEqual(self.action.action["action_id"], consume["action_id"])
        self.assertEqual(self.action.action_sha256, consume["action_sha256"])
        return consume

    def _assert_started(self, consume: dict[str, object]) -> dict[str, object]:
        rows = self._rows(self.attempts)
        self.assertEqual(1, len(rows))
        started = rows[0]
        self.assertEqual("attempt_started", started["event_type"])
        self.assertEqual(self.action.action["action_id"], started["action_id"])
        self.assertEqual(self.action.action_sha256, started["action_sha256"])
        self.assertEqual(consume["event_id"], started["consume_event_id"])
        return started

    def _assert_complete(self, consume: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
        rows = self._rows(self.attempts)
        self.assertEqual(2, len(rows))
        started, finished = rows
        self.assertEqual("attempt_started", started["event_type"])
        self.assertEqual("attempt_finished", finished["event_type"])
        self.assertEqual(consume["event_id"], started["consume_event_id"])
        self.assertEqual(consume["event_id"], finished["consume_event_id"])
        self.assertEqual(self.action.action["action_id"], started["action_id"])
        self.assertEqual(self.action.action_sha256, started["action_sha256"])
        self.assertEqual(started["event_id"], finished["attempt_started_event_id"])
        self.assertEqual(self.action.action["action_id"], finished["action_id"])
        self.assertEqual(self.action.action_sha256, finished["action_sha256"])
        self.assertEqual("success", finished["outcome"])
        self.assertEqual(GOOD_OBSERVATION, finished["observation"])
        return started, finished

    def _assert_incomplete_adapter_rejected(
        self,
        started: dict[str, object] | None,
        consume: dict[str, object],
    ) -> None:
        with self.assertRaises(ContractError):
            build_external_action_receipt(
                started,
                None,
                expected_action_id=self.action.action["action_id"],
                expected_action_sha256=self.action.action_sha256,
                expected_consume_event_id=consume["event_id"],
                executor_ref={"ref_id": "executor:process-boundary", "sha256": "c" * 64},
            )

    def _assert_replay_rejected(self) -> None:
        authority_before = self.authority.read_bytes()
        attempts_before = self.attempts.read_bytes() if self.attempts.exists() else None
        marker_before = self.marker.read_bytes() if self.marker.exists() else None
        replay_transport = _LocalTransport(self.marker, mode="success")
        with self.assertRaises(ApprovalReplayError):
            executor.execute_action_merge_pr(
                self.authority,
                self.attempts,
                self.action,
                self.approval["event_id"],
                replay_transport,
            )
        self.assertEqual(authority_before, self.authority.read_bytes())
        self.assertEqual(attempts_before, self.attempts.read_bytes() if self.attempts.exists() else None)
        self.assertEqual(marker_before, self.marker.read_bytes() if self.marker.exists() else None)

    def test_child_exit_after_consume_before_start_leaves_only_consumption(self) -> None:
        process = self.context.Process(
            target=_child_after_consume,
            args=(str(self.authority), str(self.attempts), self.action, self.approval["event_id"], str(self.marker)),
        )
        self._join_one(process, EXIT_AFTER_CONSUME)
        consume = self._assert_authority()
        self.assertEqual([], self._rows(self.attempts))
        self.assertEqual(b"", self.marker.read_bytes() if self.marker.exists() else b"")
        self._assert_incomplete_adapter_rejected(None, consume)
        self._assert_replay_rejected()

    def test_child_exit_after_start_before_put_leaves_one_incomplete_start(self) -> None:
        process = self.context.Process(
            target=_child_after_start,
            args=(str(self.authority), str(self.attempts), self.action, self.approval["event_id"], str(self.marker)),
        )
        self._join_one(process, EXIT_AFTER_START)
        consume = self._assert_authority()
        started = self._assert_started(consume)
        self.assertEqual(b"", self.marker.read_bytes() if self.marker.exists() else b"")
        self._assert_incomplete_adapter_rejected(started, consume)
        self._assert_replay_rejected()

    def test_child_exit_after_durable_effect_before_finish_leaves_one_incomplete_start(self) -> None:
        process = self.context.Process(
            target=_child_after_effect,
            args=(str(self.authority), str(self.attempts), self.action, self.approval["event_id"], str(self.marker)),
        )
        self._join_one(process, EXIT_AFTER_EFFECT)
        consume = self._assert_authority()
        started = self._assert_started(consume)
        self.assertEqual(EFFECT_MARKER, self.marker.read_bytes())
        self._assert_incomplete_adapter_rejected(started, consume)
        self._assert_replay_rejected()

    def test_two_process_race_has_one_consume_start_finish_and_effect(self) -> None:
        barrier = self.context.Barrier(2)
        result_a = self.root / "race-a.txt"
        result_b = self.root / "race-b.txt"
        args = (
            str(self.authority),
            str(self.attempts),
            self.action,
            self.approval["event_id"],
            str(self.marker),
            barrier,
        )
        processes = (
            self.context.Process(target=_race_worker, args=(*args, str(result_a))),
            self.context.Process(target=_race_worker, args=(*args, str(result_b))),
        )
        self._join_race(processes)
        self.assertEqual(
            ["rejected:ApprovalReplayError", "success"],
            sorted((result_a.read_text(encoding="utf-8").strip(), result_b.read_text(encoding="utf-8").strip())),
        )
        consume = self._assert_authority()
        started, _finished = self._assert_complete(consume)
        self.assertEqual(EFFECT_MARKER, self.marker.read_bytes())
        self._assert_incomplete_adapter_rejected(started, consume)
        self._assert_replay_rejected()


if __name__ == "__main__":
    unittest.main()
