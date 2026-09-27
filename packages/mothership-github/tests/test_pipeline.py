"""Offline integration of real Core ledgers and companion attempts with fake I/O."""
import copy
import datetime
import json
import io
import urllib.error
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest import mock

from orchestration.lib.action_authority import freeze_action, ActionAuthorityError
from orchestration.lib.action_authority_ledger import record_action_decision, consume_action, ActionAuthorityLedgerError
from mothership_github.executor import execute_action_merge_pr
from mothership_github import receipts
from mothership_github.external_action import build_external_action_receipt
from mothership_github.verification import verify_merge_pr
from mothership.contracts import ContractError, canonical_json_sha256, validate_receipt_verification_binding
from mothership_github.transport import GitHubRestTransport

PARAMS = dict(repository='owner/repo', pull_request=7, expected_head_sha='a'*40,
              expected_base='main', merge_method='merge')
GOOD = dict(http_status=200, merged=True, merge_commit_sha='b'*40)

class Transport:
    def __init__(self, response=None):
        self.response = copy.deepcopy(GOOD if response is None else response)
        self.puts=[]
        self.on_get=None
    def get_pull_request(self, repository, pull_request):
        if self.on_get: self.on_get()
        return dict(http_status=200,state='open',merged=False,head_sha='a'*40,base_ref='main')
    def merge_pull_request(self, **kwargs):
        self.puts.append(kwargs)
        if isinstance(self.response, Exception): raise self.response
        return copy.deepcopy(self.response)


class ReadBackResponse(io.BytesIO):
    status = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())
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

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='pipeline-')
        self.root=Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.authority=self.root/'authority.jsonl'
        self.attempts=self.root/'attempts.jsonl'
        self.action=freeze_action('act-pipeline', 'github.merge_pr', copy.deepcopy(PARAMS))
        self.approval=record_action_decision(self.authority,self.action,'approve','act-pipeline',self.action.action_sha256)
    def tearDown(self):self.temp.cleanup()
    def execute(self, transport):
        return execute_action_merge_pr(self.authority,self.attempts,self.action,self.approval['event_id'],transport)
    def rows(self,path):
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    def assert_consumed(self):
        with self.assertRaises(ActionAuthorityLedgerError):
            consume_action(self.authority,self.approval['event_id'],'act-pipeline',self.action.action_sha256)
    def test_real_consume_start_put_finish_and_replay(self):
        t=Transport();result=self.execute(t)
        self.assertEqual('success',result['status'])
        auth=self.rows(self.authority); rows=self.rows(self.attempts)
        self.assertEqual(2,len(auth));self.assertEqual(2,len(rows))
        self.assertEqual(auth[1]['event_id'],rows[0]['consume_event_id'])
        self.assertEqual(rows[0]['event_id'],rows[1]['attempt_started_event_id'])
        self.assertEqual(self.action.action_sha256,rows[1]['action_sha256'])
        self.assertEqual([dict(repository='owner/repo',pull_request=7,expected_head_sha='a'*40,merge_method='merge')],t.puts)
        with self.assertRaises(ActionAuthorityLedgerError):self.execute(t)
        self.assertEqual(1,len(t.puts));self.assertEqual(2,len(self.rows(self.attempts)))
    def test_persisted_attempt_round_trip_into_core_preserves_uncertainty(self):
        # Real Core/companion files, fake transport, independently read consume
        # context. A supplied UNKNOWN verification is not an external observer.
        for response, expected in ((GOOD, 'SUCCESS'),
                                   (dict(http_status=409), 'FAILED'),
                                   (dict(http_status=503), 'UNKNOWN')):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                root.chmod(0o700)
                authority, attempts = root/'authority.jsonl', root/'attempts.jsonl'
                action = freeze_action('act-round-trip-' + expected.lower(), 'github.merge_pr', dict(PARAMS))
                action_id = action.action['action_id']
                approval = record_action_decision(authority, action, 'approve', action_id, action.action_sha256)
                transport = Transport(response)
                execute_action_merge_pr(authority, attempts, action, approval['event_id'], transport)
                consume = self.rows(authority)[1]
                start, finish = self.rows(attempts)
                before = (authority.read_bytes(), attempts.read_bytes())
                receipt = build_external_action_receipt(
                    start, finish, expected_action_id=action_id,
                    expected_action_sha256=action.action_sha256,
                    expected_consume_event_id=consume['event_id'],
                    executor_ref={'ref_id': 'executor:offline-pipeline', 'sha256': 'c'*64})
                self.assertEqual(expected, receipt['status'])
                self.assertEqual(canonical_json_sha256({'started': start, 'finished': finish}),
                                 receipt['executor_observation_ref']['sha256'])
                verification = dict(
                    schema_version='external-action-verification.v0', action_id=action_id,
                    action_sha256=action.action_sha256, verification_method='read_only_external_observation',
                    observed_state={'summary': 'Synthetic: no external state observed.', 'state_sha256': None},
                    evidence_refs=[], observed_at=finish['recorded_at'], status='UNKNOWN',
                    receipt_ref={'ref_id': 'receipt:' + action_id, 'sha256': canonical_json_sha256(receipt)})
                bound, verified = validate_receipt_verification_binding(
                    receipt, verification, expected_action_id=action_id,
                    expected_action_sha256=action.action_sha256)
                self.assertEqual(expected, bound['status'])
                self.assertEqual('UNKNOWN', verified['status'])
                with self.assertRaises(ContractError):
                    build_external_action_receipt(
                        start, finish, expected_action_id=action_id,
                        expected_action_sha256=action.action_sha256,
                        expected_consume_event_id=approval['event_id'], executor_ref=receipt['executor_ref'])
                self.assertEqual(before, (authority.read_bytes(), attempts.read_bytes()))
                with self.assertRaises(ActionAuthorityLedgerError):
                    execute_action_merge_pr(authority, attempts, action, approval['event_id'], transport)
                self.assertEqual(1, len(transport.puts))
                self.assertEqual(before, (authority.read_bytes(), attempts.read_bytes()))

    def test_real_pipeline_receipt_readback_is_separate_and_leaves_ledgers_unchanged(self):
        transport = Transport()
        result = self.execute(transport)
        authority_rows = self.rows(self.authority)
        attempt_rows = self.rows(self.attempts)
        consume = authority_rows[1]
        started, finished = attempt_rows
        receipt = build_external_action_receipt(
            started,
            finished,
            expected_action_id=self.action.action["action_id"],
            expected_action_sha256=self.action.action_sha256,
            expected_consume_event_id=consume["event_id"],
            executor_ref={"ref_id": "executor:pipeline", "sha256": "c" * 64},
        )
        before = (self.authority.read_bytes(), self.attempts.read_bytes())
        merged_at = finished["recorded_at"]
        opener = ReadBackOpener(
            [
                {
                    "url": "https://api.github.com/repos/owner/repo/pulls/7",
                    "number": 7,
                    "title": "synthetic",
                    "state": "closed",
                    "merged": True,
                    "merged_at": merged_at,
                    "updated_at": merged_at,
                    "draft": False,
                    "head": {"sha": "a" * 40, "ref": "feature"},
                    "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
                    "merge_commit_sha": "b" * 40,
                },
                {
                    "sha": "b" * 40,
                    "url": "https://api.github.com/repos/owner/repo/git/commits/" + "b" * 40,
                    "parents": [{"sha": "d" * 40}, {"sha": "a" * 40}],
                },
            ]
        )
        finish_dt = datetime.datetime.strptime(finished["recorded_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )
        with mock.patch("mothership_github.verification._utc_now", return_value=finish_dt + datetime.timedelta(seconds=1)):
            bundle = verify_merge_pr(self.action, receipt, opener=opener)
        self.assertEqual("SUCCESS", receipt["status"])
        self.assertEqual("CONFIRMED", bundle["verification"]["status"])
        self.assertEqual(before, (self.authority.read_bytes(), self.attempts.read_bytes()))
        self.assertEqual(2, len(opener.requests))
        self.assertEqual(1, len(transport.puts))

    def test_empty_success_status_stays_unresolved(self):
        t=Transport(dict(http_status=200))
        result=self.execute(t)
        self.assertEqual('reconciliation_required',result['status'])
        self.assert_consumed(); self.assertEqual(1,len(t.puts))
    def test_unknown_exception_text_never_enters_ledger(self):
        t=Transport(RuntimeError('synthetic-secret-must-not-persist'))
        self.assertEqual('reconciliation_required',self.execute(t)['status'])
        self.assertNotIn('synthetic-secret',self.attempts.read_text())
        self.assert_consumed();self.assertEqual(1,len(t.puts))
    def test_unsafe_receipt_path_burns_authority_before_zero_puts(self):
        self.attempts.write_text('');self.attempts.chmod(0o644)
        t=Transport()
        with self.assertRaises(Exception):self.execute(t)
        self.assertEqual([],t.puts);self.assert_consumed()
    def test_finish_fsync_failure_leaves_start_and_consumed_authority(self):
        original=receipts._fsync; calls=0
        def fsync(fd):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('synthetic finish fsync failure')
            return original(fd)
        t=Transport()
        with mock.patch.object(receipts,'_fsync',side_effect=fsync):
            with self.assertRaises(Exception):self.execute(t)
        self.assertEqual(1,len(t.puts));self.assertEqual(1,len(self.rows(self.attempts)));self.assert_consumed()
        start = self.rows(self.attempts)[0]
        with self.assertRaises(ContractError):
            build_external_action_receipt(
                start, None, expected_action_id='act-pipeline',
                expected_action_sha256=self.action.action_sha256,
                expected_consume_event_id=self.rows(self.authority)[1]['event_id'],
                executor_ref={'ref_id': 'executor:offline-pipeline', 'sha256': 'c'*64})
        self.assertEqual(1, len(self.rows(self.attempts)))
    def test_preflight_callback_cannot_replace_frozen_target(self):
        changed=copy.deepcopy(PARAMS);changed['repository']='other/repo'
        def tamper():
            object.__setattr__(self.action,'action',dict(action_id='act-pipeline',operation='github.merge_pr',execution_parameters=changed,display={}))
        t=Transport();t.on_get=tamper
        with self.assertRaises(ActionAuthorityError):self.execute(t)
        self.assertEqual([],t.puts);self.assertEqual(1,len(self.rows(self.authority)))
    def test_parallel_executors_send_exactly_one_put(self):
        barrier=threading.Barrier(2,timeout=5);t=Transport();t.on_get=barrier.wait
        def run():
            try:return self.execute(t)
            except Exception as exc:return exc
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(1,sum(isinstance(x,dict) for x in results))
        self.assertEqual(1,sum(isinstance(x,ActionAuthorityLedgerError) for x in results))
        self.assertEqual(1,len(t.puts));self.assertEqual(2,len(self.rows(self.attempts)))

    def check_rest_unresolved(self, mutation):
        class Response(io.BytesIO):
            status = 200
            headers = {}
        class Opener:
            def __init__(self): self.methods = []
            def open(self, request, timeout):
                self.methods.append(request.get_method())
                if request.get_method() == 'GET':
                    return Response(json.dumps(dict(number=7, state='open', merged=False,
                        head=dict(sha='a'*40), base=dict(ref='main'))).encode())
                raise mutation
        opener = Opener()
        transport = GitHubRestTransport('synthetic-token', opener=opener)
        result = self.execute(transport)
        self.assertEqual('reconciliation_required', result['status'])
        rows = self.rows(self.attempts)
        self.assertEqual(2, len(rows))
        self.assertEqual('reconciliation_required', rows[1]['outcome'])
        self.assertEqual(['GET', 'PUT'], opener.methods)
        self.assert_consumed()
        with self.assertRaises(ActionAuthorityLedgerError): self.execute(transport)
        self.assertEqual(1, opener.methods.count('PUT'))
        return rows[1]['observation']

    def test_rest_timeout_persists_unknown_facts_and_cannot_replay(self):
        observation = self.check_rest_unresolved(TimeoutError())
        self.assertEqual(dict(http_status=0, merged=None, merge_commit_sha=None), observation)

    def test_rest_http_error_contradiction_persists_unresolved_and_cannot_replay(self):
        body = io.BytesIO(json.dumps(dict(merged=True, sha='b'*40)).encode())
        error = urllib.error.HTTPError('https://api.github.com', 409, 'synthetic', {}, body)
        observation = self.check_rest_unresolved(error)
        self.assertEqual(dict(http_status=409, merged=True, merge_commit_sha='b'*40), observation)
        self.assertTrue(body.closed)

if __name__=='__main__':unittest.main()
