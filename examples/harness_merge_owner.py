"""One foreground reference owner: real isolated local work, fake external merge.

Requires an explicitly selected qualified HARNESS runtime on PYTHONPATH. Nothing
is installed, activated on a daily host, retried or restored. The Git observer
covers tracked and nonignored untracked regular files only, with bounded sizes.
It is a best-effort observation, not OS isolation or an atomic effect fence.
"""
from __future__ import annotations

import copy
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tempfile
import uuid

from local_execution_lease import CanonicalTaskReference, PolicyReference, RuntimeContext, derive_lease
from local_execution_lease_state import LeaseStateStore, ObservedExecutionState
from mothership.contracts import canonical_json_bytes, loads_strict
from mothership_adapters.evidence import export_evidence
from mothership_adapters.harness import HarnessMergeBridge


PARAMETERS = {
    'repository': 'example/repo', 'pull_request': 7, 'expected_head_sha': 'a' * 40,
    'expected_base': 'main', 'merge_method': 'merge',
}
EXECUTOR_REF = {
    'ref_id': 'executor:reference-fake',
    'sha256': hashlib.sha256(b'mothership-reference-fake-merge-v0').hexdigest(),
}


def _git(root, *args):
    return subprocess.run(
        ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', str(root), *args],
        check=True, capture_output=True, timeout=10,
    ).stdout


def _read_regular(path, limit):
    # Reference inputs live under one trusted owner-controlled directory. Reject
    # symlink traversal and nonregular objects rather than observing other data.
    if path.resolve() != path:
        raise ValueError('reference path changed')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError('unsupported reference file')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('reference file too large')
        return raw, stat.S_IMODE(metadata.st_mode)
    finally:
        os.close(descriptor)


class GitWorktreeObserver:
    def __init__(self, worktree):
        self.root = Path(worktree).resolve(strict=True)

    def branch(self):
        return _git(self.root, 'symbolic-ref', '--short', 'HEAD').decode().strip()

    def observe(self):
        if Path(os.fsdecode(_git(self.root, 'rev-parse', '--show-toplevel')).strip()).resolve() != self.root:
            raise ValueError('reference worktree root differs')
        head = _git(self.root, 'rev-parse', 'HEAD').decode().strip()
        before = _git(self.root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
        names = sorted(set(_git(self.root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
                           .split(b'\0')) - {b''})
        if len(names) > 1024:
            raise ValueError('reference worktree too large')
        entries = []
        total = 0
        for raw_name in names:
            name = Path(os.fsdecode(raw_name))
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('reference path outside worktree')
            try:
                raw, mode = _read_regular(self.root / name, 1_048_576)
            except FileNotFoundError:
                entries.append([raw_name.hex(), 'missing'])
            else:
                total += len(raw)
                if total > 16_777_216:
                    raise ValueError('reference worktree too large')
                entries.append([raw_name.hex(), mode, hashlib.sha256(raw).hexdigest()])
        after = _git(self.root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
        if before != after or head != _git(self.root, 'rev-parse', 'HEAD').decode().strip():
            raise ValueError('reference worktree changed during observation')
        return ObservedExecutionState(
            starting_head=head, status_digest=hashlib.sha256(before).hexdigest(),
            tree_digest=hashlib.sha256(canonical_json_bytes(entries)).hexdigest(),
        )

    def __call__(self, state):
        if state.worktree_realpath != str(self.root) or state.branch != self.branch():
            raise ValueError('reference worktree identity changed')
        return self.observe()


class FakeMergeTransport:
    """No HTTP/client/credential path; counts are synthetic local invocations."""
    def __init__(self):
        self.gets = []
        self.puts = []
        self.on_get = lambda: None
        self.mutation = {'http_status': 200, 'merged': True, 'merge_commit_sha': 'b' * 40}

    def get_pull_request(self, repository, pull_request):
        self.gets.append((repository, pull_request))
        self.on_get()
        return {'http_status': 200, 'state': 'open', 'merged': False,
                'head_sha': PARAMETERS['expected_head_sha'], 'base_ref': PARAMETERS['expected_base']}

    def merge_pull_request(self, **parameters):
        self.puts.append(parameters)
        if isinstance(self.mutation, Exception):
            raise self.mutation
        return copy.deepcopy(self.mutation)


class HarnessReferenceOwner:
    """Open one existing selected lease and retain one bridge in this process.

    The caller owns the explicit state/ledger paths and independent context
    provider. This owner never derives, issues or activates a local lease.
    """
    def __init__(self, *, worktree, state_path, lease_id, parameters, host_context_provider,
                 authority_path, attempts_path, executor_ref):
        self.observer = GitWorktreeObserver(worktree)
        self.store = LeaseStateStore(state_path, observer=self.observer)
        self.lease_id = lease_id
        self.transport = FakeMergeTransport()
        self.authority_path, self.attempts_path = authority_path, attempts_path
        self.executor_ref = copy.deepcopy(executor_ref)
        self.response = None
        self.result = None
        self.bridge = HarnessMergeBridge(
            parameters, host_context_provider=host_context_provider,
            lease_observer=lambda: self.store.resume(self.lease_id),
            authority_path=authority_path, attempts_path=attempts_path,
            transport=self.transport, executor_ref=self.executor_ref,
        )
        self.request = self.bridge.request

    def review(self, response):
        self.response = copy.deepcopy(response)
        return self.bridge.review(response)

    def execute(self, parameters):
        self.result = self.bridge.execute(parameters)
        return copy.deepcopy(self.result)

    def _rows(self, path):
        try:
            raw, _ = _read_regular(path, 262_144)
        except FileNotFoundError:
            return []
        if raw and not raw.endswith(b'\n'):
            raise ValueError('incomplete reference records')
        return [loads_strict(line) for line in raw.decode('utf-8').splitlines()]

    def export(self):
        if self.result is not None:
            result = self.result
            return export_evidence(
                result['request'], response=result['response'], decision=result['decision'],
                consume=result['consume_event'], started=result['attempt_started'],
                finished=result['attempt_finished'], executor_ref=self.executor_ref,
                verification=result['verification'],
            )
        # An exception does not prove that no write happened. Read only these
        # explicit original paths, never search for records or repair a prefix.
        records = {}
        allowed = {'authority_action_approval': 'decision', 'authority_action_consume': 'consume',
                   'attempt_started': 'started', 'attempt_finished': 'finished'}
        for row in self._rows(self.authority_path) + self._rows(self.attempts_path):
            if type(row) is not dict or row.get('event_type') not in allowed:
                raise ValueError('foreign reference records')
            key = allowed[row['event_type']]
            action = row.get('action') if key == 'decision' else row
            if type(action) is not dict or action.get('action_id') != self.request['action']['action_id']:
                raise ValueError('foreign reference records')
            if key in records:
                raise ValueError('ambiguous reference records')
            records[key] = row
        return export_evidence(self.request, response=self.response,
                               executor_ref=self.executor_ref, **records)


def prepare_local_work(root):
    """Create an explicitly synthetic local task in a fresh isolated Git repo.

    Actual bytes/HEAD/operation transitions are measured; fixture task/policy
    references are declared local-only inputs, never human external approval.
    """
    root = Path(root).resolve(strict=True)
    worktree = root / 'worktree'
    worktree.mkdir(mode=0o700)
    _git(worktree, '-c', 'init.templateDir=', 'init', '--initial-branch=codex/reference')
    (worktree / 'work.txt').write_text('before\n')
    _git(worktree, 'add', 'work.txt')
    _git(worktree, '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Fixture',
         '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'reference baseline')
    observer = GitWorktreeObserver(worktree)
    baseline = observer.observe()
    lease = derive_lease(
        CanonicalTaskReference('reference-local-edit', hashlib.sha256(b'reference-local-edit-v0').hexdigest(),
                               frozenset({'edit', 'test'}), 'unit'),
        PolicyReference('reference-local-policy', hashlib.sha256(b'reference-local-policy-v0').hexdigest(),
                        frozenset({'edit', 'test'}), frozenset({'unit'})),
        RuntimeContext('example/repo', str(worktree), observer.branch(), baseline.starting_head,
                       baseline.status_digest, baseline.tree_digest),
    )
    store = LeaseStateStore(root / 'lease-state.json', observer=observer)
    store.issue(lease)
    store.activate(lease.lease_id)
    operation = store.begin_operation(lease.lease_id)
    (worktree / 'work.txt').write_text('after\n')
    subprocess.run([sys.executable, '-B', '-c',
                    "from pathlib import Path; assert Path('work.txt').read_text() == 'after\\n'"],
                   cwd=worktree, check=True, capture_output=True, timeout=10)
    store.complete_operation(lease.lease_id, operation.operation_id)
    return store, lease


def collect_response(request, input_stream, output_stream):
    """Display the retained request and bind one exact foreground human answer.

    Tests use terminal doubles; those responses are synthetic, not acceptance.
    """
    if not input_stream.isatty() or not output_stream.isatty():
        raise ValueError('a foreground terminal is required')
    text = json.dumps(request, sort_keys=True, indent=2) + '\n'
    text += 'Fake merge only. Type approve/reject, request_id and request_sha256:\n'
    if output_stream.write(text) != len(text):
        raise OSError('request display incomplete')
    output_stream.flush()
    parts = input_stream.readline().strip().split()
    if (len(parts) != 3 or parts[0] not in {'approve', 'reject'}
            or parts[1:] != [request['request_id'], request['request_sha256']]):
        raise ValueError('answer does not match displayed request')
    return {'schema_version': 'authority-action-review-response.v0', 'decision': parts[0],
            'request_id': request['request_id'], 'request_sha256': request['request_sha256'],
            'action_id': request['action']['action_id'], 'action_sha256': request['action_sha256']}


def main():
    # Foreground-only isolated reference. No option opens a daily-host store,
    # restores an owner or replaces the fake transport with a GitHub client.
    temporary = tempfile.TemporaryDirectory(prefix='mothership-harness-reference-', delete=False)
    with temporary as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        cleaned = False
        try:
            _, lease = prepare_local_work(root)
            context = {'host_id': platform.node(), 'session_id': uuid.uuid4().hex,
                       'actor_id': getpass.getuser(), 'runtime_generation': f'{os.getpid()}-{uuid.uuid4().hex}',
                       'scope': ['github.merge_pr']}
            owner = HarnessReferenceOwner(
                worktree=root / 'worktree', state_path=root / 'lease-state.json', lease_id=lease.lease_id,
                parameters=PARAMETERS, host_context_provider=lambda: copy.deepcopy(context),
                authority_path=root / 'authority.jsonl', attempts_path=root / 'attempts.jsonl',
                executor_ref=EXECUTOR_REF,
            )
            exit_code = 0
            try:
                response = collect_response(owner.request, sys.stdin, sys.stderr)
                if owner.review(response) == 'approve':
                    owner.execute(PARAMETERS)
            except (Exception, KeyboardInterrupt):
                exit_code = 2
            # Export actual records once, including after an interrupt. Refused
            # export leaves the original bytes available for read-only diagnosis.
            print(json.dumps(owner.export(), sort_keys=True))
            if exit_code == 0:
                temporary.cleanup()
                cleaned = True
            return exit_code
        except (Exception, KeyboardInterrupt):
            return 2
        finally:
            if not cleaned:
                sys.stderr.write(f'Reference stopped; records retained at {root}; '
                                 'no retry or action reissue.\n')


if __name__ == '__main__':
    raise SystemExit(main())
