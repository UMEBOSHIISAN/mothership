"""Closed argv, TTY, output, and authority-boundary tests for llm-seat."""

from __future__ import annotations

import datetime
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


_TMP_ROOT = pathlib.Path(tempfile.gettempdir()).resolve() / "mothership-seat-cli-tests"
_SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CLI_PATH = _SOURCE_ROOT / "orchestration/bin/llm-seat"
_ALIAS = "codex-cli"
_INVOCATION_ID = "invocation-05t-001"
_REGISTRY = "1" * 64
_TASK = "2" * 64
_PROMPT = "3" * 64
_SCOPE = "4" * 64
_EPOCH = datetime.datetime(2026, 8, 2, 10, 0, 0, tzinfo=datetime.UTC)


class _TTY(io.StringIO):
    def isatty(self):
        return True


class _BrokenOutput(_TTY):
    def write(self, value):
        raise OSError("private output detail")


def _invocation_digest():
    raw = (
        f"registry_sha256={_REGISTRY}\n"
        f"task_sha256={_TASK}\n"
        f"prompt_sha256={_PROMPT}\n"
        f"scope_sha256={_SCOPE}\n"
        f"invocation_id={_INVOCATION_ID}\n"
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _load_cli():
    name = "friend_mothership_llm_seat_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(_CLI_PATH))
    spec = importlib.util.spec_from_file_location(name, _CLI_PATH, loader=loader)
    if spec is None or spec.loader is None:
        raise ImportError("llm-seat loader unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _argv(path):
    return [
        "approve",
        "--ledger",
        str(path),
        "--alias",
        _ALIAS,
        "--invocation-id",
        _INVOCATION_ID,
        "--registry-sha256",
        _REGISTRY,
        "--task-sha256",
        _TASK,
        "--prompt-sha256",
        _PROMPT,
        "--scope-sha256",
        _SCOPE,
        "--invocation-sha256",
        _invocation_digest(),
        "--expires-at",
        "2026-08-02T10:15:00Z",
    ]


class SeatCliTestCase(unittest.TestCase):
    def setUp(self):
        self.module = _load_cli()
        _TMP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(_TMP_ROOT, 0o700)
        self._temporary = tempfile.TemporaryDirectory(dir=_TMP_ROOT)
        self.workdir = pathlib.Path(self._temporary.name)
        self.path = self.workdir / "approvals.jsonl"

    def tearDown(self):
        self._temporary.cleanup()
        _TMP_ROOT.rmdir()

    def call(self, argv=None, source=None, sink=None, errors=None):
        source = _TTY(f"approve {_ALIAS} {_INVOCATION_ID}\n") if source is None else source
        sink = io.StringIO() if sink is None else sink
        errors = _TTY() if errors is None else errors
        with mock.patch.object(self.module.ledger, "_utc_now", return_value=_EPOCH):
            code = self.module.main(
                _argv(self.path) if argv is None else argv,
                input_stream=source,
                output_stream=sink,
                error_stream=errors,
            )
        return code, sink, errors

    def event_from(self, sink):
        return json.loads(sink.getvalue())


class SeatCliShapeAndGrammarTests(SeatCliTestCase):
    def test_executable_mode_shebang_and_main_signature_are_exact(self):
        import inspect

        self.assertEqual(0o755, stat.S_IMODE(os.stat(_CLI_PATH).st_mode))
        self.assertEqual(b"#!/usr/bin/env python3\n", _CLI_PATH.read_bytes().splitlines(keepends=True)[0])
        self.assertEqual(
            ("argv", "input_stream", "output_stream", "error_stream"),
            tuple(inspect.signature(self.module.main).parameters),
        )

    def test_reordered_nine_options_are_accepted_exactly_once(self):
        argv = _argv(self.path)
        pairs = [argv[index : index + 2] for index in range(1, len(argv), 2)]
        reordered = ["approve", *sum(reversed(pairs), [])]
        code, sink, _ = self.call(argv=reordered)
        self.assertEqual(0, code)
        self.assertEqual("approval_granted", self.event_from(sink)["event_type"])

    def test_missing_duplicate_unknown_positional_abbreviation_equals_and_help_are_rejected_before_append(self):
        valid = _argv(self.path)
        cases = (
            valid[:-2],
            valid[:-2] + ["--ledger", str(self.path)],
            valid[:-2] + ["--unknown", "value"],
            valid + ["positional"],
            ["approve", "--led", str(self.path), *valid[3:]],
            ["approve", f"--ledger={self.path}", *valid[3:]],
            ["approve", "--help"],
            ["approve", "-h"],
            ["list", *valid[1:]],
            ["verify", *valid[1:]],
            [],
        )
        for index, argv in enumerate(cases):
            with self.subTest(index=index):
                target = self.workdir / f"invalid-{index}.jsonl"
                rewritten = [str(target) if item == str(self.path) else item for item in argv]
                code, sink, errors = self.call(argv=rewritten)
                self.assertEqual(2, code)
                self.assertEqual("", sink.getvalue())
                self.assertEqual("llm-seat: invalid arguments\n", errors.getvalue())
                self.assertFalse(target.exists())

    def test_relative_root_non_normalized_and_invocation_digest_mismatch_fail_before_open(self):
        cases = []
        for value in ("relative.jsonl", "/", str(self.workdir / "x/../ledger.jsonl")):
            argv = _argv(self.path)
            argv[argv.index("--ledger") + 1] = value
            cases.append(argv)
        mismatch = _argv(self.path)
        mismatch[mismatch.index("--invocation-sha256") + 1] = "f" * 64
        cases.append(mismatch)
        for index, argv in enumerate(cases):
            with self.subTest(index=index):
                target = self.workdir / f"never-{index}.jsonl"
                with mock.patch.object(self.module.ledger, "approve_interactively") as approve:
                    code, sink, errors = self.call(argv=argv)
                self.assertEqual(2, code)
                self.assertEqual("", sink.getvalue())
                self.assertIn("invalid arguments", errors.getvalue())
                approve.assert_not_called()
                self.assertFalse(target.exists())

    def test_invalid_binding_and_expiry_map_to_static_usage_failure(self):
        cases = []
        for option, value in (
            ("--alias", "gemma"),
            ("--invocation-id", "bad invocation"),
            ("--registry-sha256", "A" * 64),
            ("--expires-at", "2026-08-02T10:00:00Z"),
            ("--expires-at", "2026-08-02T10:15:00+00:00"),
        ):
            argv = _argv(self.path)
            argv[argv.index(option) + 1] = value
            if option != "--expires-at":
                argv[argv.index("--invocation-sha256") + 1] = _invocation_digest()
            cases.append(argv)
        for index, argv in enumerate(cases):
            with self.subTest(index=index):
                code, sink, errors = self.call(argv=argv)
                self.assertEqual(2, code)
                self.assertEqual("", sink.getvalue())
                self.assertEqual("llm-seat: invalid arguments\n", errors.getvalue())


class SeatCliOutcomeTests(SeatCliTestCase):
    def test_success_writes_one_canonical_json_object_and_lf_to_stdout(self):
        code, sink, errors = self.call()
        self.assertEqual(0, code)
        event = self.event_from(sink)
        expected = self.module.canonical.canonical_json_bytes(event).decode() + "\n"
        self.assertEqual(expected, sink.getvalue())
        self.assertEqual("approval_granted", event["event_type"])
        self.assertIn(f"approve {_ALIAS} {_INVOCATION_ID}", errors.getvalue())

    def test_every_durable_confirmation_failure_writes_canonical_json_and_exits_two(self):
        cases = (
            (io.StringIO("ignored\n"), _TTY(), "input-not-tty"),
            (_TTY("ignored\n"), io.StringIO(), "output-not-tty"),
            (_TTY("wrong\n"), _TTY(), "mismatch"),
            (_TTY(""), _TTY(), "eof"),
        )
        for index, (source, errors, result) in enumerate(cases):
            with self.subTest(result=result):
                self.path = self.workdir / f"failed-{index}.jsonl"
                code, sink, _ = self.call(source=source, errors=errors)
                self.assertEqual(2, code)
                event = self.event_from(sink)
                self.assertEqual("confirmation_failed", event["event_type"])
                self.assertEqual(result, event["confirmation_result"])
                self.assertEqual(self.module.canonical.canonical_json_bytes(event) + b"\n", sink.getvalue().encode())

    def test_ledger_and_ceremony_failures_exit_one_with_opaque_static_stderr(self):
        failures = (
            (self.module.ledger.LedgerIOError("/sensitive/path secret"), "ledger operation failed"),
            (self.module.ledger.CeremonyIOError("typed text secret"), "approval ceremony failed"),
        )
        for error, message in failures:
            with self.subTest(error=type(error).__name__):
                sink = io.StringIO()
                errors = _TTY()
                with mock.patch.object(self.module.ledger, "approve_interactively", side_effect=error):
                    code = self.module.main(_argv(self.path), _TTY(), sink, errors)
                self.assertEqual(1, code)
                self.assertEqual("", sink.getvalue())
                self.assertIn(message, errors.getvalue())
                for forbidden in ("/sensitive/path", "secret", _REGISTRY, _PROMPT):
                    self.assertNotIn(forbidden, errors.getvalue())

    def test_stdout_failure_after_durable_grant_exits_one_without_rollback_or_retry(self):
        sink = _BrokenOutput()
        code, _, errors = self.call(sink=sink)
        self.assertEqual(1, code)
        self.assertIn("result output failed", errors.getvalue())
        lines = self.path.read_bytes().splitlines()
        self.assertEqual(1, len(lines))
        self.assertEqual("approval_granted", json.loads(lines[0])["event_type"])

    def test_event_keys_exclude_private_authority_and_content_fields(self):
        _, sink, _ = self.call()
        keys = {key.lower() for key in self.event_from(sink)}
        forbidden = (
            "quote",
            "typed",
            "prompt_text",
            "output",
            "task_content",
            "secret",
            "credential",
            "host",
            "model_path",
            "environment",
            "recommendation",
            "selected_alias",
            "actual_alias",
            "authority_effect",
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertFalse(any(fragment in key for key in keys))

    def test_success_path_never_launches_routes_models_networks_or_retries(self):
        import socket
        import subprocess

        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("launch")) as popen, mock.patch.object(subprocess, "run", side_effect=AssertionError("run")) as run, mock.patch.object(socket, "create_connection", side_effect=AssertionError("network")) as connect:
            code, sink, _ = self.call()
        self.assertEqual(0, code)
        self.assertEqual("approval_granted", self.event_from(sink)["event_type"])
        popen.assert_not_called()
        run.assert_not_called()
        connect.assert_not_called()
        self.assertEqual(1, len(self.path.read_bytes().splitlines()))


if __name__ == "__main__":
    unittest.main()
