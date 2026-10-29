"""Bounded, read-only Git snapshots without any execution authority.

Derived from PR62's reference observer. Tracks regular cached/nonignored untracked
file bytes and modes, excluding ignored files. Repeated checks are best effort,
not an atomic fence or OS isolation. The caller owns baseline/head comparisons.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.parse import urlsplit

from mothership.contracts import canonical_json_sha256


_ERROR = 'worktree observation unavailable'
_MAX_NAMES = 1024
_MAX_FILE = 16_777_216
_MAX_TREE = 67_108_864
_READ_CHUNK = 65_536
_GIT_EXECUTABLE = '/usr/bin/git'
_GIT_PATH = '/usr/bin:/bin'
_COMPONENT = r'[A-Za-z0-9_][A-Za-z0-9_.-]*'
_REPOSITORY = re.compile(rf'{_COMPONENT}/{_COMPONENT}\Z')


def _repository(value):
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise ValueError(_ERROR)
    return value.lower()


def _origin(value):
    # Accept only unambiguous canonical GitHub spellings; never contact origin.
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise ValueError(_ERROR)
    if value.startswith('git@github.com:'):
        path = value[len('git@github.com:'):]
    else:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.netloc != 'github.com'
                or parsed.query or parsed.fragment or '?' in value or '#' in value):
            raise ValueError(_ERROR)
        path = parsed.path.removeprefix('/')
    if path.endswith('.git'):
        path = path[:-4]
    return _repository(path)


def _line(raw):
    if not raw.endswith(b'\n') or b'\n' in raw[:-1] or b'\r' in raw:
        raise ValueError(_ERROR)
    return raw[:-1].decode('utf-8', errors='strict')


def _names(raw):
    if raw and not raw.endswith(b'\0'):
        raise ValueError(_ERROR)
    return raw[:-1].split(b'\0') if raw else []


def _safe_parts(raw):
    name = raw.decode('utf-8', errors='strict')
    parts = name.split('/')
    if (any(part in ('', '.', '..') for part in parts) or '\\' in name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)):
        raise ValueError(_ERROR)
    return parts


class GitWorktreeObserver:
    """Observe current facts; no Lease, ledger, approval, network or mutation API."""

    def __init__(self, worktree, repository):
        try:
            self._root = Path(worktree).absolute()
            self._repository = _repository(repository)
        except Exception:
            raise ValueError(_ERROR) from None

    def _git(self, *arguments):
        # An allowlist avoids inherited alternate Git directories, config
        # injection, tracing, credentials and implicit process-wide overrides.
        # This POSIX candidate trusts the host's system Git. Missing system Git
        # fails closed; never search caller PATH or select a fallback program.
        environment = {
            'PATH': _GIT_PATH, 'LANG': 'C', 'LC_ALL': 'C',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_CONFIG_SYSTEM': os.devnull, 'GIT_OPTIONAL_LOCKS': '0',
            'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_NO_LAZY_FETCH': '1',
            'GIT_TERMINAL_PROMPT': '0',
        }
        result = subprocess.run(
            [_GIT_EXECUTABLE, '--no-optional-locks', '--no-pager',
             '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
             '-c', 'core.untrackedCache=false', '-c', 'submodule.recurse=false',
             '-C', str(self._root), *arguments],
            env=environment, check=True, capture_output=True, timeout=10,
        )
        return result.stdout

    def _open_root(self):
        # Walk from the filesystem anchor with no-follow on EVERY component.
        # Reject platforms lacking these semantics rather than following links.
        for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK'):
            if not getattr(os, flag, 0):
                raise ValueError(_ERROR)
        if os.open not in os.supports_dir_fd:
            raise ValueError(_ERROR)
        if self._root.resolve(strict=True) != self._root:
            raise ValueError(_ERROR)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(self._root.anchor, flags)
        try:
            for part in self._root.parts[1:]:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _identity(self):
        descriptor = self._open_root()
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if _line(self._git('rev-parse', '--show-toplevel')) != str(self._root):
            raise ValueError(_ERROR)
        # Even read-only status may invoke a configured clean/process filter.
        # Such repositories are unsupported; do not execute or silently replace
        # their content-conversion semantics. Global/system config is excluded.
        keys = _names(self._git('config', '--null', '--name-only', '--list'))
        if any(key.lower().startswith(b'filter.') for key in keys):
            raise ValueError(_ERROR)
        origin = _line(self._git('config', '--local', '--no-includes',
                                '--get-all', 'remote.origin.url'))
        resolved_origin = _line(self._git('remote', 'get-url', '--all', 'origin'))
        repository = _origin(origin)
        if repository != self._repository or _origin(resolved_origin) != repository:
            raise ValueError(_ERROR)
        branch = _line(self._git('symbolic-ref', '--quiet', '--short', 'HEAD'))
        head = _line(self._git('rev-parse', '--verify', 'HEAD'))
        if not branch or not re.fullmatch(r'[0-9a-f]{40}', head):
            raise ValueError(_ERROR)
        status = self._git('status', '--porcelain=v1', '-z', '--untracked-files=all',
                           '--ignore-submodules=none')
        return metadata.st_dev, metadata.st_ino, origin, resolved_origin, repository, branch, head, status

    def _tracked_and_untracked(self):
        tracked = self._git('ls-files', '--stage', '-z', '--cached')
        names = set()
        for row in _names(tracked):
            metadata, raw_name = row.split(b'\t', 1)
            mode, object_id, stage = metadata.split(b' ')
            if (mode not in (b'100644', b'100755') or stage != b'0'
                    or not re.fullmatch(b'[0-9a-f]{40}', object_id)):
                raise ValueError(_ERROR)
            names.add(raw_name)
        names.update(_names(self._git('ls-files', '--others', '--exclude-standard', '-z')))
        if len(names) > _MAX_NAMES:
            raise ValueError(_ERROR)
        return sorted(names)

    def _read_regular(self, root_descriptor, raw_name):
        parts = _safe_parts(raw_name)
        descriptor = os.dup(root_descriptor)
        try:
            for part in parts[:-1]:
                next_descriptor = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            file_descriptor = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            try:
                before = os.fstat(file_descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE:
                    raise ValueError(_ERROR)
                digest = hashlib.sha256()
                size = 0
                with os.fdopen(file_descriptor, 'rb', closefd=False) as stream:
                    while True:
                        chunk = stream.read(min(_READ_CHUNK, _MAX_FILE + 1 - size))
                        if type(chunk) is not bytes:
                            raise ValueError(_ERROR)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > _MAX_FILE:
                            raise ValueError(_ERROR)
                        digest.update(chunk)
                after = os.fstat(file_descriptor)
                fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
                if (size != before.st_size or any(
                        getattr(before, field) != getattr(after, field) for field in fields)):
                    raise ValueError(_ERROR)
                return size, stat.S_IMODE(before.st_mode), digest.hexdigest()
            finally:
                os.close(file_descriptor)
        finally:
            os.close(descriptor)

    def _tree(self, root_descriptor, names):
        entries = []
        total = 0
        for raw_name in names:
            try:
                size, mode, digest = self._read_regular(root_descriptor, raw_name)
            except FileNotFoundError:
                entries.append([raw_name.hex(), 'missing'])
            else:
                total += size
                if total > _MAX_TREE:
                    raise ValueError(_ERROR)
                entries.append([raw_name.hex(), mode, digest])
        return canonical_json_sha256(entries)

    def observe(self):
        """Return seven detached scalar facts or a finite, sanitized ValueError."""
        try:
            before = self._identity()
            names = self._tracked_and_untracked()
            descriptor = self._open_root()
            try:
                metadata = os.fstat(descriptor)
                if (metadata.st_dev, metadata.st_ino) != before[:2]:
                    raise ValueError(_ERROR)
                tree = self._tree(descriptor, names)
                # Catch same-status byte drift as well as changes to the index
                # or name list. This is two bounded reads, never a retry.
                if (names != self._tracked_and_untracked()
                        or tree != self._tree(descriptor, names)):
                    raise ValueError(_ERROR)
            finally:
                os.close(descriptor)
            if before != self._identity():
                raise ValueError(_ERROR)
            return {
                'repository': before[4], 'worktree_realpath': str(self._root),
                'branch': before[5], 'head_sha': before[6],
                'status_sha256': hashlib.sha256(before[7]).hexdigest(),
                'tree_sha256': tree, 'clean': not before[7],
            }
        except Exception:
            raise ValueError(_ERROR) from None
