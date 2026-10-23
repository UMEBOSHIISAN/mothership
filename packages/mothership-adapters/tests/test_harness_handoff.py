"""Local-only integration: real Git/Core/ledgers, injected external I/O."""
from __future__ import annotations

import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mothership_adapters.harness_handoff import (
    ThinHarnessOwner, HandoffError, collect_response, decode_handoff_json,
    validate_preview,
)
from mothership_adapters.evidence import inspect_evidence
from mothership_adapters.session import SessionError


CONTEXT = dict(host_id="synthetic", session_id="one", actor_id="test",
               runtime_generation="one", scope=["github.merge_pr"])
REF = dict(ref_id="executor:synthetic", sha256="e" * 64)
REQUEST = "隔離したPRを確認する"
INTERPRETATION = {"candidate_actions": ["PRを確認する"], "work_type": "EDIT_CREATE"}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def preview():
    return dict(schema_version="ume.preview-handoff.v0", source="offline_interpretation",
                request_sha256=hashlib.sha256(REQUEST.encode()).hexdigest(),
                interpretation_sha256=hashlib.sha256(encoded(INTERPRETATION)).hexdigest(),
                work_type="EDIT_CREATE", classification_status="RESOLVED",
                candidate_actions=["PRを確認する"], required_human_approvals=["外部操作の確認"],
                surfaced_unknowns=[], clarification_blocked=False,
                authority=False, execution=False)


def response(request, decision="approve"):
    return dict(schema_version="authority-action-review-response.v0", decision=decision,
                request_id=request["request_id"], request_sha256=request["request_sha256"],
                action_id=request["action"]["action_id"], action_sha256=request["action_sha256"])


class Terminal(io.StringIO):
    def isatty(self):
        return True


class Transport:
    def __init__(self, parameters):
        self.parameters = parameters
        self.gets, self.puts = [], []
        self.on_get = lambda: None
        self.error = None

    def get_pull_request(self, repository, pull_request):
        self.gets.append((repository, pull_request))
        self.on_get()
        return dict(http_status=200, state="open", merged=False,
                    head_sha=self.parameters["expected_head_sha"], base_ref="canary-base")

    def merge_pull_request(self, **parameters):
        self.puts.append(parameters)
        if self.error:
            raise self.error
        return dict(http_status=200, merged=True, merge_commit_sha="b" * 40)


class HandoffInputTests(unittest.TestCase):
    def test_cli_invalid_input_stops_before_invoking_harness(self):
        from mothership_adapters.harness_handoff_cli import main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            malformed = root / "bad.json"
            malformed.write_text('{"repository":1,"repository":2}')
            with patch("subprocess.run", side_effect=AssertionError("must not invoke")), \
                 patch("sys.stderr", new=Terminal()), patch("sys.stdin", new=Terminal()):
                self.assertEqual(2, main([
                    "--harness-cli", str(root / "harness"), "--request", REQUEST,
                    "--interpretation-file", str(malformed), "--parameters", str(malformed),
                    "--host-context", str(malformed), "--worktree", str(root / "tree"),
                    "--run-directory", str(root / "run")]))
            self.assertFalse((root / "run").exists())

    def test_duplicate_nonfinite_utf8_depth_and_size_are_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'"\xff"',
                    b'[' * 18 + b'0' + b']' * 18,
                    b'"' + b'a' * 16385 + b'"', b' ' * 131073,
                    b'[' + b'0,' * 4096 + b'0]'):
            with self.subTest(raw=raw[:32]), self.assertRaises(HandoffError):
                decode_handoff_json(raw)

    def test_preview_does_not_supply_authority_or_semantic_target(self):
        checked = validate_preview(preview(), REQUEST, INTERPRETATION)
        self.assertFalse(checked["authority"])
        self.assertNotIn("repository", checked)
        for changes in ({"authority": True}, {"source": "online_interpretation"},
                        {"surfaced_unknowns": ["どのPR？"]}, {"clarification_blocked": True},
                        {"candidate_actions": []}, {"request_sha256": "0" * 64},
                        {"interpretation_sha256": "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(HandoffError):
                validate_preview({**preview(), **changes}, REQUEST, INTERPRETATION)


class HandoffOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.worktree = self.root / "tree"
        self.worktree.mkdir()
        self.git("-c", "init.templateDir=", "init", "--initial-branch=canary")
        self.git("remote", "add", "origin", "https://github.com/example/repo.git")
        (self.worktree / "content.txt").write_text("synthetic\n")
        self.git("add", "content.txt")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "-m", "synthetic")
        self.parameters = dict(repository="example/repo", pull_request=7,
                               expected_head_sha=self.git("rev-parse", "HEAD").strip(),
                               expected_base="canary-base", merge_method="merge")
        self.context = copy.deepcopy(CONTEXT)
        self.transport = Transport(self.parameters)
        self.run = self.root / "run"

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.run(["git", "-C", str(self.worktree), *args], env=env,
                              check=True, capture_output=True, text=True, timeout=10).stdout

    def owner(self, **changes):
        values = dict(preview=preview(), raw_request=REQUEST, interpretation=INTERPRETATION,
                      worktree=self.worktree, run_directory=self.run,
                      host_context_provider=lambda: copy.deepcopy(self.context),
                      transport=self.transport, executor_ref=REF)
        values.update(changes)
        return ThinHarnessOwner(self.parameters, **values)

    def approve(self, owner):
        owner.review(response(owner.request))

    def test_real_records_export_and_duplicate_does_not_reexecute(self):
        owner = self.owner()
        self.approve(owner)
        owner.execute(self.parameters)
        bundle = owner.export()
        self.assertEqual("SUCCESS", bundle["receipt"]["status"])
        self.assertEqual(["verification"], bundle["missing"])
        for row in (bundle["consume"], bundle["started"], bundle["finished"]):
            self.assertEqual(owner.request["action"]["action_id"], row["action_id"])
        with self.assertRaises(SessionError):
            owner.execute(self.parameters)
        self.assertEqual(1, len(self.transport.puts))
        outcome = owner.save()
        self.assertFalse(outcome["inspection"]["external_effect_verified"])
        original = json.loads((self.run / "original.json").read_bytes())
        self.assertEqual(inspect_evidence(original), outcome["inspection"])
        self.assertEqual("", self.git("status", "--porcelain"))
        manifest = json.loads((self.run / "manifest.json").read_bytes())
        for name, digest in manifest["artifacts"].items():
            self.assertEqual(digest, hashlib.sha256((self.run / name).read_bytes()).hexdigest())

    def test_wrong_worktree_head_and_run_location_fail_before_authority(self):
        self.parameters["expected_head_sha"] = "a" * 40
        with self.assertRaises(HandoffError):
            self.owner()
        self.assertFalse(self.run.exists())
        self.parameters["expected_head_sha"] = self.git("rev-parse", "HEAD").strip()
        with self.assertRaises(HandoffError):
            self.owner(run_directory=self.worktree / "run")
        self.run.mkdir()
        with self.assertRaises(HandoffError):
            self.owner()
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))

    def test_review_drift_and_empty_scope_fail_without_transport(self):
        owner = self.owner()
        (self.worktree / "content.txt").write_text("changed\n")
        with self.assertRaises(SessionError):
            self.approve(owner)
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))
        (self.worktree / "content.txt").write_text("synthetic\n")
        self.context["scope"] = []
        with self.assertRaises((SessionError, HandoffError)):
            self.owner(run_directory=self.root / "empty-scope")

    def test_drift_after_preflight_keeps_consumed_unknown_without_put(self):
        owner = self.owner()
        self.approve(owner)
        self.transport.on_get = lambda: (self.worktree / "content.txt").write_text("changed\n")
        owner.execute(self.parameters)
        bundle = owner.export()
        self.assertIsNotNone(bundle["consume"])
        self.assertEqual("UNKNOWN", bundle["receipt"]["status"])
        self.assertEqual([], self.transport.puts)

    def test_cancel_and_reject_leave_no_attempt(self):
        owner = self.owner()
        owner.review(response(owner.request, "reject"))
        bundle = owner.export()
        self.assertEqual("reject", bundle["decision"]["decision"])
        self.assertIsNone(bundle["consume"])
        with self.assertRaises(SessionError):
            owner.execute(self.parameters)
        other = self.owner(run_directory=self.root / "canceled")
        other.cancel()
        with self.assertRaises(SessionError):
            self.approve(other)
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))

    def test_timeout_is_not_retried_or_promoted(self):
        owner = self.owner()
        self.approve(owner)
        self.transport.error = TimeoutError("secret exception")
        owner.execute(self.parameters)
        bundle = owner.export()
        self.assertEqual("UNKNOWN", bundle["receipt"]["status"])
        self.assertNotIn("secret exception", json.dumps(bundle))
        self.assertEqual(1, len(self.transport.puts))

    def test_finish_missing_preserves_started_and_no_receipt(self):
        owner = self.owner()
        self.approve(owner)
        with patch("mothership_github.executor.record_attempt_finished", side_effect=OSError("secret")):
            with self.assertRaises(SessionError):
                owner.execute(self.parameters)
        bundle = owner.export()
        self.assertEqual(["finished", "verification"], bundle["missing"])
        self.assertIsNone(bundle["receipt"])
        with self.assertRaises(HandoffError):
            owner.readback(opener=lambda *a, **k: self.fail("incomplete records must not observe"))
        owner.save()
        self.assertEqual(1, len(self.transport.puts))
        self.assertEqual("unknown", json.loads((self.run / "result.json").read_bytes())["diagnostic"]["external_effect"])

    def test_write_then_throw_recovers_only_actual_rows(self):
        from mothership.action_authority import record_action_decision
        owner = self.owner()
        def persist_then_fail(*args, **kwargs):
            record_action_decision(*args, **kwargs)
            raise OSError("secret")
        with patch("mothership_adapters.session.record_action_decision", side_effect=persist_then_fail):
            with self.assertRaises(SessionError):
                self.approve(owner)
        bundle = owner.export()
        self.assertEqual("approve", bundle["decision"]["decision"])
        self.assertIsNone(bundle["consume"])
        self.assertEqual([], self.transport.puts)

    def test_torn_ledger_and_output_failure_keep_originals_without_retry(self):
        owner = self.owner()
        self.approve(owner)
        owner.execute(self.parameters)
        path = self.run / "attempts.jsonl"
        path.write_bytes(path.read_bytes() + b'{"torn":')
        before = path.read_bytes()
        with self.assertRaises(HandoffError):
            owner.save()
        self.assertEqual(before, path.read_bytes())
        self.assertFalse((self.run / "original.json").exists())
        self.assertEqual(1, len(self.transport.puts))

    def test_missing_opener_never_falls_back_to_network(self):
        owner = self.owner()
        self.approve(owner)
        owner.execute(self.parameters)
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            with self.assertRaises(HandoffError):
                owner.readback(opener=None)
        self.assertEqual(["verification"], owner.export()["missing"])

    def test_readback_statuses_and_separate_process_reread_keep_original_bytes(self):
        fixed = datetime.datetime(2026, 10, 23, tzinfo=datetime.UTC)
        for status in ("CONFIRMED", "UNKNOWN", "MISMATCH"):
            with self.subTest(status=status), \
                 patch("orchestration.lib.action_authority._utc_now", return_value=fixed), \
                 patch("orchestration.lib.action_authority_ledger._utc_now", return_value=fixed):
                owner = self.owner(run_directory=self.root / status)
                self.approve(owner)
                start = fixed
                with patch("mothership_github.receipts._utc_now", side_effect=[start, start + datetime.timedelta(seconds=1)]):
                    owner.execute(self.parameters)
                stamp = start + datetime.timedelta(seconds=0 if status == "UNKNOWN" else 5)
                payloads = [dict(
                    url="https://api.github.com/repos/example/repo/pulls/7", number=7,
                    title="synthetic canary", draft=False, updated_at="2026-10-23T00:00:06Z",
                    state="closed", merged=True, merged_at=stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    head={"sha": "a" * 40 if status == "MISMATCH" else self.parameters["expected_head_sha"]},
                    base={"ref": "canary-base", "repo": {"full_name": "example/repo"}},
                    merge_commit_sha="b" * 40),
                    dict(sha="b" * 40, parents=[{"sha": "c" * 40}, {"sha": self.parameters["expected_head_sha"]}])]
                calls = []
                def opener(request, *, timeout):
                    calls.append(request.full_url)
                    body = io.BytesIO(json.dumps(payloads.pop(0)).encode())
                    body.status, body.headers, body.url = 200, {}, request.full_url
                    body.geturl = lambda: body.url
                    return body
                with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")), \
                     patch("mothership_github.verification._utc_now", return_value=start + datetime.timedelta(seconds=10)):
                    observed = owner.readback(opener=opener)
                self.assertEqual(status, observed["bundle"]["verification"]["status"], observed["evidence"])
                self.assertEqual("injected", observed["evidence"]["transport"])
                with self.assertRaises(HandoffError):
                    owner.readback(opener=opener)
                self.assertLessEqual(len(calls), 2)
                outcome = owner.save()
                self.assertEqual(status, outcome["inspection"]["verification_status"])
                self.assertFalse(outcome["inspection"]["external_effect_verified"])
                self.assertIsNone(json.loads((owner.root / "original.json").read_bytes())["verification"])
                before = {p.name: p.read_bytes() for p in owner.root.iterdir() if p.is_file()}
                proc = subprocess.run([
                    __import__("sys").executable, "-B", "-m", "mothership_adapters.cli", "inspect", "--human",
                    "--readback-evidence", str(owner.root / "readback-evidence.json")],
                    input=(owner.root / "verified.json").read_bytes(), capture_output=True, timeout=15)
                self.assertEqual(0, proc.returncode, proc.stderr)
                self.assertIn(("verification: " + status).encode(), proc.stdout)
                self.assertEqual(before, {p.name: p.read_bytes() for p in owner.root.iterdir() if p.is_file()})

    def test_persistence_failure_keeps_ledgers_and_partial_artifact(self):
        owner = self.owner()
        self.approve(owner)
        owner.execute(self.parameters)
        original_rows = (self.run / "attempts.jsonl").read_bytes()
        real_write = os.write
        def short(fd, raw):
            return real_write(fd, raw[:11])
        with patch("mothership_adapters.harness_handoff.os.write", side_effect=short):
            with self.assertRaises(HandoffError):
                owner.save()
        self.assertEqual(original_rows, (self.run / "attempts.jsonl").read_bytes())
        self.assertEqual(11, (self.run / "original.json").stat().st_size)
        with self.assertRaises(HandoffError):
            owner.save()
        self.assertEqual(1, len(self.transport.puts))

    def test_changed_context_parameters_and_expired_request_do_not_reissue(self):
        owner = self.owner()
        self.approve(owner)
        self.context["runtime_generation"] = "changed"
        with self.assertRaises(SessionError):
            owner.execute(self.parameters)
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))
        self.context = copy.deepcopy(CONTEXT)
        other = self.owner(run_directory=self.root / "changed-parameters")
        self.approve(other)
        with self.assertRaises(SessionError):
            other.execute({**self.parameters, "pull_request": 8})
        expired = self.owner(run_directory=self.root / "expired")
        with patch("orchestration.lib.action_authority._utc_now",
                   return_value=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)):
            with self.assertRaises(SessionError):
                self.approve(expired)
        self.assertEqual(([], []), (self.transport.gets, self.transport.puts))

    def test_original_interpretation_bytes_retained_and_copy_restore_rejected(self):
        import pickle
        raw = json.dumps(INTERPRETATION, indent=2, ensure_ascii=False).encode()
        owner = self.owner(interpretation_bytes=raw)
        self.assertEqual(raw, (self.run / "interpretation.json").read_bytes())
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.assertRaises(TypeError):
                operation(owner)

    def test_terminal_requires_exact_request_and_complete_display(self):
        owner = self.owner()
        request = owner.request
        text = "approve " + request["request_id"] + " " + request["request_sha256"] + "\n"
        self.assertEqual(response(request), collect_response(request, Terminal(text), Terminal()))
        with self.assertRaises(HandoffError):
            collect_response(request, Terminal("approve wrong wrong\n"), Terminal())
        class Short(Terminal):
            def write(self, text):
                return len(text) - 1
        input_stream = Terminal(text)
        with self.assertRaises(HandoffError):
            collect_response(request, input_stream, Short())
        self.assertEqual(0, input_stream.tell())
        self.assertFalse((self.run / "authority.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
