"""Real local Git observations; synthetic repositories, no network or credentials."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from mothership_adapters.worktree_observer import GitWorktreeObserver
except ModuleNotFoundError as error:
    if error.name != 'mothership_adapters.worktree_observer':
        raise
    GitWorktreeObserver = None


class WorktreeObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.environment = {
            'PATH': os.environ.get('PATH', os.defpath), 'LC_ALL': 'C',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_CONFIG_SYSTEM': os.devnull, 'GIT_TERMINAL_PROMPT': '0',
        }
        self.git('init', '--initial-branch=topic', '--template=')
        (self.root / 'work.txt').write_bytes(b'original\n')
        self.git('add', 'work.txt')
        self.git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 'commit', '-m', 'fixture')
        self.git('remote', 'add', 'origin', 'https://github.com/example/repo.git')

    def git(self, *arguments, input=None):
        return subprocess.run(
            ['git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
             '-c', 'core.fsmonitor=false', '-C', str(self.root), *arguments],
            env=self.environment, check=True, capture_output=True, timeout=10, input=input,
        ).stdout

    def observer(self, root=None, repository='example/repo'):
        self.assertIsNotNone(GitWorktreeObserver, 'Lease-free observer must be implemented')
        return GitWorktreeObserver(self.root if root is None else root, repository)

    def rejected(self, root=None, repository='example/repo'):
        with self.assertRaises(ValueError) as raised:
            self.observer(root, repository).observe()
        self.assertEqual(str(raised.exception), 'worktree observation unavailable')

    def test_snapshot_has_exact_fields_and_real_identity(self):
        observed = self.observer().observe()
        self.assertEqual(set(observed), {
            'repository', 'worktree_realpath', 'branch', 'head_sha',
            'status_sha256', 'tree_sha256', 'clean',
        })
        self.assertEqual(observed['repository'], 'example/repo')
        self.assertEqual(observed['worktree_realpath'], str(self.root))
        self.assertEqual(observed['branch'], 'topic')
        self.assertEqual(observed['head_sha'], self.git('rev-parse', 'HEAD').decode().strip())
        self.assertEqual(observed['status_sha256'], hashlib.sha256(b'').hexdigest())
        self.assertIs(observed['clean'], True)
        self.assertRegex(observed['tree_sha256'], r'^[0-9a-f]{64}$')

    def test_returns_detached_observation(self):
        observer = self.observer()
        original = observer.observe()
        changed = observer.observe()
        changed['branch'] = 'invented'
        self.assertEqual(observer.observe(), original)

    def test_canonical_https_and_ssh_origins(self):
        for url in ('https://github.com/Example/Repo',
                    'https://github.com/example/repo.git',
                    'git@github.com:example/repo', 'git@github.com:Example/Repo.git'):
            with self.subTest(url=url):
                self.git('remote', 'set-url', 'origin', url)
                self.assertEqual(self.observer().observe()['repository'], 'example/repo')

    def test_rejects_unsafe_or_mismatched_origin_without_disclosing_it(self):
        for url in ('https://secret@github.com/example/repo.git',
                    'https://github.com/example/repo?secret',
                    'https://github.com/example/repo#secret',
                    'https://github.com:443/example/repo',
                    'https://evil.invalid/example/repo',
                    'https://github.com/example/%72epo',
                    'https://github.com/example/re\tpo',
                    'https://github.com/example/../repo',
                    'ssh://git@github.com/example/repo',
                    'other@github.com:example/repo',
                    'git@github.com:other/repo.git'):
            with self.subTest(url=url):
                self.git('remote', 'set-url', 'origin', url)
                self.rejected()

    def test_rejects_multiple_origin_urls_and_local_rewrite(self):
        self.git('config', '--add', 'remote.origin.url', 'https://github.com/example/repo')
        self.rejected()
        self.git('config', '--unset-all', 'remote.origin.url')
        self.git('config', 'remote.origin.url', 'https://github.com/example/repo.git')
        self.git('config', 'url.file:///synthetic/non-github/.insteadOf', 'https://github.com/')
        self.rejected()

    def test_reports_new_head_and_branch_between_calls(self):
        observer = self.observer()
        before = observer.observe()
        self.git('checkout', '-b', 'next')
        self.git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 'commit', '--allow-empty', '-m', 'new head')
        after = observer.observe()
        self.assertEqual(after['branch'], 'next')
        self.assertNotEqual(after['head_sha'], before['head_sha'])
        self.assertIs(after['clean'], True)

    def test_rejects_detached_head_and_nested_path(self):
        self.git('checkout', '--detach')
        self.rejected()
        self.git('checkout', 'topic')
        nested = self.root / 'nested'
        nested.mkdir()
        self.rejected(nested)

    def test_detects_bytes_with_identical_dirty_status(self):
        observer = self.observer()
        (self.root / 'work.txt').write_bytes(b'first\n')
        before = observer.observe()
        (self.root / 'work.txt').write_bytes(b'other\n')
        after = observer.observe()
        self.assertEqual(before['status_sha256'], after['status_sha256'])
        self.assertNotEqual(before['tree_sha256'], after['tree_sha256'])
        self.assertIs(after['clean'], False)

    def test_tracks_modes_and_nonignored_untracked_bytes(self):
        observer = self.observer()
        before = observer.observe()
        (self.root / 'work.txt').chmod(0o755)
        self.assertNotEqual(observer.observe()['tree_sha256'], before['tree_sha256'])
        extra = self.root / 'untracked.txt'
        extra.write_bytes(b'first')
        before = observer.observe()
        extra.write_bytes(b'other')
        after = observer.observe()
        self.assertEqual(before['status_sha256'], after['status_sha256'])
        self.assertNotEqual(before['tree_sha256'], after['tree_sha256'])

    def test_ignored_files_are_explicitly_out_of_scope(self):
        (self.root / '.git/info').mkdir()
        (self.root / '.git/info/exclude').write_text('ignored\n', encoding='utf-8')
        observer = self.observer()
        before = observer.observe()
        (self.root / 'ignored').write_bytes(b'not observed')
        self.assertEqual(observer.observe(), before)

    def test_missing_tracked_regular_file_has_dirty_snapshot(self):
        before = self.observer().observe()
        (self.root / 'work.txt').unlink()
        after = self.observer().observe()
        self.assertIs(after['clean'], False)
        self.assertNotEqual(before['tree_sha256'], after['tree_sha256'])

    def test_rejects_symlink_files_ancestors_and_root(self):
        (self.root / 'link').symlink_to(self.root / 'work.txt')
        self.rejected()
        (self.root / 'link').unlink()
        (self.base / 'alias').symlink_to(self.root, target_is_directory=True)
        self.rejected(self.base / 'alias')
        self.git('update-index', '--add', '--cacheinfo', '100644',
                 self.git('hash-object', 'work.txt').decode().strip(), 'directory/child')
        (self.root / 'directory').symlink_to(self.base, target_is_directory=True)
        self.rejected()

    def test_rejects_staged_symlink_even_when_deleted(self):
        (self.root / 'link').symlink_to('work.txt')
        self.git('add', 'link')
        (self.root / 'link').unlink()
        self.rejected()

    def test_rejects_missing_and_present_gitlinks(self):
        self.git('update-index', '--add', '--cacheinfo', '160000',
                 self.git('rev-parse', 'HEAD').decode().strip(), 'module')
        self.rejected()
        (self.root / 'module').mkdir()
        self.rejected()

    def test_rejects_nonregular_file_without_blocking(self):
        (self.root / 'work.txt').unlink()
        os.mkfifo(self.root / 'work.txt')
        self.rejected()

    def test_rejects_unsafe_filenames(self):
        for name in ('new\nline', 'new\tline', 'back\\slash'):
            with self.subTest(name=name):
                target = self.root / name
                target.write_bytes(b'unsafe')
                self.rejected()
                target.unlink()
        # APFS cannot create this filename; the Git index can still carry it.
        object_id = self.git('hash-object', 'work.txt').strip()
        self.git('update-index', '-z', '--index-info',
                 input=b'100644 ' + object_id + b'\tinvalid-\xff\0')
        self.rejected()

    def test_no_follow_support_is_required(self):
        with patch.object(os, 'O_NOFOLLOW', 0):
            self.rejected()

    def test_small_tree_keeps_original_fingerprint(self):
        (self.root / 'work.txt').chmod(0o644)
        # SHA256 of canonical [[hex('work.txt'), 420, SHA256(b'original\n')]].
        self.assertEqual(self.observer().observe()['tree_sha256'],
                         '5cac21e1aef0b33e1b3875aaaad46c1fd06efc126def11c65f5799009af77f19')

    def test_large_files_and_tree_include_trailing_bytes(self):
        (self.root / 'work.txt').chmod(0o644)
        for number in range(3):
            target = self.root / f'large-{number}.bin'
            target.write_bytes(b'a' * (10 * 1024 * 1024))
            target.chmod(0o644)
        self.git('add', '.')
        self.git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 'commit', '-m', 'large fixture')
        observer = self.observer()
        try:
            before = observer.observe()
        except ValueError:
            self.fail('bounded 30MiB tree with 10MiB regular files must be observed')
        self.assertIs(before['clean'], True)
        # Independently derived canonical entries, including original work.txt.
        self.assertEqual(before['tree_sha256'],
                         '75d00bed2f3211f1ed52ccb954920ba4bb941f76d27e0ff925e894fdfe0c0700')
        target = self.root / 'large-2.bin'
        with target.open('r+b') as stream:
            stream.seek(-1, os.SEEK_END)
            stream.write(b'b')
        dirty = observer.observe()
        with target.open('r+b') as stream:
            stream.seek(-1, os.SEEK_END)
            stream.write(b'c')
        changed = observer.observe()
        self.assertEqual(dirty['status_sha256'], changed['status_sha256'])
        self.assertNotEqual(before['tree_sha256'], dirty['tree_sha256'])
        self.assertNotEqual(dirty['tree_sha256'], changed['tree_sha256'])

    def probe_reads(self, sizes, *, max_piece=None, after_first=None):
        real_fdopen = os.fdopen

        class Reader:
            def __init__(self, stream):
                self.stream, self.first = stream, True

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def read(self, size=-1):
                sizes.append(size)
                data = self.stream.read(size if max_piece is None else min(size, max_piece))
                if self.first and after_first is not None:
                    self.first = False
                    after_first()
                return data

        return patch('mothership_adapters.worktree_observer.os.fdopen',
                     side_effect=lambda *a, **kw: Reader(real_fdopen(*a, **kw)))

    def test_content_reads_have_bounded_chunk_requests(self):
        sizes = []
        with self.probe_reads(sizes):
            observed = self.observer().observe()
        self.assertIs(observed['clean'], True)
        self.assertTrue(sizes)
        self.assertTrue(all(0 < size <= 65536 for size in sizes), sizes)

    def test_short_reads_are_hashed_until_eof(self):
        (self.root / 'work.txt').chmod(0o644)
        with self.probe_reads([], max_piece=3):
            observed = self.observer().observe()
        self.assertEqual(observed['tree_sha256'],
                         '5cac21e1aef0b33e1b3875aaaad46c1fd06efc126def11c65f5799009af77f19')

    def test_growth_and_truncation_during_stream_are_rejected(self):
        target = self.root / 'work.txt'
        for size in (0, 128 * 1024 + 1):
            with self.subTest(size=size):
                target.write_bytes(b'x' * (128 * 1024))
                def mutate():
                    with target.open('r+b') as stream:
                        stream.truncate(size)
                with self.probe_reads([], after_first=mutate):
                    self.rejected()

    def test_per_file_byte_limit(self):
        target = self.root / 'work.txt'
        target.write_bytes(b'x' * 16_777_216)
        self.assertIs(self.observer().observe()['clean'], False)
        with target.open('ab') as stream:
            stream.write(b'x')
        self.rejected()

    def test_total_byte_limit(self):
        (self.root / 'work.txt').write_bytes(b'')
        for number in range(4):
            (self.root / f'file-{number}').write_bytes(b'x' * 16_777_216)
        self.assertIs(self.observer().observe()['clean'], False)
        (self.root / 'work.txt').write_bytes(b'x')
        self.rejected()

    def test_name_limit(self):
        for number in range(1023):
            (self.root / f'file-{number}').touch()
        self.assertIs(self.observer().observe()['clean'], False)
        (self.root / 'too-many').touch()
        self.rejected()

    def test_sanitizes_inherited_git_environment(self):
        index = (self.root / '.git/index').read_bytes()
        trace = self.base / 'trace'
        poison = {
            'GIT_DIR': str(self.base / 'not-a-repository'),
            'GIT_WORK_TREE': str(self.base), 'GIT_INDEX_FILE': str(self.base / 'index'),
            'GIT_COMMON_DIR': str(self.base), 'GIT_TRACE': str(trace),
            'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.bare',
            'GIT_CONFIG_VALUE_0': 'true', 'GIT_CONFIG_PARAMETERS': "'core.bare=true'",
            'GIT_CONFIG_GLOBAL': str(self.base / 'not-config'),
        }
        observer = self.observer()
        expected = observer.observe()
        with patch.dict(os.environ, poison):
            self.assertEqual(observer.observe(), expected)
        self.assertFalse(trace.exists())
        self.assertFalse((self.base / 'index').exists())
        self.assertEqual((self.root / '.git/index').read_bytes(), index)

    def test_caller_path_cannot_select_git_executable(self):
        poison = self.base / 'untrusted-bin'
        poison.mkdir()
        marker = self.base / 'untrusted-git-called'
        executable = poison / 'git'
        # Delegate real observations, but leave evidence if caller PATH selects
        # this program. No network, hook or real operation is involved.
        executable.write_text(
            '#!/bin/sh\nprintf called >> ' + shlex.quote(str(marker)) +
            '\nexec /usr/bin/git "$@"\n', encoding='utf-8')
        executable.chmod(0o755)
        observer = self.observer()
        expected = observer.observe()
        with patch.dict(os.environ, {'PATH': str(poison) + os.pathsep + self.environment['PATH']}):
            self.assertEqual(observer.observe(), expected)
        self.assertFalse(marker.exists(), 'caller-selected git must never execute')

    def test_fsmonitor_is_disabled_and_index_worktree_unchanged(self):
        marker = self.base / 'called'
        monitor = self.base / 'monitor'
        monitor.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding='utf-8')
        monitor.chmod(0o755)
        self.git('config', 'core.fsmonitor', str(monitor))
        index = (self.root / '.git/index').read_bytes()
        content = (self.root / 'work.txt').read_bytes()
        observer = self.observer()
        self.assertEqual(observer.observe(), observer.observe())
        self.assertFalse(marker.exists())
        self.assertEqual((self.root / '.git/index').read_bytes(), index)
        self.assertEqual((self.root / 'work.txt').read_bytes(), content)

    def test_configured_content_filter_is_rejected_before_it_can_execute(self):
        marker = self.base / 'filter-called'
        (self.root / '.gitattributes').write_text('work.txt filter=probe\n', encoding='utf-8')
        self.git('config', 'filter.probe.clean', f'touch "{marker}"; cat')
        # Force status to inspect content instead of relying on the cached stat.
        (self.root / 'work.txt').write_bytes(b'different\n')
        self.rejected()
        self.assertFalse(marker.exists())

    def test_rejects_identity_or_status_change_during_observation(self):
        observer = self.observer()
        real_run = subprocess.run
        self.git('branch', 'alias')
        mutations = (
            lambda: self.git('symbolic-ref', 'HEAD', 'refs/heads/alias'),
            lambda: self.git('remote', 'set-url', 'origin', 'git@github.com:example/repo'),
            lambda: (self.root / 'changed').write_bytes(b'new'),
        )
        for mutate in mutations:
            fired = False

            def changing_run(arguments, **kwargs):
                nonlocal fired
                result = real_run(arguments, **kwargs)
                if 'ls-files' in arguments and not fired:
                    fired = True
                    mutate()
                return result

            with self.subTest(mutation=mutate), patch(
                    'mothership_adapters.worktree_observer.subprocess.run', side_effect=changing_run):
                with self.assertRaises(ValueError):
                    observer.observe()
            self.assertTrue(fired)
            self.git('symbolic-ref', 'HEAD', 'refs/heads/topic')
            self.git('remote', 'set-url', 'origin', 'https://github.com/example/repo.git')
            (self.root / 'changed').unlink(missing_ok=True)

    def test_rejects_same_status_byte_drift_during_observation(self):
        (self.root / 'work.txt').write_bytes(b'first\n')
        observer = self.observer()
        real_tree = observer._tree
        fired = False

        def changing_tree(*arguments):
            nonlocal fired
            result = real_tree(*arguments)
            if not fired:
                fired = True
                (self.root / 'work.txt').write_bytes(b'other\n')
            return result

        with patch.object(observer, '_tree', side_effect=changing_tree):
            with self.assertRaises(ValueError):
                observer.observe()
        self.assertTrue(fired)

    def test_rejects_root_replacement_during_observation(self):
        observer = self.observer()
        real_run = subprocess.run
        fired = False

        def changing_run(arguments, **kwargs):
            nonlocal fired
            result = real_run(arguments, **kwargs)
            if 'ls-files' in arguments and not fired:
                fired = True
                moved = self.base / 'moved'
                self.root.rename(moved)
                self.root.symlink_to(moved, target_is_directory=True)
            return result

        with patch('mothership_adapters.worktree_observer.subprocess.run', side_effect=changing_run):
            with self.assertRaises(ValueError):
                observer.observe()
        self.assertTrue(fired)

    def test_rejects_head_change_during_observation(self):
        observer = self.observer()
        real_run = subprocess.run
        fired = False

        def changing_run(arguments, **kwargs):
            nonlocal fired
            result = real_run(arguments, **kwargs)
            if 'ls-files' in arguments and not fired:
                fired = True
                self.git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                         'commit', '--allow-empty', '-m', 'changed during observation')
            return result

        with patch('mothership_adapters.worktree_observer.subprocess.run', side_effect=changing_run):
            with self.assertRaises(ValueError):
                observer.observe()
        self.assertTrue(fired)

    def test_import_is_independent_of_retired_lease_modules(self):
        source = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('local_execution_lease', 'local_execution_lease_state')):
        raise AssertionError('retired authority import')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from mothership_adapters.worktree_observer import GitWorktreeObserver
assert callable(GitWorktreeObserver.observe)
'''
        result = subprocess.run(
            [sys.executable, '-B', '-c', source],
            env={**self.environment, 'PYTHONPATH': os.environ.get('PYTHONPATH', '')},
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
