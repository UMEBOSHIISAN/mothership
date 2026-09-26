"""Acceptance tests for the human-operated reference consumer."""

from __future__ import annotations

import copy
import datetime
import getpass
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings

from examples import github_merge_reference as reference
from mothership_github import receipts
from orchestration.lib import action_authority as core_action_authority
from orchestration.lib import action_authority_ledger


_HEAD = "a" * 40
_OTHER_HEAD = "b" * 40
_MERGE_SHA = "c" * 40


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class ApprovalInput(TTYBuffer):
    def __init__(self, output: TTYBuffer, decision: str = "approve", on_read=None):
        super().__init__()
        self._output = output
        self._decision = decision
        self._on_read = on_read

    def readline(self, *args, **kwargs):
        if self._on_read is not None:
            self._on_read()
        rows = [json.loads(line) for line in self._output.getvalue().splitlines() if line]
        frozen = next(row for row in rows if row.get("event") == "frozen_action")
        return (
            f"{self._decision} {frozen['action']['action_id']} "
            f"{frozen['action_sha256']}\n"
        )


class FakeTransport:
    def __init__(self, mutation=None, *, snapshots=None):
        self.snapshots = snapshots or [
            {
                "http_status": 200,
                "state": "open",
                "merged": False,
                "head_sha": _HEAD,
                "base_ref": "main",
            }
        ]
        self.mutation = (
            mutation
            if mutation is not None
            else {
                "http_status": 200,
                "merged": True,
                "merge_commit_sha": _MERGE_SHA,
            }
        )
        self.get_calls: list[tuple[str, int]] = []
        self.put_calls: list[dict[str, object]] = []

    def get_pull_request(self, repository: str, pull_request: int):
        self.get_calls.append((repository, pull_request))
        index = min(len(self.get_calls) - 1, len(self.snapshots) - 1)
        return copy.deepcopy(self.snapshots[index])

    def merge_pull_request(self, **kwargs):
        self.put_calls.append(copy.deepcopy(kwargs))
        if isinstance(self.mutation, BaseException):
            raise self.mutation
        return copy.deepcopy(self.mutation)


class ReferenceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reference-runner-")
        self.root = Path(self.temp.name).resolve()
        self.ledger_dir = self.root / "ledger"
        self.ledger_dir.mkdir(mode=0o700)
        os.chmod(self.ledger_dir, 0o700)

    def tearDown(self):
        self.temp.cleanup()

    def run_runner(
        self,
        transport,
        *,
        decision="approve",
        argv=None,
        input_stream=None,
        output=None,
    ):
        output = TTYBuffer() if output is None else output
        if input_stream is None:
            input_stream = ApprovalInput(output, decision)
        arguments = argv or [
            "--pr",
            "7",
            "--ledger-dir",
            str(self.ledger_dir),
            "--merge-method",
            "merge",
        ]
        code = reference.main(
            arguments,
            transport=transport,
            input_stream=input_stream,
            output_stream=output,
        )
        return code, output.getvalue()

    @staticmethod
    def rows(text: str) -> list[dict[str, object]]:
        return [json.loads(line) for line in text.splitlines() if line]

    def test_approval_uses_real_core_ledgers_and_executor_once(self):
        transport = FakeTransport()

        code, output = self.run_runner(transport)

        self.assertEqual(0, code)
        self.assertEqual(2, len(transport.get_calls))
        self.assertEqual(1, len(transport.put_calls))
        self.assertEqual(
            {
                "repository": "UMEBOSHIISAN/mothership",
                "pull_request": 7,
                "expected_head_sha": _HEAD,
                "merge_method": "merge",
            },
            transport.put_calls[0],
        )
        rows = self.rows(output)
        self.assertEqual("success", rows[-1]["status"])
        self.assertEqual(2, len((self.ledger_dir / "authority.jsonl").read_text().splitlines()))
        self.assertEqual(2, len((self.ledger_dir / "attempts.jsonl").read_text().splitlines()))

    def test_rejection_records_decision_without_consuming_or_executing(self):
        transport = FakeTransport()

        code, output = self.run_runner(transport, decision="reject")

        self.assertEqual(0, code)
        self.assertEqual([], transport.put_calls)
        self.assertEqual(1, len(transport.get_calls))
        rows = self.rows(output)
        self.assertEqual("rejected", rows[-1]["status"])
        self.assertEqual(1, len((self.ledger_dir / "authority.jsonl").read_text().splitlines()))
        self.assertFalse((self.ledger_dir / "attempts.jsonl").exists())

    def test_contradictory_executor_outcomes_require_reconciliation(self):
        cases = (
            ("success", 503, None, None),
            ("success", 200, False, _MERGE_SHA),
            ("success", 200, None, _MERGE_SHA),
            ("success", 200, True, None),
            ("failure", 409, True, None),
            ("failure", 409, False, _MERGE_SHA),
        )
        for status, http_status, merged, sha in cases:
            with self.subTest(status=status, http_status=http_status, merged=merged, sha=sha):
                payload, code = reference._execution_payload(
                    {"status": status, "http_status": http_status,
                     "merged": merged, "merge_commit_sha": sha},
                    self.ledger_dir,
                )
                self.assertEqual(1, code)
                self.assertEqual("reconciliation_required", payload["status"])

    def test_invalid_http_status_is_not_displayed_as_a_normalized_observation(self):
        for http_status in (1, 99):
            with self.subTest(http_status=http_status):
                payload, code = reference._execution_payload(
                    {"status": "reconciliation_required", "http_status": http_status,
                     "merged": None, "merge_commit_sha": None},
                    self.ledger_dir,
                )
                self.assertEqual(1, code)
                self.assertEqual("reconciliation_required", payload["status"])
                self.assertNotIn("http_status", payload)

    def test_explicit_reconciliation_is_not_promoted_by_apparent_success_facts(self):
        payload, code = reference._execution_payload(
            {"status": "reconciliation_required", "http_status": 200,
             "merged": True, "merge_commit_sha": _MERGE_SHA},
            self.ledger_dir,
        )
        self.assertEqual(1, code)
        self.assertEqual("reconciliation_required", payload["status"])
        self.assertEqual(_MERGE_SHA, payload["merge_commit_sha"])

    def test_inconsistent_executor_summary_stops_after_one_durable_attempt(self):
        transport = FakeTransport()
        execute = reference.executor.execute_action_merge_pr

        def inconsistent_summary(*args, **kwargs):
            result = execute(*args, **kwargs)
            # Preserve the real consume, receipts, and PUT. Corrupt only the
            # returned summary at the consumer boundary being checked.
            return {**result, "http_status": 503}

        with mock.patch.object(reference.executor, "execute_action_merge_pr", side_effect=inconsistent_summary):
            code, output = self.run_runner(transport)

        self.assertEqual(1, code)
        self.assertEqual("reconciliation_required", self.rows(output)[-1]["status"])
        self.assertEqual(1, len(transport.put_calls))
        authority = self.rows((self.ledger_dir / "authority.jsonl").read_text())
        attempts = self.rows((self.ledger_dir / "attempts.jsonl").read_text())
        self.assertEqual(2, len(authority))
        self.assertEqual(2, len(attempts))
        self.assertEqual("success", attempts[-1]["outcome"])

    def test_wrong_action_bound_approval_is_rejected_without_record_or_execute(self):
        transport = FakeTransport()
        output = TTYBuffer()

        class WrongApproval(TTYBuffer):
            def readline(self, *args, **kwargs):
                rows = [json.loads(line) for line in output.getvalue().splitlines() if line]
                frozen = next(row for row in rows if row.get("event") == "frozen_action")
                return f"approve {frozen['action']['action_id']} {'0' * 64}\n"

        code, output_text = self.run_runner(
            transport,
            input_stream=WrongApproval(),
            output=output,
        )

        self.assertEqual(0, code)
        self.assertEqual([], transport.put_calls)
        self.assertEqual("approval_mismatch", self.rows(output_text)[-1]["reason"])
        self.assertFalse((self.ledger_dir / "authority.jsonl").exists())

    def test_eof_and_interrupt_do_not_record_or_execute(self):
        for stream in (TTYBuffer(""),):
            transport = FakeTransport()
            code, output = self.run_runner(transport, input_stream=stream)
            self.assertEqual(0, code)
            self.assertEqual([], transport.put_calls)
            self.assertEqual("approval_eof", self.rows(output)[-1]["reason"])
            self.assertFalse((self.ledger_dir / "authority.jsonl").exists())

        self.ledger_dir = self.root / "interrupt-ledger"
        self.ledger_dir.mkdir(mode=0o700)
        os.chmod(self.ledger_dir, 0o700)
        transport = FakeTransport()
        output = TTYBuffer()

        class InterruptInput(TTYBuffer):
            def readline(self, *args, **kwargs):
                raise KeyboardInterrupt

        code = reference.main(
            ["--pr", "7", "--ledger-dir", str(self.ledger_dir)],
            transport=transport,
            input_stream=InterruptInput(),
            output_stream=output,
        )
        self.assertEqual(0, code)
        self.assertEqual("approval_interrupted", self.rows(output.getvalue())[-1]["reason"])
        self.assertFalse((self.ledger_dir / "authority.jsonl").exists())
        self.assertEqual([], transport.put_calls)

    def test_expired_action_is_a_pre_execution_failure(self):
        transport = FakeTransport()
        output = TTYBuffer()
        clock = [datetime.datetime(2026, 9, 21, 10, 0, tzinfo=datetime.UTC)]

        def expire_before_record():
            clock[0] += datetime.timedelta(minutes=11)

        with (
            mock.patch.object(core_action_authority, "_utc_now", side_effect=lambda: clock[0]),
            mock.patch.object(action_authority_ledger, "_utc_now", side_effect=lambda: clock[0]),
        ):
            code, output_text = self.run_runner(
                transport,
                input_stream=ApprovalInput(output, on_read=expire_before_record),
                output=output,
            )

        self.assertEqual(1, code)
        self.assertEqual([], transport.put_calls)
        self.assertEqual("pre_execution_failure", self.rows(output_text)[-1]["status"])

    def test_changed_head_or_base_after_freeze_stops_before_put(self):
        for changed in (
            {"head_sha": _OTHER_HEAD},
            {"base_ref": "release"},
        ):
            with self.subTest(changed=changed):
                self.ledger_dir = self.root / ("changed-" + next(iter(changed)))
                self.ledger_dir.mkdir(mode=0o700)
                os.chmod(self.ledger_dir, 0o700)
                second = {
                    "http_status": 200,
                    "state": "open",
                    "merged": False,
                    "head_sha": _HEAD,
                    "base_ref": "main",
                }
                second.update(changed)
                transport = FakeTransport(snapshots=[FakeTransport().snapshots[0], second])

                code, output = self.run_runner(transport)

                self.assertEqual(1, code)
                self.assertEqual([], transport.put_calls)
                self.assertEqual("reconciliation_required", self.rows(output)[-1]["status"])

    def test_timeout_and_ambiguous_mutation_are_reconciliation_required(self):
        for index, mutation in enumerate(
            (
                TimeoutError("synthetic timeout"),
                KeyboardInterrupt(),
                {"http_status": 409, "merged": True, "merge_commit_sha": _MERGE_SHA},
            )
        ):
            with self.subTest(mutation=mutation):
                self.ledger_dir = self.root / f"mutation-{index}"
                self.ledger_dir.mkdir(mode=0o700)
                os.chmod(self.ledger_dir, 0o700)
                transport = FakeTransport(mutation)

                code, output = self.run_runner(transport)

                self.assertEqual(1, code)
                self.assertEqual(1, len(transport.put_calls))
                self.assertEqual("reconciliation_required", self.rows(output)[-1]["status"])

    def test_receipt_start_failure_is_reconciliation_required_without_raw_error(self):
        transport = FakeTransport()
        with mock.patch.object(receipts, "_fsync", side_effect=OSError("secret-start-error")):
            code, output = self.run_runner(transport)

        self.assertEqual(1, code)
        self.assertEqual([], transport.put_calls)
        final = self.rows(output)[-1]
        self.assertEqual("reconciliation_required", final["status"])
        self.assertNotIn("secret-start-error", output)

    def test_receipt_finish_failure_is_reconciliation_required_after_one_put(self):
        transport = FakeTransport()
        original = receipts._fsync
        calls = 0

        def fsync_once_then_fail(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("secret-finish-error")
            return original(fd)

        with mock.patch.object(receipts, "_fsync", side_effect=fsync_once_then_fail):
            code, output = self.run_runner(transport)

        self.assertEqual(1, code)
        self.assertEqual(1, len(transport.put_calls))
        self.assertEqual("reconciliation_required", self.rows(output)[-1]["status"])
        self.assertNotIn("secret-finish-error", output)

    def test_final_result_display_failure_returns_nonzero_after_one_put(self):
        transport = FakeTransport()

        class FailingFinalOutput(TTYBuffer):
            def write(self, value):
                if '"event":"execution_result"' in value:
                    raise OSError("display failed")
                return super().write(value)

        output = FailingFinalOutput()
        code, _ = self.run_runner(transport, output=output)

        self.assertEqual(1, code)
        self.assertEqual(1, len(transport.put_calls))

    def test_second_invocation_refuses_existing_session_without_get(self):
        first_transport = FakeTransport()
        self.assertEqual(0, self.run_runner(first_transport)[0])
        second_transport = FakeTransport()

        output = TTYBuffer()
        code = reference.main(
            ["--pr", "7", "--ledger-dir", str(self.ledger_dir)],
            transport=second_transport,
            input_stream=TTYBuffer(""),
            output_stream=output,
        )

        self.assertEqual(1, code)
        self.assertEqual([], second_transport.get_calls)
        self.assertEqual("pre_execution_failure", self.rows(output.getvalue())[-1]["status"])

    def test_frozen_display_and_paths_are_json_escaped(self):
        self.ledger_dir = self.root / "ledger\nwith-control"
        self.ledger_dir.mkdir(mode=0o700)
        os.chmod(self.ledger_dir, 0o700)
        transport = FakeTransport()

        code, output = self.run_runner(transport)

        self.assertEqual(0, code)
        self.assertNotIn(str(self.ledger_dir), output.replace("\\n", ""))
        rows = self.rows(output)
        frozen = next(row for row in rows if row["event"] == "frozen_action")
        self.assertEqual("github.merge_pr", frozen["action"]["operation"])
        paths = rows[-1]["paths"]
        self.assertEqual(str(self.ledger_dir / "authority.jsonl"), paths["authority"])

    def test_no_tty_rejects_before_reading_or_writing(self):
        transport = FakeTransport()
        output = io.StringIO()
        input_stream = io.StringIO("approve anything anything\n")

        code = reference.main(
            ["--pr", "7", "--ledger-dir", str(self.ledger_dir)],
            transport=transport,
            input_stream=input_stream,
            output_stream=output,
        )

        self.assertEqual(2, code)
        self.assertEqual([], transport.get_calls)
        self.assertEqual(0, input_stream.tell())
        self.assertEqual("", output.getvalue())

    def test_help_is_available_without_a_tty_and_has_no_side_effects(self):
        output = io.StringIO()

        code = reference.main(
            ["--help"],
            input_stream=io.StringIO(),
            output_stream=output,
        )

        self.assertEqual(0, code)
        self.assertIn("--ledger-dir", output.getvalue())

    def test_yes_bypass_is_not_a_supported_argument(self):
        transport = FakeTransport()
        output = TTYBuffer()
        code = reference.main(
            [
                "--pr",
                "7",
                "--ledger-dir",
                str(self.ledger_dir),
                "--yes",
            ],
            transport=transport,
            input_stream=TTYBuffer(""),
            output_stream=output,
        )

        self.assertEqual(2, code)
        self.assertEqual([], transport.get_calls)
        self.assertEqual("invalid_arguments", self.rows(output.getvalue())[-1]["reason"])

    def test_invalid_or_dangling_ledger_symlink_is_rejected(self):
        for target_kind in ("directory", "dangling"):
            with self.subTest(target_kind=target_kind):
                link = self.root / ("link-" + target_kind)
                if target_kind == "directory":
                    os.symlink(self.ledger_dir, link, target_is_directory=True)
                else:
                    os.symlink(self.root / "does-not-exist", link)
                transport = FakeTransport()
                output = TTYBuffer()
                code = reference.main(
                    ["--pr", "7", "--ledger-dir", str(link)],
                    transport=transport,
                    input_stream=TTYBuffer(""),
                    output_stream=output,
                )
                self.assertEqual(1, code)
                self.assertEqual([], transport.get_calls)
                self.assertEqual("pre_execution_failure", self.rows(output.getvalue())[-1]["status"])

    def test_getpass_warning_is_a_pre_execution_failure_without_fallback(self):
        output = TTYBuffer()

        def cannot_hide_input(prompt):
            warnings.warn("echo enabled", getpass.GetPassWarning)
            return "should-not-be-used"

        with mock.patch.object(reference.getpass, "getpass", side_effect=cannot_hide_input):
            code = reference.main(
                ["--pr", "7", "--ledger-dir", str(self.ledger_dir)],
                input_stream=TTYBuffer(""),
                output_stream=output,
            )

        self.assertEqual(1, code)
        self.assertEqual("pre_execution_failure", self.rows(output.getvalue())[-1]["status"])
        self.assertNotIn("should-not-be-used", output.getvalue())


if __name__ == "__main__":
    unittest.main()
