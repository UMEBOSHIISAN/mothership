"""Closed approval-ledger, replay, durability, and finish lifecycle tests."""

from __future__ import annotations

import datetime
import hashlib
import importlib
import io
import json
import multiprocessing
import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock


_TMP_ROOT = pathlib.Path(tempfile.gettempdir()).resolve() / "mothership-ledger-tests"
_ALIAS = "codex-cli"
_INVOCATION_ID = "invocation-05t-001"
_REGISTRY = "1" * 64
_TASK = "2" * 64
_PROMPT = "3" * 64
_SCOPE = "4" * 64
_EPOCH = datetime.datetime(2026, 8, 2, 10, 0, 0, tzinfo=datetime.UTC)


def _load_modules():
    ledger = importlib.import_module("orchestration.lib.ledger")
    canonical = importlib.import_module("orchestration.lib.canonical")
    jsonio = importlib.import_module("orchestration.lib.jsonio")
    return ledger, canonical, jsonio


def _binding(ledger, **changes):
    values = {
        "alias": _ALIAS,
        "invocation_id": _INVOCATION_ID,
        "registry_sha256": _REGISTRY,
        "task_sha256": _TASK,
        "prompt_sha256": _PROMPT,
        "scope_sha256": _SCOPE,
    }
    values.update(changes)
    return ledger.make_binding(**values)


def _common(binding, event_type, event_id, recorded_at, expires_at):
    return {
        "schema_version": "0.1.0",
        "event_id": event_id,
        "event_type": event_type,
        "alias": binding.alias,
        "invocation_id": binding.invocation_id,
        "registry_sha256": binding.registry_sha256,
        "task_sha256": binding.task_sha256,
        "prompt_sha256": binding.prompt_sha256,
        "scope_sha256": binding.scope_sha256,
        "invocation_sha256": binding.invocation_sha256,
        "recorded_at": recorded_at,
        "expires_at": expires_at,
    }


def _grant(binding, suffix="1", recorded="2026-08-02T10:00:00Z", expires="2026-08-02T10:15:00Z"):
    return _common(binding, "approval_granted", "event-" + suffix * 32, recorded, expires)


def _failed(binding, suffix="2", result="mismatch"):
    event = _common(
        binding,
        "confirmation_failed",
        "event-" + suffix * 32,
        "2026-08-02T10:00:00Z",
        "2026-08-02T10:15:00Z",
    )
    event["confirmation_result"] = result
    return event


class _TTY(io.StringIO):
    def isatty(self):
        return True


class _FixedLineTTY(_TTY):
    def __init__(self, fixed_line):
        super().__init__()
        self.fixed_line = fixed_line

    def readline(self, *args):
        return self.fixed_line


class _ExplodingTTY:
    def isatty(self):
        raise OSError("private detail")


def _append_worker(ledger_path, event, result_path, barrier):
    ledger = importlib.import_module("orchestration.lib.ledger")
    barrier.wait()
    try:
        ledger.append_event(pathlib.Path(ledger_path), event)
        outcome = "ok"
    except ledger.LedgerError as exc:
        outcome = "rejected:" + type(exc).__name__
    pathlib.Path(result_path).write_text(outcome, encoding="utf-8")


def _consume_worker(ledger_path, result_path, barrier):
    ledger = importlib.import_module("orchestration.lib.ledger")
    binding = _binding(ledger)
    barrier.wait()
    try:
        ledger.consume_approval_and_start(
            pathlib.Path(ledger_path), binding, _EPOCH + datetime.timedelta(seconds=1)
        )
        outcome = "ok"
    except ledger.LedgerError as exc:
        outcome = "rejected:" + type(exc).__name__
    pathlib.Path(result_path).write_text(outcome, encoding="utf-8")


def _finish_worker(ledger_path, start_id, result_path, barrier):
    ledger = importlib.import_module("orchestration.lib.ledger")
    binding = _binding(ledger)
    barrier.wait()
    try:
        ledger.finish_attempt(
            pathlib.Path(ledger_path),
            binding,
            start_id,
            "success",
            0,
            _EPOCH + datetime.timedelta(seconds=2),
        )
        outcome = "ok"
    except ledger.LedgerError as exc:
        outcome = "rejected:" + type(exc).__name__
    pathlib.Path(result_path).write_text(outcome, encoding="utf-8")


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.ledger, self.canonical, self.jsonio = _load_modules()
        _TMP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(_TMP_ROOT, 0o700)
        self._temporary = tempfile.TemporaryDirectory(dir=_TMP_ROOT)
        self.workdir = pathlib.Path(self._temporary.name)
        self.path = self.workdir / "approvals.jsonl"

    def tearDown(self):
        self._temporary.cleanup()
        _TMP_ROOT.rmdir()

    def append_grant(self, binding=None, **changes):
        binding = binding or _binding(self.ledger)
        event = _grant(binding, **changes)
        self.ledger.append_event(self.path, event)
        return binding, event

    def start_attempt(self, binding=None):
        binding, grant = self.append_grant(binding)
        result = self.ledger.consume_approval_and_start(
            self.path, binding, _EPOCH + datetime.timedelta(seconds=1)
        )
        return binding, grant, result

    def read_events(self):
        raw = self.path.read_bytes()
        return [self.jsonio.loads_strict(line) for line in raw.splitlines()]

    def run_two(self, target, args_a, args_b):
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        result_a = self.workdir / "result-a.txt"
        result_b = self.workdir / "result-b.txt"
        process_a = context.Process(target=target, args=(*args_a, str(result_a), barrier))
        process_b = context.Process(target=target, args=(*args_b, str(result_b), barrier))
        process_a.start()
        process_b.start()
        try:
            process_a.join(15)
            process_b.join(15)
            self.assertFalse(process_a.is_alive(), "first child exceeded visible join cap")
            self.assertFalse(process_b.is_alive(), "second child exceeded visible join cap")
            self.assertEqual(0, process_a.exitcode)
            self.assertEqual(0, process_b.exitcode)
            return result_a.read_text(encoding="utf-8"), result_b.read_text(encoding="utf-8")
        finally:
            for process in (process_a, process_b):
                if process.is_alive():
                    process.terminate()
                    process.join(5)


class BindingAndEventTests(LedgerTestCase):
    def test_binding_dataclass_signature_hash_and_independent_changes_are_exact(self):
        import dataclasses
        import inspect

        fields = tuple(field.name for field in dataclasses.fields(self.ledger.InvocationBinding))
        self.assertEqual(
            (
                "alias",
                "invocation_id",
                "registry_sha256",
                "task_sha256",
                "prompt_sha256",
                "scope_sha256",
                "invocation_sha256",
            ),
            fields,
        )
        self.assertEqual(
            ("alias", "invocation_id", "registry_sha256", "task_sha256", "prompt_sha256", "scope_sha256"),
            tuple(inspect.signature(self.ledger.make_binding).parameters),
        )
        binding = _binding(self.ledger)
        raw = (
            f"registry_sha256={_REGISTRY}\n"
            f"task_sha256={_TASK}\n"
            f"prompt_sha256={_PROMPT}\n"
            f"scope_sha256={_SCOPE}\n"
            f"invocation_id={_INVOCATION_ID}\n"
        ).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), binding.invocation_sha256)
        changes = (
            {"registry_sha256": "5" * 64},
            {"task_sha256": "6" * 64},
            {"prompt_sha256": "7" * 64},
            {"scope_sha256": "8" * 64},
            {"invocation_id": "invocation-05t-002"},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertNotEqual(binding.invocation_sha256, _binding(self.ledger, **change).invocation_sha256)

    def test_binding_rejects_wrong_types_alias_ids_and_digests(self):
        invalid = (
            {"alias": "gemma"},
            {"alias": 1},
            {"invocation_id": "bad invocation"},
            {"invocation_id": "a" * 129},
            {"registry_sha256": "A" * 64},
            {"task_sha256": "2" * 63},
            {"prompt_sha256": "3" * 64 + "\n"},
            {"scope_sha256": True},
        )
        for change in invalid:
            with self.subTest(change=change):
                with self.assertRaises(self.ledger.EventValidationError):
                    _binding(self.ledger, **change)

    def test_each_event_type_has_one_exact_field_set(self):
        binding = _binding(self.ledger)
        grant = _grant(binding)
        failed = _failed(binding)
        started = _common(
            binding,
            "attempt_started",
            "event-" + "3" * 32,
            "2026-08-02T10:00:01Z",
            grant["expires_at"],
        )
        started.update(
            approval_event_id=grant["event_id"],
            approval_sha256=self.canonical.canonical_json_sha256(grant),
        )
        finished = _common(
            binding,
            "attempt_finished",
            "event-" + "4" * 32,
            "2026-08-02T10:00:02Z",
            grant["expires_at"],
        )
        finished.update(
            attempt_started_event_id=started["event_id"], exit_class="success", exit_code=0
        )
        for event in (grant, failed, started, finished):
            with self.subTest(event_type=event["event_type"]):
                self.assertEqual(event, self.ledger.validate_event(event))
                missing = dict(event)
                missing.pop(next(iter(set(event) - {"schema_version", "event_type"})))
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.validate_event(missing)
                extra = dict(event, prompt_text="private")
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.validate_event(extra)

    def test_event_semantics_reject_malformed_ids_times_hashes_cross_fields_and_privacy(self):
        binding = _binding(self.ledger)
        base = _grant(binding)
        invalid = (
            dict(base, event_id="event-short"),
            dict(base, recorded_at="2026-02-30T10:00:00Z"),
            dict(base, recorded_at="2026-08-02T10:00:00.1Z"),
            dict(base, expires_at="2026-08-02T10:00:00Z"),
            dict(base, expires_at="2026-08-02T09:59:59Z"),
            dict(base, invocation_sha256="f" * 64),
            dict(base, confirmation_result="mismatch"),
            dict(base, approval_quote="approve"),
            dict(base, registry_sha256=_REGISTRY + "\n"),
        )
        for event in invalid:
            with self.subTest(event=event):
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.validate_event(event)

    def test_exit_class_code_matrix_is_closed_and_bool_never_counts_as_integer(self):
        binding = _binding(self.ledger)
        base = _common(
            binding,
            "attempt_finished",
            "event-" + "4" * 32,
            "2026-08-02T10:00:02Z",
            "2026-08-02T10:15:00Z",
        )
        base["attempt_started_event_id"] = "event-" + "3" * 32
        valid = (("success", 0), ("nonzero-exit", 1), ("nonzero-exit", -9), ("launch-error", None), ("timeout", None), ("output-limit-exceeded", None))
        invalid = (("success", True), ("success", None), ("success", 1), ("nonzero-exit", False), ("nonzero-exit", 0), ("nonzero-exit", None), ("launch-error", 1), ("timeout", 0), ("output-limit-exceeded", -1), ("other", None))
        for exit_class, exit_code in valid:
            with self.subTest(valid=(exit_class, exit_code)):
                event = dict(base, exit_class=exit_class, exit_code=exit_code)
                self.assertEqual(event, self.ledger.validate_event(event))
        for exit_class, exit_code in invalid:
            with self.subTest(invalid=(exit_class, exit_code)):
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.validate_event(dict(base, exit_class=exit_class, exit_code=exit_code))

    def test_now_requires_exact_whole_second_utc_datetime(self):
        binding, _ = self.append_grant()
        invalid = (
            "2026-08-02T10:00:01Z",
            True,
            datetime.datetime(2026, 8, 2, 10, 0, 1),
            datetime.datetime(2026, 8, 2, 10, 0, 1, 1, tzinfo=datetime.UTC),
            datetime.datetime(2026, 8, 2, 11, 0, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=1))),
        )
        for now in invalid:
            with self.subTest(now=now):
                with self.assertRaises(self.ledger.NaiveDatetimeError):
                    self.ledger.consume_approval_and_start(self.path, binding, now)


class AppendDurabilityTests(LedgerTestCase):
    def test_append_accepts_concrete_path_and_rejects_nonpath_forms(self):
        # Rejecting pathlib.PosixPath prevents every normal ledger operation.
        binding = _binding(self.ledger)
        event = _grant(binding)
        self.assertIsInstance(self.path, pathlib.PosixPath)
        self.assertEqual(event["event_id"], self.ledger.append_event(self.path, event))
        for invalid in (str(self.path), pathlib.PurePosixPath(self.path)):
            with self.subTest(invalid=invalid):
                with self.assertRaises(self.ledger.LedgerIOError):
                    self.ledger.append_event(invalid, event)

    def test_append_is_canonical_jsonl_mode_0600_and_returns_event_id(self):
        binding = _binding(self.ledger)
        first = _grant(binding, "1")
        second = _grant(binding, "2")
        self.assertEqual(first["event_id"], self.ledger.append_event(self.path, first))
        self.assertEqual(second["event_id"], self.ledger.append_event(self.path, second))
        self.assertEqual(0o600, stat.S_IMODE(os.lstat(self.path).st_mode))
        self.assertEqual(
            self.canonical.canonical_json_bytes(first) + b"\n" + self.canonical.canonical_json_bytes(second) + b"\n",
            self.path.read_bytes(),
        )

    def test_append_rejects_relative_root_symlink_and_wrong_mode_targets(self):
        binding = _binding(self.ledger)
        event = _grant(binding)
        real = self.workdir / "real.jsonl"
        real.write_bytes(b"")
        os.chmod(real, 0o600)
        symlink = self.workdir / "link.jsonl"
        symlink.symlink_to(real)
        wrong_mode = self.workdir / "wrong.jsonl"
        wrong_mode.write_bytes(b"")
        os.chmod(wrong_mode, 0o644)
        for target in (pathlib.Path("relative.jsonl"), pathlib.Path("/"), symlink, wrong_mode):
            with self.subTest(target=target):
                with self.assertRaises(self.ledger.LedgerIOError):
                    self.ledger.append_event(target, event)

    def test_append_rejects_nonregular_targets_without_blocking(self):
        binding = _binding(self.ledger)
        event = _grant(binding)
        directory = self.workdir / "directory"
        directory.mkdir()
        fifo = self.workdir / "fifo"
        os.mkfifo(fifo, 0o600)
        for target in (directory, fifo):
            with self.subTest(target=target):
                with self.assertRaises(self.ledger.LedgerIOError):
                    self.ledger.append_event(target, event)
        for index, file_type in enumerate((stat.S_IFSOCK, stat.S_IFCHR)):
            with self.subTest(simulated_type=file_type):
                backing = self.workdir / f"nonregular-{index}"
                descriptor = os.open(backing, os.O_RDWR | os.O_CREAT, 0o600)
                metadata = mock.Mock(st_mode=file_type | 0o600)
                with mock.patch.object(self.ledger, "os", wraps=os) as ledger_os:
                    ledger_os.open.return_value = descriptor
                    ledger_os.fstat.side_effect = lambda value: metadata if value == descriptor else os.fstat(value)
                    with self.assertRaises(self.ledger.LedgerIOError):
                        self.ledger.append_event(backing, event)

    def test_strict_reread_rejects_partial_empty_duplicate_key_duplicate_id_and_bad_utf8(self):
        binding = _binding(self.ledger)
        event = _grant(binding)
        raw_cases = (
            self.canonical.canonical_json_bytes(event),
            self.canonical.canonical_json_bytes(event) + b"\n\n",
            b'{"schema_version":"0.1.0","schema_version":"0.1.0"}\n',
            self.canonical.canonical_json_bytes(event) + b"\n" + self.canonical.canonical_json_bytes(event) + b"\n",
            b"\xff\n",
        )
        for index, raw in enumerate(raw_cases):
            with self.subTest(index=index):
                target = self.workdir / f"bad-{index}.jsonl"
                target.write_bytes(raw)
                os.chmod(target, 0o600)
                with self.assertRaises(self.ledger.MalformedLedgerEntryError):
                    self.ledger.append_event(target, _grant(binding, str(index + 3)))

    def test_short_write_loops_and_zero_negative_oversize_or_exception_never_claim_success(self):
        binding = _binding(self.ledger)
        event = _grant(binding)
        original = self.ledger._write_chunk

        def short(handle, raw):
            return handle.write(raw[: max(1, len(raw) // 2)])

        with mock.patch.object(self.ledger, "_write_chunk", side_effect=short):
            self.assertEqual(event["event_id"], self.ledger.append_event(self.path, event))
        self.assertEqual([event], self.read_events())

        for result in (0, -1, None, 10**9):
            target = self.workdir / f"write-{result}.jsonl"
            with self.subTest(result=result):
                with mock.patch.object(self.ledger, "_write_chunk", return_value=result):
                    with self.assertRaises(self.ledger.LedgerIOError):
                        self.ledger.append_event(target, _grant(binding, "2"))
        target = self.workdir / "write-error.jsonl"
        with mock.patch.object(self.ledger, "_write_chunk", side_effect=OSError("private")):
            with self.assertRaises(self.ledger.LedgerIOError):
                self.ledger.append_event(target, _grant(binding, "3"))
        self.assertIs(self.ledger._write_chunk, original)

    def test_flush_and_fsync_failures_raise_without_false_success(self):
        binding = _binding(self.ledger)
        for seam in ("_flush", "_fsync"):
            with self.subTest(seam=seam):
                target = self.workdir / f"{seam}.jsonl"
                with mock.patch.object(self.ledger, seam, side_effect=OSError("private")):
                    with self.assertRaises(self.ledger.LedgerIOError):
                        self.ledger.append_event(target, _grant(binding))

    def test_lock_is_held_on_one_descriptor_across_reread_append_flush_and_fsync(self):
        binding = _binding(self.ledger)
        state = {"locked": False, "descriptor": None}
        original_flock = self.ledger._flock
        original_read = self.ledger._read_chunk
        original_write = self.ledger._write_chunk
        original_flush = self.ledger._flush
        original_fsync = self.ledger._fsync

        def flock(descriptor, operation):
            result = original_flock(descriptor, operation)
            if operation & getattr(importlib.import_module("fcntl"), "LOCK_UN"):
                state["locked"] = False
            else:
                state.update(locked=True, descriptor=descriptor)
            return result

        def read(descriptor, size):
            self.assertTrue(state["locked"])
            self.assertEqual(state["descriptor"], descriptor)
            return original_read(descriptor, size)

        def write(handle, raw):
            self.assertTrue(state["locked"])
            self.assertEqual(state["descriptor"], handle.fileno())
            return original_write(handle, raw)

        def flush(handle):
            self.assertTrue(state["locked"])
            return original_flush(handle)

        def fsync(descriptor):
            self.assertTrue(state["locked"])
            self.assertEqual(state["descriptor"], descriptor)
            return original_fsync(descriptor)

        with mock.patch.object(self.ledger, "_flock", side_effect=flock), mock.patch.object(self.ledger, "_read_chunk", side_effect=read), mock.patch.object(self.ledger, "_write_chunk", side_effect=write), mock.patch.object(self.ledger, "_flush", side_effect=flush), mock.patch.object(self.ledger, "_fsync", side_effect=fsync):
            self.ledger.append_event(self.path, _grant(binding))

    def test_direct_append_and_complete_reread_enforce_start_and_finish_relationships(self):
        binding = _binding(self.ledger)
        grant = _grant(binding)
        self.ledger.append_event(self.path, grant)
        started = _common(binding, "attempt_started", "event-" + "3" * 32, "2026-08-02T10:00:01Z", grant["expires_at"])
        started.update(approval_event_id=grant["event_id"], approval_sha256=self.canonical.canonical_json_sha256(grant))
        for change in (
            {"approval_event_id": "event-" + "9" * 32},
            {"approval_sha256": "9" * 64},
            {"expires_at": "2026-08-02T10:14:59Z"},
        ):
            with self.subTest(start_change=change):
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.append_event(self.path, dict(started, **change))
        self.ledger.append_event(self.path, started)
        finished = _common(binding, "attempt_finished", "event-" + "4" * 32, "2026-08-02T10:00:02Z", grant["expires_at"])
        finished.update(attempt_started_event_id=started["event_id"], exit_class="success", exit_code=0)
        for change in (
            {"attempt_started_event_id": "event-" + "9" * 32},
            {"expires_at": "2026-08-02T10:14:59Z"},
            {"recorded_at": "2026-08-02T10:00:00Z"},
        ):
            with self.subTest(finish_change=change):
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.append_event(self.path, dict(finished, **change))
        self.ledger.append_event(self.path, finished)
        with self.assertRaises(self.ledger.EventValidationError):
            self.ledger.append_event(self.path, dict(finished, event_id="event-" + "5" * 32))

    def test_complete_reread_rejects_every_invalid_reference_relationship(self):
        binding = _binding(self.ledger)
        other_binding = _binding(self.ledger, task_sha256="6" * 64)
        grant = _grant(binding)
        started = _common(binding, "attempt_started", "event-" + "3" * 32, "2026-08-02T10:00:01Z", grant["expires_at"])
        started.update(approval_event_id=grant["event_id"], approval_sha256=self.canonical.canonical_json_sha256(grant))
        finished = _common(binding, "attempt_finished", "event-" + "4" * 32, "2026-08-02T10:00:02Z", grant["expires_at"])
        finished.update(attempt_started_event_id=started["event_id"], exit_class="success", exit_code=0)
        wrong_binding = _common(other_binding, "attempt_finished", "event-" + "5" * 32, "2026-08-02T10:00:02Z", grant["expires_at"])
        wrong_binding.update(attempt_started_event_id=started["event_id"], exit_class="success", exit_code=0)
        cases = (
            (started, grant),
            (grant, finished, started),
            (grant, dict(started, approval_sha256="9" * 64)),
            (grant, started, wrong_binding),
            (grant, started, dict(finished, expires_at="2026-08-02T10:14:59Z")),
            (grant, started, dict(finished, recorded_at="2026-08-02T10:00:00Z")),
            (grant, started, finished, dict(finished, event_id="event-" + "6" * 32)),
        )
        for index, events in enumerate(cases):
            with self.subTest(index=index):
                target = self.workdir / f"invalid-relationship-{index}.jsonl"
                target.write_bytes(b"".join(self.canonical.canonical_json_bytes(event) + b"\n" for event in events))
                os.chmod(target, 0o600)
                with self.assertRaises(self.ledger.MalformedLedgerEntryError):
                    self.ledger.append_event(target, _grant(binding, "8"))


class CeremonyTests(LedgerTestCase):
    def run_ceremony(self, line, input_tty=True, output_tty=True):
        binding = _binding(self.ledger)
        source = _TTY(line) if input_tty else io.StringIO(line)
        sink = _TTY() if output_tty else io.StringIO()
        with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH), mock.patch.object(self.ledger, "_new_event_id", return_value="event-" + "a" * 32):
            event = self.ledger.approve_interactively(binding, "2026-08-02T10:15:00Z", self.path, source, sink)
        return event, sink

    def test_exact_lf_and_crlf_confirmation_grant_without_persisting_typed_text(self):
        expected = f"approve {_ALIAS} {_INVOCATION_ID}"
        for terminator in ("\n", "\r\n"):
            with self.subTest(terminator=repr(terminator)):
                target = self.workdir / ("lf.jsonl" if terminator == "\n" else "crlf.jsonl")
                old = self.path
                self.path = target
                event, _ = self.run_ceremony(expected + terminator)
                self.path = old
                self.assertEqual("approval_granted", event["event_type"])
                self.assertNotIn(expected.encode(), target.read_bytes())

    def test_mismatch_eof_and_non_tty_outcomes_are_closed_and_never_grant(self):
        expected = f"approve {_ALIAS} {_INVOCATION_ID}"
        cases = (
            (" " + expected + "\n", True, True, "mismatch"),
            (expected.upper() + "\n", True, True, "mismatch"),
            (expected + " extra\n", True, True, "mismatch"),
            ("\n", True, True, "mismatch"),
            (expected + "\r", True, True, "mismatch"),
            ("", True, True, "eof"),
            (expected + "\n", False, True, "input-not-tty"),
            (expected + "\n", True, False, "output-not-tty"),
        )
        for index, (line, input_tty, output_tty, result) in enumerate(cases):
            with self.subTest(result=result, index=index):
                self.path = self.workdir / f"ceremony-{index}.jsonl"
                event, _ = self.run_ceremony(line, input_tty, output_tty)
                self.assertEqual("confirmation_failed", event["event_type"])
                self.assertEqual(result, event["confirmation_result"])
                self.assertEqual(0, sum(item["event_type"] == "approval_granted" for item in self.read_events()))
        self.path = self.workdir / "ceremony-repeated-terminator.jsonl"
        binding = _binding(self.ledger)
        with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH), mock.patch.object(self.ledger, "_new_event_id", return_value="event-" + "b" * 32):
            event = self.ledger.approve_interactively(
                binding,
                "2026-08-02T10:15:00Z",
                self.path,
                _FixedLineTTY(expected + "\n\n"),
                _TTY(),
            )
        self.assertEqual("mismatch", event["confirmation_result"])

    def test_input_tty_failure_has_precedence_and_output_is_not_inspected(self):
        binding = _binding(self.ledger)
        output = _ExplodingTTY()
        with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH), mock.patch.object(self.ledger, "_new_event_id", return_value="event-" + "a" * 32):
            event = self.ledger.approve_interactively(binding, "2026-08-02T10:15:00Z", self.path, io.StringIO("ignored"), output)
        self.assertEqual("input-not-tty", event["confirmation_result"])

    def test_clock_is_sampled_once_and_expiry_must_be_canonical_future(self):
        binding = _binding(self.ledger)
        clock = mock.Mock(side_effect=[_EPOCH, AssertionError("second clock read")])
        with mock.patch.object(self.ledger, "_utc_now", clock), mock.patch.object(self.ledger, "_new_event_id", return_value="event-" + "a" * 32):
            self.ledger.approve_interactively(binding, "2026-08-02T10:15:00Z", self.path, _TTY(f"approve {_ALIAS} {_INVOCATION_ID}\n"), _TTY())
        self.assertEqual(1, clock.call_count)
        for expiry in ("2026-08-02T10:00:00Z", "2026-08-02T10:00:00+00:00", "2026-02-30T10:00:00Z"):
            with self.subTest(expiry=expiry), mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH):
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.approve_interactively(binding, expiry, self.workdir / "never.jsonl", _TTY(), _TTY())

    def test_stream_inspection_prompt_flush_and_read_exceptions_append_nothing(self):
        binding = _binding(self.ledger)

        class BrokenOutput(_TTY):
            def write(self, value):
                raise OSError("private")

        class BrokenFlush(_TTY):
            def flush(self):
                raise OSError("private")

        class BrokenRead(_TTY):
            def readline(self, *args):
                raise OSError("private")

        streams = (
            (_ExplodingTTY(), _TTY()),
            (_TTY("line\n"), _ExplodingTTY()),
            (_TTY("line\n"), BrokenOutput()),
            (_TTY("line\n"), BrokenFlush()),
            (BrokenRead(), _TTY()),
        )
        for index, (source, sink) in enumerate(streams):
            with self.subTest(index=index), mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH):
                target = self.workdir / f"io-{index}.jsonl"
                with self.assertRaises(self.ledger.CeremonyIOError):
                    self.ledger.approve_interactively(binding, "2026-08-02T10:15:00Z", target, source, sink)
                self.assertFalse(target.exists())

    def test_persistence_failure_propagates_without_claiming_an_event(self):
        binding = _binding(self.ledger)
        with mock.patch.object(self.ledger, "_utc_now", return_value=_EPOCH), mock.patch.object(self.ledger, "append_event", side_effect=self.ledger.LedgerIOError("static")):
            with self.assertRaises(self.ledger.LedgerIOError):
                self.ledger.approve_interactively(binding, "2026-08-02T10:15:00Z", self.path, _TTY(f"approve {_ALIAS} {_INVOCATION_ID}\n"), _TTY())


class ConsumeTests(LedgerTestCase):
    def test_absent_failed_only_future_expired_and_exact_expiry_fail_closed(self):
        binding = _binding(self.ledger)
        with self.assertRaises(self.ledger.AbsentApprovalError):
            self.ledger.consume_approval_and_start(self.path, binding, _EPOCH)
        cases = (
            (_failed(binding), self.ledger.AbsentApprovalError, _EPOCH),
            (_grant(binding, recorded="2026-08-02T10:00:02Z"), self.ledger.FutureIssuedApprovalError, _EPOCH),
            (_grant(binding, recorded="2026-08-02T09:45:00Z", expires="2026-08-02T09:59:59Z"), self.ledger.ExpiredApprovalError, _EPOCH),
            (_grant(binding, recorded="2026-08-02T09:45:00Z", expires="2026-08-02T10:00:00Z"), self.ledger.ExpiredApprovalError, _EPOCH),
        )
        for index, (event, error, now) in enumerate(cases):
            with self.subTest(error=error.__name__):
                target = self.workdir / f"consume-{index}.jsonl"
                self.ledger.append_event(target, event)
                with self.assertRaises(error):
                    self.ledger.consume_approval_and_start(target, binding, now)

    def test_each_binding_mismatch_fails_with_specific_static_error(self):
        self.append_grant()
        cases = (
            ({"alias": "ollama-local"}, self.ledger.WrongAliasError),
            ({"registry_sha256": "5" * 64}, self.ledger.StaleRegistryDigestError),
            ({"task_sha256": "6" * 64}, self.ledger.StaleTaskDigestError),
            ({"prompt_sha256": "7" * 64}, self.ledger.StalePromptDigestError),
            ({"scope_sha256": "8" * 64}, self.ledger.StaleScopeDigestError),
        )
        for change, error in cases:
            with self.subTest(error=error.__name__):
                with self.assertRaises(error):
                    self.ledger.consume_approval_and_start(self.path, _binding(self.ledger, **change), _EPOCH + datetime.timedelta(seconds=1))

    def test_ledger_order_selects_last_eligible_across_mixed_histories(self):
        binding = _binding(self.ledger)
        histories = (
            (
                _grant(binding, "1", recorded="2026-08-02T09:45:00Z", expires="2026-08-02T09:59:59Z"),
                _grant(binding, "2", recorded="2026-08-02T10:00:00Z", expires="2026-08-02T10:15:00Z"),
            ),
            (
                _grant(binding, "1", recorded="2026-08-02T10:00:02Z", expires="2026-08-02T10:15:00Z"),
                _grant(binding, "2", recorded="2026-08-02T10:00:00Z", expires="2026-08-02T10:15:00Z"),
            ),
            (
                _grant(binding, "1", recorded="2026-08-02T10:00:00Z", expires="2026-08-02T10:15:00Z"),
                _grant(binding, "2", recorded="2026-08-02T10:00:02Z", expires="2026-08-02T10:15:00Z"),
            ),
            (
                _grant(binding, "1", recorded="2026-08-02T10:00:00Z", expires="2026-08-02T10:15:00Z"),
                _grant(binding, "2", recorded="2026-08-02T09:45:00Z", expires="2026-08-02T09:59:59Z"),
            ),
        )
        expected = (1, 1, 0, 0)
        for index, history in enumerate(histories):
            with self.subTest(index=index):
                target = self.workdir / f"history-{index}.jsonl"
                for event in history:
                    self.ledger.append_event(target, event)
                result = self.ledger.consume_approval_and_start(target, binding, _EPOCH + datetime.timedelta(seconds=1))
                self.assertEqual(history[expected[index]]["event_id"], result["approval_event_id"])

    def test_successful_start_returns_exact_closed_object_and_is_single_use_despite_new_grant(self):
        binding, grant = self.append_grant()
        now = _EPOCH + datetime.timedelta(seconds=1)
        result = self.ledger.consume_approval_and_start(self.path, binding, now)
        self.assertEqual(
            {"approval_event_id", "approval_sha256", "attempt_started_event_id", "expires_at"},
            set(result),
        )
        self.assertEqual(grant["event_id"], result["approval_event_id"])
        self.assertEqual(self.canonical.canonical_json_sha256(grant), result["approval_sha256"])
        self.ledger.append_event(self.path, _grant(binding, "2"))
        with self.assertRaises(self.ledger.ReplayedInvocationError):
            self.ledger.consume_approval_and_start(self.path, binding, now)
        self.assertEqual(1, sum(event["event_type"] == "attempt_started" for event in self.read_events()))

    def test_malformed_complete_ledger_blocks_consumption_without_prefix_recovery(self):
        binding, _ = self.append_grant()
        with self.path.open("ab") as handle:
            handle.write(b"{not-json}\n")
        with self.assertRaises(self.ledger.MalformedLedgerEntryError):
            self.ledger.consume_approval_and_start(self.path, binding, _EPOCH + datetime.timedelta(seconds=1))


class FinishTests(LedgerTestCase):
    def test_finish_signature_all_valid_outcomes_and_exact_closed_return(self):
        import inspect

        self.assertEqual(
            ("ledger_path", "binding", "attempt_started_event_id", "exit_class", "exit_code", "now"),
            tuple(inspect.signature(self.ledger.finish_attempt).parameters),
        )
        outcomes = (("success", 0), ("nonzero-exit", 4), ("nonzero-exit", -9), ("launch-error", None), ("timeout", None), ("output-limit-exceeded", None))
        for index, (exit_class, exit_code) in enumerate(outcomes):
            with self.subTest(outcome=(exit_class, exit_code)):
                self.path = self.workdir / f"finish-{index}.jsonl"
                binding, _, start = self.start_attempt()
                result = self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], exit_class, exit_code, _EPOCH + datetime.timedelta(seconds=2))
                self.assertEqual({"attempt_finished_event_id", "attempt_started_event_id", "recorded_at"}, set(result))
                self.assertEqual(start["attempt_started_event_id"], result["attempt_started_event_id"])
                self.assertEqual("2026-08-02T10:00:02Z", result["recorded_at"])

    def test_finish_rejects_invalid_pairings_missing_id_wrong_binding_and_backwards_time(self):
        binding, _, start = self.start_attempt()
        invalid_pairs = (("success", True), ("success", 1), ("nonzero-exit", 0), ("nonzero-exit", None), ("launch-error", 1), ("timeout", 1), ("output-limit-exceeded", 1))
        for exit_class, exit_code in invalid_pairs:
            with self.subTest(pair=(exit_class, exit_code)):
                with self.assertRaises(self.ledger.EventValidationError):
                    self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], exit_class, exit_code, _EPOCH + datetime.timedelta(seconds=2))
        for start_id in ("bad", "event-" + "9" * 32):
            with self.subTest(start_id=start_id):
                with self.assertRaises(self.ledger.FinishAttemptError):
                    self.ledger.finish_attempt(self.path, binding, start_id, "success", 0, _EPOCH + datetime.timedelta(seconds=2))
        with self.assertRaises(self.ledger.FinishAttemptError):
            self.ledger.finish_attempt(self.path, _binding(self.ledger, task_sha256="6" * 64), start["attempt_started_event_id"], "success", 0, _EPOCH + datetime.timedelta(seconds=2))
        with self.assertRaises(self.ledger.FinishAttemptError):
            self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], "success", 0, _EPOCH)

    def test_finish_copies_expiry_and_allows_before_equal_or_after_expiry(self):
        times = (
            _EPOCH + datetime.timedelta(seconds=2),
            _EPOCH + datetime.timedelta(minutes=15),
            _EPOCH + datetime.timedelta(minutes=16),
        )
        for index, now in enumerate(times):
            with self.subTest(now=now):
                self.path = self.workdir / f"expiry-{index}.jsonl"
                binding, _, start = self.start_attempt()
                self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], "success", 0, now)
                events = self.read_events()
                self.assertEqual(events[-2]["expires_at"], events[-1]["expires_at"])

    def test_second_finish_is_rejected_and_never_enables_another_start(self):
        binding, _, start = self.start_attempt()
        self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], "success", 0, _EPOCH + datetime.timedelta(seconds=2))
        with self.assertRaises(self.ledger.FinishAttemptError):
            self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], "success", 0, _EPOCH + datetime.timedelta(seconds=3))
        self.ledger.append_event(self.path, _grant(binding, "2"))
        with self.assertRaises(self.ledger.ReplayedInvocationError):
            self.ledger.consume_approval_and_start(self.path, binding, _EPOCH + datetime.timedelta(seconds=3))

    def test_finish_uses_same_locked_descriptor_and_propagates_durability_failures(self):
        binding, _, start = self.start_attempt()
        descriptors = []
        original_read = self.ledger._read_locked
        original_append = self.ledger._append_on_locked_fd

        def read(descriptor):
            descriptors.append(descriptor)
            return original_read(descriptor)

        def append(descriptor, handle, events, event):
            descriptors.append(descriptor)
            return original_append(descriptor, handle, events, event)

        with mock.patch.object(self.ledger, "_read_locked", side_effect=read), mock.patch.object(self.ledger, "_append_on_locked_fd", side_effect=append):
            self.ledger.finish_attempt(self.path, binding, start["attempt_started_event_id"], "success", 0, _EPOCH + datetime.timedelta(seconds=2))
        self.assertEqual(1, len(set(descriptors)))

        for seam in ("_write_chunk", "_flush", "_fsync"):
            with self.subTest(seam=seam):
                target = self.workdir / f"failure-{seam}.jsonl"
                self.path = target
                binding, _, start = self.start_attempt()
                kwargs = {"return_value": 0} if seam == "_write_chunk" else {"side_effect": OSError("private")}
                with mock.patch.object(self.ledger, seam, **kwargs):
                    with self.assertRaises(self.ledger.LedgerIOError):
                        self.ledger.finish_attempt(target, binding, start["attempt_started_event_id"], "success", 0, _EPOCH + datetime.timedelta(seconds=2))


class ProcessContentionTests(LedgerTestCase):
    def test_two_appenders_with_same_event_id_produce_one_durable_event(self):
        event = _grant(_binding(self.ledger))
        outcome_a, outcome_b = self.run_two(
            _append_worker,
            (str(self.path), event),
            (str(self.path), event),
        )
        self.assertEqual(1, [outcome_a, outcome_b].count("ok"))
        self.assertEqual(1, len(self.read_events()))

    def test_two_consumers_produce_one_durable_start(self):
        self.append_grant()
        outcome_a, outcome_b = self.run_two(
            _consume_worker,
            (str(self.path),),
            (str(self.path),),
        )
        self.assertEqual(1, [outcome_a, outcome_b].count("ok"))
        self.assertEqual(1, sum(event["event_type"] == "attempt_started" for event in self.read_events()))

    def test_two_finishers_produce_one_durable_finish(self):
        _, _, start = self.start_attempt()
        start_id = start["attempt_started_event_id"]
        outcome_a, outcome_b = self.run_two(
            _finish_worker,
            (str(self.path), start_id),
            (str(self.path), start_id),
        )
        self.assertEqual(1, [outcome_a, outcome_b].count("ok"))
        self.assertEqual(1, sum(event["event_type"] == "attempt_finished" for event in self.read_events()))


if __name__ == "__main__":
    unittest.main()
