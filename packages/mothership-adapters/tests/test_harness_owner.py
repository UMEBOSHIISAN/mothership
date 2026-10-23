"""Reference-host qualification: real Git/worktree and lease state, fake transport.

All approval responses in this automated suite are synthetic test inputs.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_harness import CONTEXT, PARAMETERS, REF, approval_response
from local_execution_lease_state import LeaseLifecycle
from mothership_adapters.session import SessionError
from mothership.contracts import canonical_json_sha256
from examples.harness_merge_owner import (
    HarnessReferenceOwner, collect_response, prepare_local_work,
)


class HarnessReferenceOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.store, self.lease = prepare_local_work(self.root)
        self.context = copy.deepcopy(CONTEXT)

    def owner(self):
        return HarnessReferenceOwner(
            worktree=self.root / 'worktree', state_path=self.root / 'lease-state.json',
            lease_id=self.lease.lease_id, parameters=PARAMETERS,
            host_context_provider=lambda: copy.deepcopy(self.context),
            authority_path=self.root / 'authority.jsonl', attempts_path=self.root / 'attempts.jsonl',
            executor_ref=REF,
        )

    def rows(self, name):
        path = self.root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def approve(self, owner):
        owner.review(approval_response(owner.request))

    def test_real_local_operation_closes_but_lease_stays_active_before_bridge(self):
        state = self.store.get(self.lease.lease_id)
        self.assertEqual(LeaseLifecycle.ACTIVE, state.lifecycle)
        self.assertIsNone(state.open_operation_id)
        self.assertNotEqual(state.baseline_anchor, state.expected_execution_state)
        owner = self.owner()
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual([], owner.transport.gets)
        self.assertEqual([], owner.transport.puts)
        self.assertEqual([], self.rows('authority.jsonl'))

    def test_same_owner_executes_once_and_exports_actual_mapping_without_verification(self):
        owner = self.owner()
        self.approve(owner)
        result = owner.execute(PARAMETERS)
        bundle = owner.export()
        self.assertEqual('SUCCESS', bundle['receipt']['status'])
        self.assertIsNone(bundle['verification'])
        self.assertEqual(['verification'], bundle['missing'])
        for source, target in (('request', 'request'), ('response', 'response'), ('decision', 'decision'),
                               ('consume_event', 'consume'), ('attempt_started', 'started'),
                               ('attempt_finished', 'finished')):
            self.assertEqual(result[source], bundle[target])
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual(1, len(owner.transport.puts))
        self.assertEqual(['authority_action_approval', 'authority_action_consume'],
                         [row['event_type'] for row in self.rows('authority.jsonl')])

    def test_same_callback_remeasures_bytes_even_when_dirty_status_is_unchanged(self):
        owner = self.owner()
        status = subprocess.check_output(['git', '-C', str(self.root / 'worktree'), 'status', '--porcelain'])
        (self.root / 'worktree' / 'work.txt').write_text('out of band content\n')
        self.assertEqual(status, subprocess.check_output(
            ['git', '-C', str(self.root / 'worktree'), 'status', '--porcelain']))
        with self.assertRaises(SessionError):
            self.approve(owner)
        self.assertEqual(LeaseLifecycle.INVALIDATED, self.store.get(self.lease.lease_id).lifecycle)
        self.assertEqual([], self.rows('authority.jsonl'))
        self.assertEqual([], owner.transport.gets)

    def test_drift_after_review_stops_before_get_and_keeps_approval(self):
        owner = self.owner()
        self.approve(owner)
        (self.root / 'worktree' / 'new.txt').write_text('unexpected')
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual([], owner.transport.gets)
        self.assertEqual(1, len(self.rows('authority.jsonl')))
        self.assertEqual(['consume', 'started', 'finished', 'verification'], owner.export()['missing'])

    def test_changed_lease_source_is_observed_without_replacing_callback(self):
        owner = self.owner()
        self.store.revoke(self.lease.lease_id, 'test revocation')
        with self.assertRaises(SessionError):
            self.approve(owner)
        self.assertEqual([], self.rows('authority.jsonl'))
        self.assertEqual([], owner.transport.gets)

    def test_expiry_after_construction_stops_review_before_decision(self):
        owner = self.owner()
        expires = self.store.get(self.lease.lease_id).expires_at
        with patch('mothership_adapters.harness.time.time', return_value=expires):
            with self.assertRaises(SessionError):
                self.approve(owner)
        self.assertEqual([], self.rows('authority.jsonl'))
        self.assertEqual([], owner.transport.gets)

    def test_cancel_before_review_or_execute_preserves_only_existing_approval(self):
        owner = self.owner()
        owner.bridge.cancel()
        with self.assertRaises(SessionError):
            self.approve(owner)
        self.assertEqual([], self.rows('authority.jsonl'))
        owner = self.owner()
        self.approve(owner)
        owner.bridge.cancel()
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual(1, len(self.rows('authority.jsonl')))
        self.assertEqual([], owner.transport.gets)
        self.assertEqual([], owner.transport.puts)

    def test_context_changes_and_empty_scope_stop_the_retained_owner(self):
        for field in CONTEXT:
            with self.subTest(field=field):
                self.context = copy.deepcopy(CONTEXT)
                owner = self.owner()
                self.context[field] = [] if field == 'scope' else 'changed'
                with self.assertRaises(SessionError):
                    self.approve(owner)
                self.assertEqual([], owner.transport.gets)
        self.assertEqual([], self.rows('authority.jsonl'))

    def test_cancel_during_get_keeps_one_consume_zero_put_unknown_and_no_replay(self):
        owner = self.owner()
        self.approve(owner)
        owner.transport.on_get = owner.bridge.cancel
        result = owner.execute(PARAMETERS)
        self.assertEqual('UNKNOWN', result['receipt']['status'])
        self.assertEqual('UNKNOWN', owner.export()['receipt']['status'])
        self.assertEqual(2, len(self.rows('authority.jsonl')))
        self.assertEqual([], owner.transport.puts)
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual(1, len(owner.transport.gets))

    def test_suspend_resume_rechecks_actual_worktree(self):
        owner = self.owner()
        owner.bridge.suspend()
        with self.assertRaises(SessionError):
            self.approve(owner)
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        (self.root / 'worktree' / 'work.txt').write_text('drift while suspended')
        with self.assertRaises(SessionError):
            owner.bridge.resume()
        self.assertEqual('suspended', owner.bridge.state)
        self.assertEqual([], self.rows('authority.jsonl'))

    def test_foreign_request_or_digest_response_cannot_record_approval(self):
        for key in ('request_id', 'request_sha256', 'action_sha256'):
            with self.subTest(key=key):
                owner = self.owner()
                response = approval_response(owner.request)
                response[key] = 'f' * 64
                with self.assertRaises(SessionError):
                    owner.review(response)
        self.assertEqual([], self.rows('authority.jsonl'))

    def test_different_parameters_do_not_reach_transport(self):
        owner = self.owner()
        self.approve(owner)
        with self.assertRaises(SessionError):
            owner.execute({**PARAMETERS, 'pull_request': 8})
        self.assertEqual([], owner.transport.gets)
        self.assertEqual(1, len(self.rows('authority.jsonl')))

    def test_timeout_exports_unknown_without_second_mutation(self):
        owner = self.owner()
        self.approve(owner)
        owner.transport.mutation = TimeoutError('test timeout')
        owner.execute(PARAMETERS)
        self.assertEqual('UNKNOWN', owner.export()['receipt']['status'])
        self.assertIsNone(owner.export()['verification'])
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual(1, len(owner.transport.puts))

    def test_missing_finish_exports_only_persisted_rows_without_receipt(self):
        owner = self.owner()
        self.approve(owner)
        with patch('mothership_github.executor.record_attempt_finished', side_effect=OSError('fixture')):
            with self.assertRaises(SessionError):
                owner.execute(PARAMETERS)
        bundle = owner.export()
        self.assertEqual(['finished', 'verification'], bundle['missing'])
        self.assertIsNone(bundle['receipt'])
        self.assertIsNotNone(bundle['started'])
        with self.assertRaises(SessionError):
            owner.execute(PARAMETERS)
        self.assertEqual(1, len(owner.transport.puts))
        self.assertEqual(1, len(self.rows('attempts.jsonl')))

    def test_unknown_verification_stays_unknown_beside_success_receipt(self):
        owner = self.owner()
        self.approve(owner)
        result = owner.execute(PARAMETERS)
        owner.result['verification'] = {
            'schema_version': 'external-action-verification.v0',
            'action_id': result['request']['action']['action_id'],
            'action_sha256': result['request']['action_sha256'],
            'verification_method': 'read_only_external_observation',
            'observed_state': {'summary': 'synthetic unknown', 'state_sha256': 'd' * 64},
            'evidence_refs': [{'ref_id': 'observation:synthetic', 'sha256': 'e' * 64}],
            'observed_at': result['attempt_finished']['recorded_at'], 'status': 'UNKNOWN',
            'receipt_ref': {'ref_id': 'receipt:' + result['request']['action']['action_id'],
                            'sha256': canonical_json_sha256(result['receipt'])},
        }
        bundle = owner.export()
        self.assertEqual('SUCCESS', bundle['receipt']['status'])
        self.assertEqual('UNKNOWN', bundle['verification']['status'])

    def test_torn_or_foreign_retained_records_are_rejected_without_repair(self):
        owner = self.owner()
        self.approve(owner)
        path = self.root / 'authority.jsonl'
        raw = path.read_bytes()
        path.write_bytes(raw[:-1])
        with self.assertRaises(ValueError):
            owner.export()
        self.assertEqual(raw[:-1], path.read_bytes())
        row = json.loads(raw)
        row['action']['action_id'] = 'act-foreign'
        path.write_text(json.dumps(row) + '\n')
        with self.assertRaises(ValueError):
            owner.export()
        self.assertEqual([], owner.transport.puts)

    def test_lost_process_owner_cannot_resume_or_reissue(self):
        owner = self.owner()
        with patch('os.getpid', return_value=-1):
            with self.assertRaises(SessionError):
                self.approve(owner)
        self.assertEqual([], self.rows('authority.jsonl'))
        self.assertEqual([], owner.transport.gets)

    def test_real_head_or_branch_change_and_unsupported_files_are_rejected(self):
        for change in ('branch', 'head', 'symlink'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                store, lease = prepare_local_work(root)
                owner = HarnessReferenceOwner(
                    worktree=root / 'worktree', state_path=root / 'lease-state.json', lease_id=lease.lease_id,
                    parameters=PARAMETERS, host_context_provider=lambda: CONTEXT,
                    authority_path=root / 'authority.jsonl', attempts_path=root / 'attempts.jsonl', executor_ref=REF,
                )
                if change == 'branch':
                    subprocess.run(['git', '-C', str(root / 'worktree'), 'switch', '-c', 'changed'],
                                   check=True, capture_output=True)
                elif change == 'head':
                    subprocess.run(['git', '-C', str(root / 'worktree'), '-c', 'user.name=Fixture',
                                    '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-m', 'drift'],
                                   check=True, capture_output=True)
                else:
                    (root / 'worktree' / 'link').symlink_to(root / 'worktree' / 'work.txt')
                with self.assertRaises(SessionError):
                    self.approve(owner)
                self.assertEqual([], owner.transport.gets)

    def test_human_input_path_binds_the_displayed_request_and_refuses_nonterminal_input(self):
        owner = self.owner()
        request = owner.request
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        output = Terminal()
        response = collect_response(request, Terminal(
            f"approve {request['request_id']} {request['request_sha256']}\n"), output)
        self.assertEqual(approval_response(request), response)
        self.assertIn(request['request_sha256'], output.getvalue())
        with self.assertRaises(ValueError):
            collect_response(request, Terminal('approve stale-request stale-digest\n'), Terminal())
        with self.assertRaises(ValueError):
            collect_response(request, io.StringIO('approve\n'), Terminal())
        self.assertEqual([], self.rows('authority.jsonl'))
