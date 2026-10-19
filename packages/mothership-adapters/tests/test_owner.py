from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from mothership_adapters import evidence as evidence_module
from mothership_adapters.evidence import export_evidence, inspect_evidence


ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "packages" / "mothership-adapters"
GITHUB_ROOT = ROOT / "packages" / "mothership-github"
PYTHON = Path(sys.executable)

PARAMETERS = {
    "repository": "example/repo",
    "pull_request": 7,
    "expected_head_sha": "a" * 40,
    "expected_base": "main",
    "merge_method": "merge",
}
CONTEXT = {
    "host_id": "owner-test",
    "session_id": "session",
    "actor_id": "actor",
    "runtime_generation": "generation",
    "scope": ["github.merge_pr"],
}
EXECUTOR_REF = {"ref_id": "executor:owner-test", "sha256": "c" * 64}


def _frame(owner_id, frame_type, seq, request_id, action_id, payload, reply_to=None):
    return {
        "schema_version": "mothership-owner.v0",
        "type": frame_type,
        "seq": seq,
        "reply_to": reply_to,
        "owner_id": owner_id,
        "request_id": request_id,
        "action_id": action_id,
        "payload": payload,
    }


class ChildDriver:
    def __init__(self, *, parent_pid: int | None = None, session_diagnostics=False):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.owner_id = "owner-test-nonce"
        self.schema = "mothership-owner.v1" if session_diagnostics else "mothership-owner.v0"
        self.authority = root / "authority.jsonl"
        self.attempts = root / "attempts.jsonl"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(PACKAGE_ROOT), str(GITHUB_ROOT)))
        self.process = subprocess.Popen(
            [
                str(PYTHON),
                "-B",
                "-m",
                "mothership_adapters.owner",
                "--owner-id",
                self.owner_id,
                "--parent-pid",
                str(os.getpid() if parent_pid is None else parent_pid),
                "--authority-path",
                str(self.authority),
                "--attempts-path",
                str(self.attempts),
                *(["--session-diagnostics"] if session_diagnostics else []),
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.parent_seq = 0
        self.request_id = None
        self.action_id = None
        self.get_callbacks = 0
        self.merge_callbacks = 0

    def close(self):
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        self.process.stdout.read()
        self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.temp.cleanup()

    def send(self, frame_type, payload, *, request_id=None, action_id=None):
        self.parent_seq += 1
        frame = _frame(
            self.owner_id,
            frame_type,
            self.parent_seq,
            self.request_id if request_id is None else request_id,
            self.action_id if action_id is None else action_id,
            payload,
        )
        frame["schema_version"] = self.schema
        self.process.stdin.write(
            (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        self.process.stdin.flush()
        return frame

    def read(self):
        raw = self.process.stdout.readline(65537)
        if not raw:
            raise AssertionError(f"child EOF; stderr={self.process.stderr.read().decode(errors='replace')}")
        value = json.loads(raw)
        if value.get("type") == "get":
            self.get_callbacks += 1
        elif value.get("type") == "merge":
            self.merge_callbacks += 1
        return value

    def reply_callback(
        self,
        callback,
        payload,
        *,
        frame_type="result",
        request_id=None,
        action_id=None,
        reply_to=None,
    ):
        self.parent_seq += 1
        response = _frame(
            self.owner_id,
            frame_type,
            self.parent_seq,
            callback["request_id"] if request_id is None else request_id,
            callback["action_id"] if action_id is None else action_id,
            payload,
            reply_to=callback["seq"] if reply_to is None else reply_to,
        )
        response["schema_version"] = self.schema
        self.process.stdin.write(
            (json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        self.process.stdin.flush()

    def finish_prepare(self):
        callback = self.read()
        self.assert_frame(callback, "context", 1, None, None)
        self.reply_callback(callback, copy.deepcopy(CONTEXT))
        result = self.read()
        assert result["type"] == "result"
        assert result["seq"] == 2
        assert result["reply_to"] == 1
        assert result["owner_id"] == self.owner_id
        request = result["payload"]
        self.request_id = request["request_id"]
        self.action_id = request["action"]["action_id"]
        assert result["request_id"] == self.request_id
        assert result["action_id"] == self.action_id
        return request

    def approve(self, request):
        response = {
            "schema_version": "authority-action-review-response.v0",
            "decision": "approve",
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "action_id": request["action"]["action_id"],
            "action_sha256": request["action_sha256"],
        }
        self.send("review", response)
        callback = self.read()
        self.assert_frame(callback, "context", 3, None, self.action_id)
        self.reply_callback(callback, copy.deepcopy(CONTEXT))
        result = self.read()
        self.assert_frame(result, "result", 4, 3, self.action_id)
        assert result["payload"] == "approve"
        return response

    def execute_result(self, *, drift=False, merge_error=False):
        self.send("execute", copy.deepcopy(PARAMETERS))
        callback = self.read()
        self.assert_frame(callback, "context", 5, None, self.action_id)
        self.reply_callback(callback, copy.deepcopy(CONTEXT))
        callback = self.read()
        self.assert_frame(callback, "context", 6, None, self.action_id)
        self.reply_callback(callback, copy.deepcopy(CONTEXT))
        get = self.read()
        self.assert_frame(get, "get", 7, None, self.action_id)
        assert {"repository", "pull_request"} == set(get["payload"])
        self.reply_callback(
            get,
            {
                "http_status": 200,
                "state": "open",
                "merged": False,
                "head_sha": PARAMETERS["expected_head_sha"],
                "base_ref": PARAMETERS["expected_base"],
            },
        )
        callback = self.read()
        self.assert_frame(callback, "context", 8, None, self.action_id)
        if drift:
            self.reply_callback(
                callback,
                {"host_id": "changed", "session_id": "session", "actor_id": "actor",
                 "runtime_generation": "generation", "scope": ["github.merge_pr"]},
            )
            result = self.read()
            self.assert_frame(result, "result", 9, 5, self.action_id)
            return result["payload"]
        else:
            self.reply_callback(callback, copy.deepcopy(CONTEXT))
        merge = self.read()
        self.assert_frame(merge, "merge", 9, None, self.action_id)
        if merge_error:
            self.reply_callback(merge, {"code": "transport"}, frame_type="error")
        else:
            self.reply_callback(merge, {
                "http_status": 200,
                "merged": True,
                "merge_commit_sha": "b" * 40,
            })
        result = self.read()
        self.assert_frame(result, "result", 10, 5, self.action_id)
        return result["payload"]

    def execute_success(self, *, drift=False):
        return self.execute_result(drift=drift)

    def assert_frame(self, value, frame_type, seq, reply_to, action_id):
        if value.get("type") != frame_type:
            raise AssertionError(value)
        assert {
            "schema_version", "type", "seq", "reply_to", "owner_id",
            "request_id", "action_id", "payload",
        } == set(value)
        assert value["schema_version"] == self.schema
        assert value["type"] == frame_type
        assert value["seq"] == seq
        assert value["reply_to"] == reply_to
        assert value["owner_id"] == self.owner_id
        assert value["request_id"] == (self.request_id if self.request_id is not None else None)
        assert value["action_id"] == action_id


class OwnerProtocolTests(unittest.TestCase):
    def tearDown(self):
        driver = getattr(self, "driver", None)
        if driver is not None:
            driver.close()

    def test_opt_in_diagnostic_is_from_the_matched_session_failure(self):
        self.driver = ChildDriver(session_diagnostics=True)
        driver = self.driver
        driver.send("prepare", {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF})
        request = driver.finish_prepare()
        driver.approve(request)
        driver.send("execute", copy.deepcopy(PARAMETERS))
        driver.reply_callback(driver.read(), copy.deepcopy(CONTEXT))
        driver.reply_callback(driver.read(), copy.deepcopy(CONTEXT))
        callback = driver.read()
        self.assertEqual("get", callback["type"])
        driver.reply_callback(callback, {"code": "transport"}, frame_type="error")
        error = driver.read()
        self.assertEqual("mothership-owner.v1", error["schema_version"])
        self.assertEqual(driver.request_id, error["request_id"])
        self.assertEqual(driver.action_id, error["action_id"])
        self.assertEqual(5, error["reply_to"])
        self.assertEqual({"code": "session", "diagnostic": {
            "code": "preflight_transport_failed", "phase": "preflight_transport",
            "authority_use": "unknown", "external_effect": "unknown",
            "next_check": "authority_and_attempt_records", "retry_allowed": False,
        }}, error["payload"])
        self.assertEqual(0, driver.merge_callbacks)
        self.assertFalse(driver.attempts.exists())

    def test_opt_in_does_not_accept_parent_supplied_diagnostics(self):
        self.driver = ChildDriver(session_diagnostics=True)
        driver = self.driver
        driver.send("prepare", {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF})
        callback = driver.read()
        driver.reply_callback(callback, {"code": "session", "diagnostic": {"phase": "parent-secret"}}, frame_type="error")
        error = driver.read()
        # Session construction wraps the rejected callback as its own unknown
        # SessionError; the untrusted parent's diagnostic is never forwarded.
        self.assertEqual({"code": "session", "diagnostic": {
            "code": "unknown", "phase": "unknown", "authority_use": "unknown",
            "external_effect": "unknown", "next_check": "existing_evidence_bundle",
            "retry_allowed": False,
        }}, error["payload"])
        self.assertFalse(driver.authority.exists())
        self.assertFalse(driver.attempts.exists())

    def test_protocol_version_mismatch_fails_without_a_diagnostic_or_records(self):
        for diagnostics in (False, True):
            with self.subTest(diagnostics=diagnostics):
                driver = ChildDriver(session_diagnostics=diagnostics)
                self.driver = driver
                driver.schema = "mothership-owner.v0" if diagnostics else "mothership-owner.v1"
                driver.send("prepare", {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF})
                error = driver.read()
                self.assertEqual({"code": "nonce"}, error["payload"])
                self.assertFalse(driver.authority.exists())
                self.assertFalse(driver.attempts.exists())
                driver.close()
                self.driver = None

    def test_real_child_success_uses_one_session_and_exact_callback_shapes(self):
        self.driver = ChildDriver()
        self.driver.send("prepare", {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF}, request_id=None, action_id=None)
        request = self.driver.finish_prepare()
        self.assertEqual(PARAMETERS, request["action"]["execution_parameters"])
        self.driver.approve(request)
        result = self.driver.execute_success()
        self.assertEqual("SUCCESS", result["receipt"]["status"])
        self.driver.send("cancel", {}, request_id=self.driver.request_id, action_id=self.driver.action_id)
        canceled = self.driver.read()
        self.assertEqual("error", canceled["type"])
        self.assertEqual("phase", canceled["payload"]["code"])

    def test_context_drift_after_get_consumes_without_put_and_returns_unknown(self):
        self.driver = ChildDriver()
        self.driver.send("prepare", {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF}, request_id=None, action_id=None)
        request = self.driver.finish_prepare()
        self.driver.approve(request)
        result = self.driver.execute_success(drift=True)
        self.assertEqual("reconciliation_required", result["status"])
        self.assertEqual("UNKNOWN", result["receipt"]["status"])

    def test_result_delivery_loss_recovery_and_replay_matrix(self):
        cases = (
            ("success_exact", False, False, "SUCCESS"),
            ("success_changed", False, True, "SUCCESS"),
            ("unknown_exact", True, False, "UNKNOWN"),
            ("unknown_changed", True, True, "UNKNOWN"),
        )
        for name, merge_error, changed_replay, expected_receipt in cases:
            with self.subTest(case=name):
                driver = ChildDriver()
                self.driver = driver
                try:
                    driver.send(
                        "prepare",
                        {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF},
                        request_id=None,
                        action_id=None,
                    )
                    request = driver.finish_prepare()
                    approval_response = driver.approve(request)

                    # The harness drains the reply without delivering it to the
                    # simulated application. Recovery uses retained review data
                    # and fixture records, never another execution.
                    _ = driver.execute_result(merge_error=merge_error)
                    authority_bytes = driver.authority.read_bytes()
                    attempts_bytes = driver.attempts.read_bytes()
                    authority_rows = [
                        json.loads(line) for line in authority_bytes.splitlines()
                    ]
                    attempt_rows = [
                        json.loads(line) for line in attempts_bytes.splitlines()
                    ]
                    self.assertEqual(
                        ["authority_action_approval", "authority_action_consume"],
                        [row["event_type"] for row in authority_rows],
                    )
                    self.assertEqual(
                        ["attempt_started", "attempt_finished"],
                        [row["event_type"] for row in attempt_rows],
                    )
                    self.assertEqual(1, driver.get_callbacks)
                    self.assertEqual(1, driver.merge_callbacks)

                    recovered = export_evidence(
                        request,
                        response=approval_response,
                        decision=authority_rows[0],
                        consume=authority_rows[1],
                        started=attempt_rows[0],
                        finished=attempt_rows[1],
                        executor_ref=EXECUTOR_REF,
                    )
                    for _reading in range(3):
                        exported = export_evidence(
                            request,
                            response=approval_response,
                            decision=authority_rows[0],
                            consume=authority_rows[1],
                            started=attempt_rows[0],
                            finished=attempt_rows[1],
                            executor_ref=EXECUTOR_REF,
                        )
                        self.assertEqual(recovered, exported)
                        inspection = inspect_evidence(exported)
                        summary = evidence_module.summarize_evidence(exported)
                        self.assertEqual(expected_receipt, inspection["receipt_status"])
                        self.assertEqual(["verification"], inspection["missing"])
                        self.assertIsNone(inspection["verification_status"])
                        self.assertEqual("source-unverified", inspection["source_status"])
                        self.assertFalse(inspection["authority"])
                        self.assertFalse(inspection["external_effect_verified"])
                        self.assertIsNone(exported["verification"])
                        self.assertIn(f"receipt: {expected_receipt}", summary)
                        self.assertIn("missing: verification", summary)
                        self.assertIn("source: source-unverified", summary)
                        self.assertIn("authority: false", summary)
                        self.assertIn("external effect verified: false", summary)

                    self.assertEqual(authority_bytes, driver.authority.read_bytes())
                    self.assertEqual(attempts_bytes, driver.attempts.read_bytes())
                    replay_parameters = copy.deepcopy(PARAMETERS)
                    if changed_replay:
                        replay_parameters["pull_request"] = 8
                    driver.send("execute", replay_parameters)
                    replay_error = driver.read()
                    driver.assert_frame(
                        replay_error, "error", 11, 11, driver.action_id
                    )
                    self.assertEqual({"code": "phase"}, replay_error["payload"])
                    driver.process.wait(timeout=5)
                    self.assertEqual(2, driver.process.returncode)
                    self.assertEqual(b"", driver.process.stdout.read())
                    self.assertEqual(1, driver.get_callbacks)
                    self.assertEqual(1, driver.merge_callbacks)
                    self.assertEqual(authority_bytes, driver.authority.read_bytes())
                    self.assertEqual(attempts_bytes, driver.attempts.read_bytes())
                    self.assertEqual(2, len(authority_rows))
                    self.assertEqual(2, len(attempt_rows))
                    self.assertEqual(
                        {request["action"]["action_id"]},
                        {
                            authority_rows[0]["action"]["action_id"],
                            authority_rows[1]["action_id"],
                            attempt_rows[0]["action_id"],
                            attempt_rows[1]["action_id"],
                        },
                    )
                finally:
                    driver.close()
                    self.driver = None

    def test_stale_callback_replies_fail_before_consume_matrix(self):
        cases = (
            ("stale_reply_to", {"reply_to": "stale"}),
            ("wrong_request_id", {"request_id": "request-stale"}),
            ("unsupported_ack_frame", {"frame_type": "ack"}),
        )
        for name, overrides in cases:
            with self.subTest(case=name):
                driver = ChildDriver()
                self.driver = driver
                try:
                    driver.send(
                        "prepare",
                        {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF},
                        request_id=None,
                        action_id=None,
                    )
                    request = driver.finish_prepare()
                    driver.approve(request)
                    authority_bytes = driver.authority.read_bytes()
                    driver.send("execute", copy.deepcopy(PARAMETERS))
                    callback = driver.read()
                    driver.assert_frame(callback, "context", 5, None, driver.action_id)
                    reply_overrides = dict(overrides)
                    if "reply_to" in reply_overrides:
                        # The context callback during review used owner sequence 3.
                        reply_overrides["reply_to"] = 3
                    driver.reply_callback(
                        callback,
                        copy.deepcopy(CONTEXT),
                        **reply_overrides,
                    )
                    error = driver.read()
                    driver.assert_frame(error, "error", 6, 5, driver.action_id)
                    self.assertEqual({"code": "session"}, error["payload"])
                    driver.process.wait(timeout=5)
                    self.assertEqual(2, driver.process.returncode)
                    self.assertEqual(b"", driver.process.stdout.read())
                    self.assertEqual(0, driver.get_callbacks)
                    self.assertEqual(0, driver.merge_callbacks)
                    self.assertEqual(authority_bytes, driver.authority.read_bytes())
                    self.assertEqual(
                        ["authority_action_approval"],
                        [
                            json.loads(line)["event_type"]
                            for line in authority_bytes.splitlines()
                        ],
                    )
                    self.assertFalse(driver.attempts.exists())
                finally:
                    driver.close()
                    self.driver = None

    def test_reject_does_not_request_transport_and_cancel_is_terminal(self):
        self.driver = ChildDriver()
        self.driver.send("prepare", {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF}, request_id=None, action_id=None)
        request = self.driver.finish_prepare()
        response = {
            "schema_version": "authority-action-review-response.v0",
            "decision": "reject",
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "action_id": request["action"]["action_id"],
            "action_sha256": request["action_sha256"],
        }
        self.driver.send("review", response)
        callback = self.driver.read()
        self.driver.assert_frame(callback, "context", 3, None, self.driver.action_id)
        self.driver.reply_callback(callback, copy.deepcopy(CONTEXT))
        result = self.driver.read()
        self.assertEqual("reject", result["payload"])
        self.driver.send("cancel", {})
        canceled = self.driver.read()
        self.assertEqual("error", canceled["type"])
        self.assertIn(canceled["payload"]["code"], {"phase", "session"})

    def test_wrong_parent_pid_fails_before_processing_a_frame(self):
        self.driver = ChildDriver(parent_pid=os.getpid() + 10000)
        self.driver.process.stdin.close()
        self.driver.process.wait(timeout=5)
        self.assertNotEqual(0, self.driver.process.returncode)

    def test_duplicate_and_oversized_frames_are_rejected(self):
        for raw in (
            b'{"schema_version":"mothership-owner.v0","schema_version":"mothership-owner.v0"}\n',
            b"{" + b'"schema_version":"mothership-owner.v0",' + b'"x":"' + b"a" * 66000 + b'"}\n',
        ):
            with self.subTest(size=len(raw)):
                driver = ChildDriver()
                self.driver = driver
                try:
                    driver.process.stdin.write(raw)
                    driver.process.stdin.close()
                except BrokenPipeError:
                    pass
                driver.process.wait(timeout=5)
                self.assertNotEqual(0, driver.process.returncode)
                stderr = driver.process.stderr.read()
                self.assertNotIn(b"Traceback", stderr)
                driver.close()
                self.driver = None

    def test_wrong_sequence_nonce_and_eof_are_terminal(self):
        driver = ChildDriver()
        self.driver = driver
        bad = _frame(driver.owner_id, "prepare", 2, None, None, {"parameters": PARAMETERS, "executor_ref": EXECUTOR_REF})
        driver.process.stdin.write((json.dumps(bad, separators=(",", ":")) + "\n").encode())
        driver.process.stdin.flush()
        driver.process.stdin.close()
        driver.process.wait(timeout=5)
        self.assertNotEqual(0, driver.process.returncode)
        driver.close()
        self.driver = None


if __name__ == "__main__":
    unittest.main()
