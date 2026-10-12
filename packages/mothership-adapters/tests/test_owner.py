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


ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "packages" / "mothership-adapters"
GITHUB_ROOT = ROOT / "packages" / "mothership-github"
PYTHON = ROOT.parent / "ci-venv" / "bin" / "python"

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
    def __init__(self, *, parent_pid: int | None = None):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.owner_id = "owner-test-nonce"
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
        self.process.stdin.write(
            (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        self.process.stdin.flush()
        return frame

    def read(self):
        raw = self.process.stdout.readline(65537)
        if not raw:
            raise AssertionError(f"child EOF; stderr={self.process.stderr.read().decode(errors='replace')}")
        return json.loads(raw)

    def reply_callback(self, callback, payload):
        self.parent_seq += 1
        response = _frame(
            self.owner_id,
            "result",
            self.parent_seq,
            callback["request_id"],
            callback["action_id"],
            payload,
            reply_to=callback["seq"],
        )
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

    def execute_success(self, *, drift=False):
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
        self.reply_callback(merge, {
            "http_status": 200,
            "merged": True,
            "merge_commit_sha": "b" * 40,
        })
        result = self.read()
        self.assert_frame(result, "result", 10, 5, self.action_id)
        return result["payload"]

    def assert_frame(self, value, frame_type, seq, reply_to, action_id):
        if value.get("type") != frame_type:
            raise AssertionError(value)
        assert {
            "schema_version", "type", "seq", "reply_to", "owner_id",
            "request_id", "action_id", "payload",
        } == set(value)
        assert value["schema_version"] == "mothership-owner.v0"
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
