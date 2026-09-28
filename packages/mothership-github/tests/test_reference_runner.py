"""Acceptance tests for the human-operated reference consumer."""

from __future__ import annotations

import copy
import datetime
import errno
import getpass
import hashlib
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
_BASE_SHA = "d" * 40


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


class ReadBackResponse(io.BytesIO):
    status = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.headers = {}

    def getcode(self):
        return self.status


class ReadBackOpener:
    def __init__(self, payloads):
        self.payloads = [copy.deepcopy(payload) for payload in payloads]
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        return ReadBackResponse(self.payloads.pop(0))


def readback_pr(*, merged_at, merged=True, head_sha=_HEAD, base_ref="main"):
    return {
        "url": "https://api.github.com/repos/UMEBOSHIISAN/mothership/pulls/7",
        "number": 7,
        "title": "synthetic",
        "state": "closed" if merged else "open",
        "updated_at": merged_at or "2026-09-27T00:00:00Z",
        "draft": False,
        "closed": merged,
        "merged": merged,
        "merged_at": merged_at if merged else None,
        "head": {"sha": head_sha, "ref": "feature"},
        "base": {"ref": base_ref, "repo": {"full_name": "UMEBOSHIISAN/mothership"}},
        "merge_commit_sha": _MERGE_SHA if merged else None,
    }


def readback_commit():
    return {
        "sha": _MERGE_SHA,
        "url": "https://api.github.com/repos/UMEBOSHIISAN/mothership/git/commits/" + _MERGE_SHA,
        "parents": [{"sha": _BASE_SHA}, {"sha": _HEAD}],
    }


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
        readback_opener=None,
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
            readback_opener=readback_opener,
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

    def verified_run(self, *, mode="confirmed", mutation=None, transform=None,
                     decision="approve", output=None, input_stream=None,
                     save_result=False):
        from mothership.contracts import canonical_json_sha256, validate_receipt_verification_binding
        from mothership_github import verification

        self.ledger_dir = Path(tempfile.mkdtemp(dir=self.root)).resolve()
        transport = FakeTransport(mutation)
        captured = {}
        requests = []
        real_execute = reference.executor.execute_action_merge_pr
        real_verify = verification.verify_merge_pr

        def execute(*args, **kwargs):
            captured["action"] = args[2]
            captured["action_value"] = reference._json_value(args[2].action)
            result = real_execute(*args, **kwargs)
            captured["ledger_bytes"] = [
                (self.ledger_dir / name).read_bytes()
                for name in ("authority.jsonl", "attempts.jsonl")
            ]
            captured["result"] = copy.deepcopy(result)
            return transform(result) if transform else result

        def now():
            finish = captured["result"]["attempt_finished"]["recorded_at"]
            return datetime.datetime.strptime(finish, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.UTC) + datetime.timedelta(seconds=2)

        def opener(request, *, timeout):
            requests.append(request)
            self.assertFalse(request.has_header("Authorization"))
            if mode == "read_failure":
                raise OSError("secret-readback-error")
            result = captured["result"]
            if mode == "same_second":
                merged_at = result["attempt_started"]["recorded_at"]
            else:
                merged_at = (now() - datetime.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            if "/pulls/" in request.full_url:
                value = readback_pr(merged_at=merged_at, merged=mode != "unmerged",
                                    head_sha=_OTHER_HEAD if mode == "mismatch" else _HEAD)
                value["body"] = "secret-remote-prose"
            else:
                value = readback_commit()
            return ReadBackResponse(value)

        def verify(action, receipt, **kwargs):
            self.assertIs(captured["action"], action)
            before = copy.deepcopy(receipt)
            if mode == "verifier_exception":
                raise RuntimeError("secret-verifier-error")
            bundle = real_verify(action, receipt, **kwargs)
            self.assertEqual(before, receipt)
            validate_receipt_verification_binding(
                receipt, bundle["verification"], expected_action_id=action.action["action_id"],
                expected_action_sha256=action.action_sha256)
            return bundle

        with mock.patch.object(reference.executor, "execute_action_merge_pr", side_effect=execute) as execution, \
             mock.patch.object(verification, "verify_merge_pr", side_effect=verify) as verifier, \
             mock.patch.object(verification, "_utc_now", side_effect=now):
            argv = ["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result"]
            if save_result:
                argv.append("--save-result")
            code, text = self.run_runner(
                transport, argv=argv,
                decision=decision, output=output, input_stream=input_stream, readback_opener=opener)
        rows = self.rows(text)
        if "action" in captured:
            self.assertEqual(captured["action_value"], reference._json_value(captured["action"].action))
        if "ledger_bytes" in captured:
            self.assertEqual(captured["ledger_bytes"], [
                (self.ledger_dir / name).read_bytes() for name in ("authority.jsonl", "attempts.jsonl")])
        if rows and rows[-1].get("receipt"):
            receipt = rows[-1]["receipt"]
            self.assertEqual(canonical_json_sha256(rows[-1]["source_pair"]),
                             receipt["executor_observation_ref"]["sha256"])
        self.assertNotIn("secret-", text)
        return code, rows, transport, requests, execution.call_count, verifier.call_count

    def test_verify_result_builds_bound_receipt_and_confirmed_readback(self):
        code, rows, transport, requests, executions, verifications = self.verified_run()
        self.assertEqual(0, code)
        self.assertEqual("SUCCESS", rows[-1]["receipt"]["status"])
        self.assertEqual("CONFIRMED", rows[-1]["status"])
        self.assertEqual((1, 1, 1, 2), (executions, verifications, len(transport.put_calls), len(requests)))
        self.assertEqual(hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
                         rows[-1]["receipt"]["executor_ref"]["sha256"])

    def test_save_result_verified_success_matches_terminal_output_and_mode(self):
        code, rows, _, _, _, _ = self.verified_run(save_result=True)

        self.assertEqual(0, code)
        result_path = self.ledger_dir / "result.jsonl"
        self.assertTrue(result_path.is_file())
        self.assertEqual(0o600, os.stat(result_path, follow_symlinks=False).st_mode & 0o777)
        saved = [json.loads(line) for line in result_path.read_text().splitlines() if line]
        expected = [row for row in rows if row.get("event") in {
            "frozen_action", "execution_result", "verification_result"
        }]
        self.assertEqual(expected, saved)
        self.assertEqual(
            [json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
             for row in expected],
            result_path.read_text().splitlines(),
        )

    def test_save_result_preserves_unknown_verification(self):
        code, rows, _, _, _, _ = self.verified_run(mode="read_failure", save_result=True)

        self.assertEqual(3, code)
        self.assertEqual("UNKNOWN", rows[-1]["status"])
        saved = [json.loads(line) for line in (self.ledger_dir / "result.jsonl").read_text().splitlines()]
        self.assertEqual("UNKNOWN", saved[-1]["status"])
        self.assertEqual(
            [row for row in rows if row.get("event") in {
                "frozen_action", "execution_result", "verification_result"
            }],
            saved,
        )

    def test_each_saved_event_is_synced_before_terminal_display(self):
        result_paths = []
        reserved_fd = []
        synced_sizes = []
        observations = []
        reserve = reference._ResultSaver.reserve
        original_fsync = reference.os.fsync

        def capture_reservation(ledger_dir):
            saver = reserve(ledger_dir)
            reserved_fd.append(saver._result_fd)
            result_paths.append(ledger_dir / "result.jsonl")
            return saver

        def record_sync(fd):
            original_fsync(fd)
            if reserved_fd and fd == reserved_fd[0]:
                synced_sizes.append(os.fstat(fd).st_size)

        class ObservedOutput(TTYBuffer):
            def write(self, value):
                row = json.loads(value)
                if row.get("event") in {"frozen_action", "execution_result", "verification_result"}:
                    saved = result_paths[0].read_bytes()
                    observations.append((row["event"], saved.endswith(value.encode("ascii")),
                                         len(saved), synced_sizes[-1] if synced_sizes else None))
                return super().write(value)

        with mock.patch.object(reference._ResultSaver, "reserve", side_effect=capture_reservation), \
             mock.patch.object(reference.os, "fsync", side_effect=record_sync):
            code, _, _, _, _, _ = self.verified_run(save_result=True, output=ObservedOutput())

        self.assertEqual(0, code)
        self.assertEqual(["frozen_action", "execution_result", "verification_result"],
                         [item[0] for item in observations])
        self.assertEqual(3, len(synced_sizes))
        for event, saved_before_display, size, synced_size in observations:
            with self.subTest(event=event):
                self.assertTrue(saved_before_display)
                self.assertEqual(size, synced_size)

    def test_default_path_does_not_create_result_file(self):
        code, _ = self.run_runner(FakeTransport())

        self.assertEqual(0, code)
        self.assertFalse((self.ledger_dir / "result.jsonl").exists())

    def test_save_result_requires_verify_result_before_transport_or_files(self):
        transport = FakeTransport()
        output = TTYBuffer()

        code = reference.main(
            ["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--save-result"],
            transport=transport,
            input_stream=TTYBuffer(""),
            output_stream=output,
        )

        self.assertEqual(2, code)
        self.assertEqual([], transport.get_calls)
        self.assertFalse((self.ledger_dir / "result.jsonl").exists())
        self.assertEqual("invalid_arguments", self.rows(output.getvalue())[-1]["reason"])

    def test_saved_events_exclude_approval_and_sensitive_output(self):
        code, rows, _, _, _, _ = self.verified_run(save_result=True)

        self.assertEqual(0, code)
        saved_text = (self.ledger_dir / "result.jsonl").read_text()
        self.assertNotIn("approval_required", saved_text)
        self.assertNotIn("token_required", saved_text)
        self.assertNotIn("approve ", saved_text)
        self.assertNotIn("secret-", saved_text)
        self.assertEqual({"frozen_action", "execution_result", "verification_result"},
                         {row["event"] for row in self.rows(saved_text)})

    def test_manual_token_prompt_is_not_saved(self):
        output = TTYBuffer()
        token_prompt = mock.Mock(return_value="secret-token-value")
        with mock.patch.object(reference, "GitHubRestTransport", side_effect=RuntimeError("secret-transport")):
            code = reference.main(
                ["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
                input_stream=TTYBuffer(""),
                output_stream=output,
                token_prompt=token_prompt,
            )

        self.assertEqual(1, code)
        token_prompt.assert_called_once()
        saved_text = (self.ledger_dir / "result.jsonl").read_text()
        self.assertEqual("", saved_text)
        self.assertNotIn("secret-token-value", saved_text)
        self.assertNotIn("token_required", saved_text)

    def test_existing_result_entry_blocks_without_overwrite(self):
        result_path = self.ledger_dir / "result.jsonl"
        result_path.write_text("sentinel\n")
        before = result_path.read_bytes()
        transport = FakeTransport()

        code, output = self.run_runner(transport)

        self.assertEqual(1, code)
        self.assertEqual([], transport.get_calls)
        self.assertEqual(before, result_path.read_bytes())
        self.assertEqual("pre_execution_failure", self.rows(output)[-1]["status"])

    def test_existing_result_symlink_and_directory_block_without_following(self):
        target = self.root / "result-target"
        target.write_text("target\n")
        for kind in ("symlink", "directory"):
            with self.subTest(kind=kind):
                self.ledger_dir = self.root / f"ledger-{kind}"
                self.ledger_dir.mkdir(mode=0o700)
                os.chmod(self.ledger_dir, 0o700)
                result_path = self.ledger_dir / "result.jsonl"
                if kind == "symlink":
                    os.symlink(target, result_path)
                else:
                    result_path.mkdir(mode=0o700)
                transport = FakeTransport()

                code, output = self.run_runner(transport)

                self.assertEqual(1, code)
                self.assertEqual([], transport.get_calls)
                self.assertEqual("pre_execution_failure", self.rows(output)[-1]["status"])
                if kind == "symlink":
                    self.assertEqual("target\n", target.read_text())

    def test_save_result_reservation_fsync_failure_stops_before_token_or_get(self):
        token_prompt = mock.Mock(side_effect=AssertionError("token must not be read"))
        constructor = mock.Mock(side_effect=AssertionError("transport must not be built"))
        with mock.patch.object(reference.os, "fsync", side_effect=OSError("secret-fsync")), \
             mock.patch.object(reference, "GitHubRestTransport", constructor):
            code = reference.main(
                ["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
                input_stream=TTYBuffer(""),
                output_stream=TTYBuffer(),
                token_prompt=token_prompt,
            )

        self.assertEqual(1, code)
        token_prompt.assert_not_called()
        constructor.assert_not_called()
        result_path = self.ledger_dir / "result.jsonl"
        self.assertTrue(result_path.exists())
        self.assertEqual(0o600, os.stat(result_path, follow_symlinks=False).st_mode & 0o777)

    def test_save_result_fails_closed_when_no_follow_is_unavailable(self):
        transport = FakeTransport()
        with mock.patch.object(reference.os, "O_NOFOLLOW", None):
            code, output = self.run_runner(
                transport,
                argv=["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
            )

        self.assertEqual(1, code)
        self.assertEqual([], transport.get_calls)
        self.assertFalse((self.ledger_dir / "result.jsonl").exists())
        self.assertEqual("evidence_save_failed", self.rows(output)[-1]["reason"])

    def test_save_write_failure_after_execution_does_not_repeat_executor(self):
        transport = FakeTransport()
        execute = reference.executor.execute_action_merge_pr
        calls = 0
        writes = 0
        reserved_fd = []
        partial_bytes = []

        reserve = reference._ResultSaver.reserve

        def capture_reservation(ledger_dir):
            saver = reserve(ledger_dir)
            reserved_fd.append(saver._result_fd)
            return saver

        def execute_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            return execute(*args, **kwargs)

        def short_after_frozen(fd, data):
            nonlocal writes
            if reserved_fd and fd == reserved_fd[0]:
                writes += 1
                if writes == 2:
                    prefix = data[:len(data) // 2]
                    partial_bytes.append(prefix)
                    return original_write(fd, prefix)
            return original_write(fd, data)

        original_write = reference.os.write
        with mock.patch.object(reference.executor, "execute_action_merge_pr", side_effect=execute_once), \
             mock.patch.object(reference._ResultSaver, "reserve", side_effect=capture_reservation), \
             mock.patch.object(reference.os, "write", side_effect=short_after_frozen), \
             mock.patch.object(reference, "_run_verification", side_effect=AssertionError("unexpected readback")) as verify:
            code, output = self.run_runner(
                transport,
                argv=["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
            )

        self.assertEqual(1, code)
        self.assertEqual(1, calls)
        self.assertEqual(1, len(transport.put_calls))
        verify.assert_not_called()
        self.assertEqual(2, writes)
        complete_line, partial_line = (self.ledger_dir / "result.jsonl").read_bytes().split(b"\n", 1)
        self.assertEqual("frozen_action", json.loads(complete_line)["event"])
        self.assertEqual(partial_bytes[0], partial_line)
        self.assertNotIn("short write", output)
        self.assertEqual("evidence_save_failed", self.rows(output)[-1]["reason"])

    def test_save_fsync_failure_after_execution_does_not_repeat_executor(self):
        transport = FakeTransport()
        calls = 0
        fsyncs = 0
        reserved_fd = []
        reserve = reference._ResultSaver.reserve

        def capture_reservation(ledger_dir):
            saver = reserve(ledger_dir)
            reserved_fd.append(saver._result_fd)
            return saver

        original_fsync = reference.os.fsync

        def fail_result_fsync(fd):
            nonlocal fsyncs
            if reserved_fd and fd == reserved_fd[0]:
                fsyncs += 1
                if fsyncs == 2:
                    raise OSError("secret-fsync-after-effect")
            return original_fsync(fd)

        execute = reference.executor.execute_action_merge_pr

        def execute_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            return execute(*args, **kwargs)

        with mock.patch.object(reference.executor, "execute_action_merge_pr", side_effect=execute_once), \
             mock.patch.object(reference._ResultSaver, "reserve", side_effect=capture_reservation), \
             mock.patch.object(reference.os, "fsync", side_effect=fail_result_fsync):
            code, output = self.run_runner(
                transport,
                argv=["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
            )

        self.assertEqual(1, code)
        self.assertEqual(1, calls, (fsyncs, transport.get_calls, output))
        self.assertEqual(1, len(transport.put_calls))
        self.assertNotIn("secret-fsync-after-effect", output)
        self.assertEqual("evidence_save_failed", self.rows(output)[-1]["reason"])

    def test_executor_exception_after_effect_saves_unknown_execution_without_retry(self):
        transport = FakeTransport()
        execute = reference.executor.execute_action_merge_pr

        def execute_then_raise(*args, **kwargs):
            execute(*args, **kwargs)
            raise RuntimeError("secret-executor-after-effect")

        with mock.patch.object(reference.executor, "execute_action_merge_pr", side_effect=execute_then_raise):
            code, output = self.run_runner(
                transport,
                argv=["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
            )

        self.assertEqual(1, code)
        self.assertEqual(1, len(transport.put_calls))
        self.assertNotIn("secret-executor-after-effect", output)
        saved = [json.loads(line) for line in (self.ledger_dir / "result.jsonl").read_text().splitlines()]
        self.assertEqual(
            ["frozen_action", "execution_result"], [row["event"] for row in saved]
        )
        self.assertEqual("reconciliation_required", saved[-1]["status"])

    def test_partial_result_is_never_reused_after_save_failure(self):
        transport = FakeTransport()
        with mock.patch.object(reference._ResultSaver, "_write_event", side_effect=OSError("short write")):
            code, _ = self.run_runner(
                transport,
                argv=["--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result", "--save-result"],
            )
        self.assertEqual(1, code)
        self.assertTrue((self.ledger_dir / "result.jsonl").exists())

        second_transport = FakeTransport()
        second_code, second_output = self.run_runner(second_transport)
        self.assertEqual(1, second_code)
        self.assertEqual([], second_transport.get_calls)
        self.assertEqual("pre_execution_failure", self.rows(second_output)[-1]["status"])

    def test_cancellation_leaves_only_frozen_action_in_saved_result(self):
        output = TTYBuffer()
        code, rows, transport, _, executions, verifications = self.verified_run(
            save_result=True, input_stream=TTYBuffer(""), output=output)

        self.assertEqual(0, code)
        self.assertEqual((0, 0, 0), (executions, verifications, len(transport.put_calls)))
        saved = [json.loads(line) for line in (self.ledger_dir / "result.jsonl").read_text().splitlines()]
        self.assertEqual(["frozen_action"], [row["event"] for row in saved])
        self.assertEqual("approval_eof", rows[-1]["reason"])

    def test_terminal_output_failure_closes_saved_file(self):
        class FailingOutput(TTYBuffer):
            def write(self, value):
                if '"event":"verification_result"' in value:
                    raise OSError("display failed")
                return super().write(value)

        descriptors = []
        reserve = reference._ResultSaver.reserve

        def capture_reservation(ledger_dir):
            saver = reserve(ledger_dir)
            descriptors.extend((saver._result_fd, saver._directory_fd))
            return saver

        with mock.patch.object(reference._ResultSaver, "reserve", side_effect=capture_reservation):
            code, _, _, _, _, _ = self.verified_run(save_result=True, output=FailingOutput())

        self.assertEqual(1, code)
        saved_path = self.ledger_dir / "result.jsonl"
        self.assertTrue(saved_path.exists())
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_result_close_failure_is_nonzero_with_fixed_reason(self):
        descriptors = []
        reserve = reference._ResultSaver.reserve
        original_close = os.close
        failed = False

        def capture_reservation(ledger_dir):
            saver = reserve(ledger_dir)
            descriptors.extend((saver._result_fd, saver._directory_fd))
            return saver

        def close_then_fail(descriptor):
            nonlocal failed
            original_close(descriptor)
            if descriptors and descriptor == descriptors[0] and not failed:
                failed = True
                raise OSError("secret-close")

        with mock.patch.object(reference._ResultSaver, "reserve", side_effect=capture_reservation), \
             mock.patch.object(reference.os, "close", side_effect=close_then_fail):
            code, rows, transport, _, executions, verifications = self.verified_run(save_result=True)

        self.assertEqual(1, code)
        self.assertTrue(failed)
        self.assertEqual((1, 1, 1), (executions, verifications, len(transport.put_calls)))
        self.assertNotIn("secret-close", json.dumps(rows))
        self.assertEqual("evidence_save_failed", rows[-1]["reason"])
        for descriptor in descriptors:
            with self.assertRaises(OSError) as raised:
                os.fstat(descriptor)
            self.assertEqual(errno.EBADF, raised.exception.errno)

    def test_unknown_mismatch_and_same_second_stay_nonzero(self):
        for mode, status in (("unmerged", "UNKNOWN"), ("read_failure", "UNKNOWN"),
                             ("same_second", "UNKNOWN"), ("mismatch", "MISMATCH")):
            with self.subTest(mode=mode):
                code, rows, transport, requests, executions, verifications = self.verified_run(mode=mode)
                self.assertEqual(3, code)
                self.assertEqual(status, rows[-1]["status"])
                self.assertEqual("SUCCESS", rows[-1]["receipt"]["status"])
                self.assertEqual((1, 1, 1), (executions, verifications, len(transport.put_calls)))
                self.assertLessEqual(len(requests), 2)
                if mode == "same_second":
                    self.assertEqual("ambiguous_merge_time", rows[-1]["evidence"]["reason"])

    def test_failed_and_unknown_execution_are_not_promoted_by_confirmation(self):
        for http_status, expected in ((409, "FAILED"), (503, "UNKNOWN")):
            with self.subTest(http_status=http_status):
                code, rows, transport, _, executions, verifications = self.verified_run(
                    mutation={"http_status": http_status, "merged": None, "merge_commit_sha": None})
                self.assertEqual(1, code)
                self.assertEqual(expected, rows[-1]["receipt"]["status"])
                self.assertEqual("CONFIRMED", rows[-1]["status"])
                self.assertEqual((1, 1, 1), (executions, verifications, len(transport.put_calls)))

    def test_missing_or_malformed_pair_is_sanitized_without_readback(self):
        for malformed in (False, True):
            def change(result):
                result["attempt_finished"] = {"secret-invalid-field": "secret-value"} if malformed else None
                return result
            with self.subTest(malformed=malformed):
                code, rows, transport, requests, executions, verifications = self.verified_run(transform=change)
                self.assertEqual(3, code)
                self.assertEqual("receipt_unavailable", rows[-1]["reason"])
                self.assertIsNone(rows[-1]["receipt"])
                self.assertIsNone(rows[-1]["source_pair"])
                self.assertEqual((1, 0, 1, 0), (executions, verifications, len(transport.put_calls), len(requests)))

    def test_verifier_exception_preserves_receipt_without_retry(self):
        code, rows, transport, requests, executions, verifications = self.verified_run(mode="verifier_exception")
        self.assertEqual(3, code)
        self.assertEqual("verification_unavailable", rows[-1]["reason"])
        self.assertEqual("SUCCESS", rows[-1]["receipt"]["status"])
        self.assertEqual((1, 1, 1, 0), (executions, verifications, len(transport.put_calls), len(requests)))

    def test_reject_and_cancel_do_not_execute_or_read_back_with_flag(self):
        for decision, input_stream in (("reject", None), ("approve", TTYBuffer(""))):
            with self.subTest(decision=decision):
                code, _, transport, requests, executions, verifications = self.verified_run(
                    decision=decision, input_stream=input_stream)
                self.assertEqual(0, code)
                self.assertEqual((0, 0, 0, 0), (executions, verifications, len(transport.put_calls), len(requests)))

    def test_approval_or_cancellation_display_failure_is_nonzero_without_side_effects(self):
        class FailingOutput(TTYBuffer):
            def __init__(self, event, operation):
                super().__init__()
                self._event = event
                self._operation = operation
                self._last_write = ""

            def write(self, value):
                if self._operation == "write" and f'"event":"{self._event}"' in value:
                    raise OSError("secret-output-error")
                self._last_write = value
                return super().write(value)

            def flush(self):
                if self._operation == "flush" and f'"event":"{self._event}"' in self._last_write:
                    raise OSError("secret-output-error")
                return super().flush()

        class TrackingEOFInput(TTYBuffer):
            def __init__(self):
                super().__init__()
                self.read_calls = 0

            def readline(self, *args, **kwargs):
                self.read_calls += 1
                return ""

        for event, input_stream_factory in (
            ("approval_required", lambda: TrackingEOFInput()),
            ("stopped", lambda: TrackingEOFInput()),
        ):
            for operation in ("write", "flush"):
                with self.subTest(event=event, operation=operation):
                    transport = FakeTransport()
                    output = FailingOutput(event, operation)
                    input_stream = input_stream_factory()

                    code, text = self.run_runner(
                        transport,
                        input_stream=input_stream,
                        output=output,
                    )

                    self.assertEqual(1, code)
                    self.assertEqual(0 if event == "approval_required" else 1, input_stream.read_calls)
                    self.assertEqual([], transport.put_calls)
                    self.assertFalse((self.ledger_dir / "authority.jsonl").exists())
                    self.assertFalse((self.ledger_dir / "attempts.jsonl").exists())
                    self.assertNotIn("secret-output-error", text)

    def test_verification_display_failure_does_not_repeat_effect(self):
        class FailingOutput(TTYBuffer):
            def write(self, value):
                if '"verification_result"' in value:
                    raise OSError("secret-output-error")
                return super().write(value)
        code, _, transport, _, executions, verifications = self.verified_run(output=FailingOutput())
        self.assertEqual(1, code)
        self.assertEqual((1, 1, 1), (executions, verifications, len(transport.put_calls)))

    def test_source_reference_is_frozen_before_effect_and_source_failure_stops(self):
        original = reference._consumer_source_reference
        captured = []
        def freeze():
            value = original()
            captured.append(value)
            return value
        def mutate(result):
            self.assertEqual(1, len(captured))
            reference._consumer_source_reference = mock.Mock(side_effect=AssertionError("late source read"))
            return result
        with mock.patch.object(reference, "_consumer_source_reference", side_effect=freeze):
            code, rows, _, _, _, _ = self.verified_run(transform=mutate)
        self.assertEqual(0, code)
        self.assertEqual(captured[0], rows[-1]["receipt"]["executor_ref"])
        with mock.patch.object(reference, "_consumer_source_reference", side_effect=OSError("secret-source")):
            code, _, transport, requests, executions, verifications = self.verified_run()
        self.assertEqual(1, code)
        self.assertEqual((0, 0, 0, 0), (executions, verifications, len(transport.put_calls), len(requests)))

    def test_executor_exception_with_flag_has_no_readback_or_raw_error(self):
        with mock.patch.object(reference.executor, "execute_action_merge_pr", side_effect=RuntimeError("secret-executor")), \
             mock.patch.object(reference, "_run_verification") as verify:
            code, text = self.run_runner(FakeTransport(), argv=[
                "--pr", "7", "--ledger-dir", str(self.ledger_dir), "--verify-result"])
        self.assertEqual(1, code)
        verify.assert_not_called()
        self.assertNotIn("secret-", text)

    def test_success_summary_cannot_promote_failed_terminal_pair(self):
        def change(result):
            result.update(status="success", http_status=200, merged=True, merge_commit_sha=_MERGE_SHA)
            return result
        code, rows, _, _, _, _ = self.verified_run(
            mutation={"http_status": 409, "merged": None, "merge_commit_sha": None}, transform=change)
        self.assertEqual(1, code)
        self.assertEqual("FAILED", rows[-1]["receipt"]["status"])
        self.assertEqual("CONFIRMED", rows[-1]["status"])

    def test_invalid_execution_status_is_not_echoed_in_verification_output(self):
        def change(result):
            result["status"] = "secret-invalid-status"
            return result
        code, rows, _, _, _, _ = self.verified_run(transform=change)
        self.assertEqual(1, code)
        self.assertEqual("reconciliation_required", rows[-1]["execution_status"])

    def test_default_execution_path_never_imports_or_calls_verification(self):
        import builtins
        real_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name in {"mothership_github.external_action", "mothership_github.verification"}:
                raise AssertionError("unexpected opt-in import")
            return real_import(name, *args, **kwargs)
        with mock.patch.object(builtins, "__import__", side_effect=guarded_import), \
             mock.patch.object(reference, "_run_verification", side_effect=AssertionError("unexpected")):
            code, text = self.run_runner(FakeTransport())
        self.assertEqual(0, code)
        self.assertNotIn("verification_result", text)

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
