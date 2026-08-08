"""Descriptor-relative, bounded task input and output handling."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO


_MAX_FILES = 32
_MAX_BYTES = 1_048_576
_CHUNK = 65_536
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_SENSITIVE_NAME = re.compile(
    r"(^\.env(?:\.|$)|^(?:id_rsa|id_dsa|id_ecdsa|id_ed25519)$|"
    r"\.(?:pem|key|p12|pfx)$|(?:auth|credential|token|secret))",
    re.I,
)
_FIXED_SENSITIVE_CONTENT = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bbearer\s+[^\s]",
    re.I,
)
_COMPONENT_SWAP_HOOK = None
_STAGE_VERIFY_HOOK = None


@dataclass(frozen=True)
class ScopeFile:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class PreparedScope:
    task_root: Path
    run_root: Path
    prompt_path: Path
    prompt_sha256: str
    files: tuple[ScopeFile, ...]
    scope_sha256: str
    staged_root: Path | None


@dataclass(frozen=True)
class _OwnedDirectory:
    parts: tuple[str, ...]
    identity: tuple[int, int]


@dataclass(frozen=True)
class _OwnedStageEntry:
    parts: tuple[str, ...]
    kind: str
    identity: tuple[int, int]


def validate_relative_path(value: str) -> PurePosixPath:
    if (
        type(value) is not str
        or not value
        or value == "."
        or "\\" in value
        or "\x00" in value
        or value.startswith("/")
        or value.endswith("/")
        or "//" in value
    ):
        raise ValueError("path must be a nonempty normalized POSIX-relative path")
    result = PurePosixPath(value)
    if str(result) != value or any(part in ("", ".", "..") for part in result.parts):
        raise ValueError("path must be a nonempty normalized POSIX-relative path")
    return result


def _close(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _directory(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("unsafe directory")
    return info


def _regular_descriptor(fd: int) -> os.stat_result:
    """Return descriptor metadata only for an actual regular file."""

    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("descriptor must be regular")
    return info


def _open_dir(name: str, parent_fd: int | None = None) -> int:
    if _COMPONENT_SWAP_HOOK is not None:
        _COMPONENT_SWAP_HOOK(name)
    fd: int | None = None
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW,
            dir_fd=parent_fd,
        )
        _directory(fd)
        return fd
    except (OSError, ValueError):
        _close(fd)
        raise ValueError("unsafe directory") from None


def _root(value: Path) -> tuple[Path, int, tuple[int, int]]:
    try:
        text = os.fspath(value)
    except TypeError:
        raise ValueError("root must be an absolute normalized real directory") from None
    if type(text) is not str or not os.path.isabs(text) or os.path.normpath(text) != text:
        raise ValueError("root must be an absolute normalized real directory")
    fd: int | None = None
    try:
        fd = _open_dir("/")
        for component in PurePosixPath(text).parts[1:]:
            child = _open_dir(component, fd)
            _close(fd)
            fd = child
        info = _directory(fd)
        return Path(text), fd, _identity(info)
    except ValueError:
        _close(fd)
        raise ValueError("root must be an absolute normalized real directory") from None


def _nested(first: Path, second: Path) -> bool:
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def _separate(
    left: Path,
    left_node: tuple[int, int],
    right: Path,
    right_node: tuple[int, int],
) -> None:
    if left_node == right_node or _nested(left, right) or _nested(right, left):
        raise ValueError("task and run roots must not overlap")


def _open_parent(
    root_fd: int,
    rel: PurePosixPath,
    create: bool = False,
    created: list[_OwnedDirectory] | None = None,
) -> tuple[int, str]:
    fd = os.dup(root_fd)
    _directory(fd)
    parts: list[str] = []
    ledger = created if created is not None else []
    try:
        for component in rel.parts[:-1]:
            parts.append(component)
            try:
                child = _open_dir(component, fd)
            except ValueError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                    created_info = os.stat(component, dir_fd=fd, follow_symlinks=False)
                    if not stat.S_ISDIR(created_info.st_mode):
                        raise ValueError("unsafe path component")
                    owned = _OwnedDirectory(tuple(parts), _identity(created_info))
                    ledger.append(owned)
                    child = _open_dir(component, fd)
                    if _identity(_directory(child)) != owned.identity:
                        _close(child)
                        raise ValueError("path component changed during traversal")
                    os.fchmod(child, 0o700)
                except OSError:
                    raise ValueError("unsafe path component") from None
            _close(fd)
            fd = child
        return fd, rel.parts[-1]
    except BaseException:
        _close(fd)
        raise


def _open_stage_parent(
    root_fd: int,
    rel: PurePosixPath,
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
) -> tuple[int, str]:
    fd = os.dup(root_fd)
    _directory(fd)
    parts: list[str] = []
    try:
        for component in rel.parts[:-1]:
            parts.append(component)
            path = tuple(parts)
            expected = ledger.get(path)
            try:
                before = os.stat(component, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                if expected is not None:
                    raise ValueError("owned stage directory is missing") from None
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                except OSError:
                    raise ValueError("unsafe stage path component") from None
                child = _open_dir(component, fd)
                child_info = _directory(child)
                owned = _OwnedStageEntry(path, "directory", _identity(child_info))
                ledger[path] = owned
                try:
                    os.fchmod(child, 0o700)
                except BaseException:
                    _close(child)
                    raise
            except OSError:
                raise ValueError("unsafe stage path component") from None
            else:
                if (
                    expected is None
                    or expected.kind != "directory"
                    or not stat.S_ISDIR(before.st_mode)
                    or _identity(before) != expected.identity
                ):
                    raise ValueError("unsafe stage path component")
                child = _open_dir(component, fd)
                if _identity(_directory(child)) != expected.identity:
                    _close(child)
                    raise ValueError("owned stage directory changed")
            _close(fd)
            fd = child
        return fd, rel.parts[-1]
    except BaseException:
        _close(fd)
        raise


def _open_regular(
    root_fd: int,
    relative: str,
) -> tuple[int, os.stat_result, PurePosixPath]:
    rel = validate_relative_path(relative)
    if _SENSITIVE_NAME.search(rel.name):
        raise ValueError("sensitive input filename")
    parent_fd, leaf = _open_parent(root_fd, rel)
    fd: int | None = None
    try:
        if _COMPONENT_SWAP_HOOK is not None:
            _COMPONENT_SWAP_HOOK(leaf)
        fd = os.open(
            leaf,
            os.O_RDONLY | _NONBLOCK | _NOFOLLOW,
            dir_fd=parent_fd,
        )
        info = _regular_descriptor(fd)
        return fd, info, rel
    except (OSError, ValueError):
        _close(fd)
        raise ValueError("unsafe input leaf") from None
    finally:
        _close(parent_fd)


class _SensitiveScanner:
    """Constant-space scanner for fixed markers and assignment names."""

    def __init__(self) -> None:
        self._fixed_tail = b""
        self._identifier_tail = bytearray()
        self._awaiting_delimiter = False
        self._sensitive_identifier = False

    @staticmethod
    def _is_identifier(byte: int) -> bool:
        return (
            ord("a") <= byte <= ord("z")
            or ord("A") <= byte <= ord("Z")
            or ord("0") <= byte <= ord("9")
            or byte in (ord("_"), ord("-"))
        )

    @staticmethod
    def _assignment_name_is_sensitive(raw: bytes) -> bool:
        name = raw.lower().replace(b"-", b"_")
        return (
            name in {b"token", b"secret", b"access_token", b"secret_access_key"}
            or name.endswith(b"_token")
            or name.endswith(b"_secret")
            or name.endswith(b"_api_key")
            or name.endswith(b"_provider_key")
            or (b"provider" in name and name.endswith(b"_key"))
        )

    def feed(self, block: bytes) -> bool:
        fixed = self._fixed_tail + block
        if _FIXED_SENSITIVE_CONTENT.search(fixed) is not None:
            return True
        self._fixed_tail = fixed[-256:]

        for byte in block:
            if self._awaiting_delimiter:
                if byte in (ord(" "), ord("\t"), ord("\r"), ord("\n")):
                    continue
                if byte in (ord(":"), ord("=")) and self._sensitive_identifier:
                    return True
                self._awaiting_delimiter = False
                self._sensitive_identifier = False
                self._identifier_tail.clear()

            if self._is_identifier(byte):
                self._identifier_tail.append(byte)
                if len(self._identifier_tail) > 128:
                    del self._identifier_tail[:-128]
                continue

            if self._identifier_tail:
                sensitive = self._assignment_name_is_sensitive(bytes(self._identifier_tail))
                self._identifier_tail.clear()
                if byte in (ord(":"), ord("=")) and sensitive:
                    return True
                if byte in (ord(" "), ord("\t"), ord("\r"), ord("\n")):
                    self._awaiting_delimiter = True
                    self._sensitive_identifier = sensitive
        return False


def _measure(
    root_fd: int,
    relative: str,
    byte_limit: int | None = None,
) -> tuple[ScopeFile, tuple[int, int]]:
    fd, info, rel = _open_regular(root_fd, relative)
    try:
        digest = hashlib.sha256()
        total = 0
        scanner = _SensitiveScanner()
        while True:
            if byte_limit is None:
                amount = _CHUNK
            else:
                amount = min(_CHUNK, max(0, byte_limit - total) + 1)
            chunk = os.read(fd, amount)
            if not chunk:
                break
            if byte_limit is not None and len(chunk) > byte_limit - total:
                raise ValueError("scope byte limit exceeded")
            if scanner.feed(chunk):
                raise ValueError("sensitive input content")
            digest.update(chunk)
            total += len(chunk)
        return ScopeFile(str(rel), total, digest.hexdigest()), _identity(info)
    finally:
        _close(fd)


def _scope_fields(task: dict[str, object]) -> tuple[str, list[str], int, int]:
    if type(task) is not dict:
        raise ValueError("invalid scope task")
    prompt = task.get("prompt_path", task.get("prompt_file"))
    files = task.get(
        "context_paths",
        task.get("context_files", task.get("scope_paths", [])),
    )
    maximum_files = task.get(
        "max_context_files",
        task.get("maximum_context_files", _MAX_FILES),
    )
    maximum_bytes = task.get(
        "max_context_bytes",
        task.get("maximum_context_bytes", _MAX_BYTES),
    )
    if (
        type(prompt) is not str
        or type(files) is not list
        or not all(type(item) is str for item in files)
        or type(maximum_files) is not int
        or type(maximum_bytes) is not int
        or maximum_files < 0
        or maximum_bytes < 0
    ):
        raise ValueError("invalid scope task")
    return prompt, files, min(maximum_files, _MAX_FILES), min(maximum_bytes, _MAX_BYTES)


def _existing_regular_nodes(root_fd: int) -> set[tuple[int, int]]:
    found: set[tuple[int, int]] = set()

    def walk(fd: int) -> None:
        _directory(fd)
        with os.scandir(fd) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError("unsafe existing output link")
                if stat.S_ISREG(info.st_mode):
                    found.add(_identity(info))
                elif stat.S_ISDIR(info.st_mode):
                    child = _open_dir(entry.name, fd)
                    try:
                        if _identity(_directory(child)) != _identity(info):
                            raise ValueError("output directory changed during traversal")
                        walk(child)
                    finally:
                        _close(child)

    copy = os.dup(root_fd)
    try:
        walk(copy)
    finally:
        _close(copy)
    return found


def _copy_input(
    source_root_fd: int,
    relative: str,
    stage_fd: int,
    expected: ScopeFile,
    expected_node: tuple[int, int],
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
) -> None:
    rel = validate_relative_path(relative)
    parent_fd, leaf = _open_stage_parent(stage_fd, rel, ledger)
    source_fd: int | None = None
    output_fd: int | None = None
    created_node: tuple[int, int] | None = None
    try:
        source_fd, source_info, _ = _open_regular(source_root_fd, relative)
        if _identity(source_info) != expected_node:
            raise ValueError("input changed after measurement")
        if _COMPONENT_SWAP_HOOK is not None:
            _COMPONENT_SWAP_HOOK(leaf)
        output_fd = os.open(
            leaf,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        output_info = _regular_descriptor(output_fd)
        created_node = _identity(output_info)
        if _identity(output_info) == expected_node:
            raise ValueError("staged output aliases input")

        digest = hashlib.sha256()
        total = 0
        remaining = expected.size
        while remaining:
            chunk = os.read(source_fd, min(_CHUNK, remaining))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            remaining -= len(chunk)
            offset = 0
            while offset < len(chunk):
                written = os.write(output_fd, chunk[offset:])
                if written <= 0:
                    raise OSError("short output write")
                offset += written
        sentinel = os.read(source_fd, 1)
        if sentinel:
            raise ValueError("input grew after measurement")

        os.fsync(output_fd)
        output_info = _regular_descriptor(output_fd)
        if (
            total != expected.size
            or output_info.st_size != expected.size
            or digest.hexdigest() != expected.sha256
            or _identity(output_info) == expected_node
        ):
            raise ValueError("staged copy verification failed")
        os.fchmod(output_fd, 0o444)
        final_info = _regular_descriptor(output_fd)
        if (
            _identity(final_info) != created_node
            or stat.S_IMODE(final_info.st_mode) != 0o444
        ):
            raise ValueError("staged copy changed before ownership commit")
        ledger[tuple(rel.parts)] = _OwnedStageEntry(
            tuple(rel.parts),
            "file",
            _identity(final_info),
        )
    except BaseException:
        try:
            _close(output_fd)
        except BaseException:
            pass
        output_fd = None
        if created_node is not None and tuple(rel.parts) not in ledger:
            try:
                _unlink_owned_leaf(parent_fd, leaf, created_node)
            except BaseException:
                pass
        try:
            _close(source_fd)
        except BaseException:
            pass
        source_fd = None
        try:
            _close(parent_fd)
        except BaseException:
            pass
        parent_fd = None
        raise
    finally:
        _close(output_fd)
        _close(source_fd)
        _close(parent_fd)


def _open_owned_stage_directory(
    root_fd: int,
    parts: tuple[str, ...],
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
) -> int:
    fd = os.dup(root_fd)
    _directory(fd)
    traversed: list[str] = []
    try:
        for component in parts:
            traversed.append(component)
            expected = ledger.get(tuple(traversed))
            before = os.stat(component, dir_fd=fd, follow_symlinks=False)
            if (
                expected is None
                or expected.kind != "directory"
                or not stat.S_ISDIR(before.st_mode)
                or _identity(before) != expected.identity
            ):
                raise ValueError("owned stage directory changed")
            child = _open_dir(component, fd)
            try:
                if _identity(_directory(child)) != expected.identity:
                    raise ValueError("owned stage directory changed")
                os.fchmod(child, 0o700)
            except BaseException:
                _close(child)
                raise
            _close(fd)
            fd = child
        return fd
    except BaseException:
        _close(fd)
        raise


def _remove_owned_stage_entry(
    root_fd: int,
    entry: _OwnedStageEntry,
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
) -> None:
    parent_fd: int | None = None
    opened_fd: int | None = None
    try:
        parent_fd = _open_owned_stage_directory(root_fd, entry.parts[:-1], ledger)
        name = entry.parts[-1]
        try:
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(before.st_mode):
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(current.st_mode):
                os.unlink(name, dir_fd=parent_fd)
            return
        if entry.kind == "file":
            if not stat.S_ISREG(before.st_mode) or _identity(before) != entry.identity:
                return
            opened_fd = os.open(
                name,
                os.O_RDONLY | _NONBLOCK | _NOFOLLOW,
                dir_fd=parent_fd,
            )
            opened = _regular_descriptor(opened_fd)
            if _identity(opened) != entry.identity:
                return
            _close(opened_fd)
            opened_fd = None
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISREG(current.st_mode) and _identity(current) == entry.identity:
                os.unlink(name, dir_fd=parent_fd)
            return
        if (
            entry.kind != "directory"
            or not stat.S_ISDIR(before.st_mode)
            or _identity(before) != entry.identity
        ):
            return
        opened_fd = _open_dir(name, parent_fd)
        if _identity(_directory(opened_fd)) != entry.identity:
            return
        os.fchmod(opened_fd, 0o700)
        _close(opened_fd)
        opened_fd = None
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISDIR(current.st_mode) and _identity(current) == entry.identity:
            os.rmdir(name, dir_fd=parent_fd)
    finally:
        _close(opened_fd)
        _close(parent_fd)


def _cleanup_stage(
    parent_fd: int,
    name: str,
    expected_node: tuple[int, int],
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
) -> None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(current.st_mode):
            os.unlink(name, dir_fd=parent_fd)
        return
    if not stat.S_ISDIR(info.st_mode) or _identity(info) != expected_node:
        return
    fd = _open_dir(name, parent_fd)
    try:
        if _identity(_directory(fd)) != expected_node:
            return
        os.fchmod(fd, 0o700)
        ordered = sorted(
            ledger.values(),
            key=lambda entry: (len(entry.parts), entry.kind == "file"),
            reverse=True,
        )
        for entry in ordered:
            try:
                _remove_owned_stage_entry(fd, entry, ledger)
            except BaseException:
                pass
    finally:
        _close(fd)
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISDIR(current.st_mode) and _identity(current) == expected_node:
        os.rmdir(name, dir_fd=parent_fd)


def _verify_stage(
    fd: int,
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
    prefix: tuple[str, ...] = (),
) -> None:
    _directory(fd)
    expected_names = {
        parts[-1]
        for parts in ledger
        if len(parts) == len(prefix) + 1 and parts[:-1] == prefix
    }
    observed_names: set[str] = set()
    with os.scandir(fd) as observations:
        for observation in observations:
            name = observation.name
            observed_names.add(name)
            parts = prefix + (name,)
            expected = ledger.get(parts)
            if expected is None:
                raise ValueError("unexpected staged entry")
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if expected.kind == "directory":
                if not stat.S_ISDIR(info.st_mode) or _identity(info) != expected.identity:
                    raise ValueError("owned staged directory changed")
                child = _open_dir(name, fd)
                try:
                    if _identity(_directory(child)) != expected.identity:
                        raise ValueError("owned staged directory changed")
                    _verify_stage(child, ledger, parts)
                finally:
                    _close(child)
            elif expected.kind == "file":
                if not stat.S_ISREG(info.st_mode) or _identity(info) != expected.identity:
                    raise ValueError("owned staged file changed")
                file_fd: int | None = None
                try:
                    file_fd = os.open(
                        name,
                        os.O_RDONLY | _NONBLOCK | _NOFOLLOW,
                        dir_fd=fd,
                    )
                    if _identity(_regular_descriptor(file_fd)) != expected.identity:
                        raise ValueError("owned staged file changed")
                except OSError:
                    raise ValueError("unsafe staged file") from None
                finally:
                    _close(file_fd)
            else:
                raise ValueError("invalid stage ownership row")
    if observed_names != expected_names:
        raise ValueError("staged entry is missing")


def _lock_stage(
    fd: int,
    ledger: dict[tuple[str, ...], _OwnedStageEntry],
    prefix: tuple[str, ...] = (),
) -> None:
    _directory(fd)
    directories = sorted(
        (
            entry
            for entry in ledger.values()
            if entry.kind == "directory"
            and len(entry.parts) == len(prefix) + 1
            and entry.parts[:-1] == prefix
        ),
        key=lambda entry: entry.parts[-1].encode("utf-8"),
    )
    for entry in directories:
        name = entry.parts[-1]
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode) or _identity(before) != entry.identity:
            raise ValueError("owned staged directory changed before lock")
        child = _open_dir(name, fd)
        try:
            if _identity(_directory(child)) != entry.identity:
                raise ValueError("owned staged directory changed before lock")
            _lock_stage(child, ledger, entry.parts)
        finally:
            _close(child)
    os.fchmod(fd, 0o555)


def prepare_scope(
    task: dict[str, object],
    task_root: Path,
    run_root: Path,
    create_stage: bool,
) -> PreparedScope:
    task_fd: int | None = None
    run_fd: int | None = None
    try:
        task_path, task_fd, task_node = _root(task_root)
        run_path, run_fd, run_node = _root(run_root)
        _separate(task_path, task_node, run_path, run_node)
        prompt_rel, contexts, file_limit, byte_limit = _scope_fields(task)
        if len(contexts) > file_limit:
            raise ValueError("scope file limit exceeded")

        prompt, prompt_node = _measure(task_fd, prompt_rel)
        identities = {prompt_node}
        measured: list[tuple[ScopeFile, tuple[int, int]]] = []
        remaining = byte_limit
        for relative in contexts:
            item, node = _measure(task_fd, relative, remaining)
            if node in identities:
                raise ValueError("input aliases another input")
            identities.add(node)
            remaining -= item.size
            measured.append((item, node))
        if identities & _existing_regular_nodes(run_fd):
            raise ValueError("input aliases an existing output")

        measured.sort(key=lambda pair: pair[0].relative_path.encode("utf-8"))
        files = tuple(item for item, _ in measured)
        rows = b"".join(
            f"{item.relative_path}\t{item.size}\t{item.sha256}\n".encode("utf-8")
            for item in files
        )
        staged: Path | None = None
        if create_stage:
            try:
                os.stat("staged-context", dir_fd=run_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("stage already exists")

            os.mkdir("staged-context", 0o700, dir_fd=run_fd)
            stage_info = os.stat("staged-context", dir_fd=run_fd, follow_symlinks=False)
            stage_node = _identity(stage_info)
            stage_fd: int | None = None
            stage_ledger: dict[tuple[str, ...], _OwnedStageEntry] = {}
            try:
                stage_fd = _open_dir("staged-context", run_fd)
                opened_stage = _directory(stage_fd)
                if _identity(opened_stage) != stage_node:
                    raise ValueError("stage changed during creation")
                stage_node = _identity(opened_stage)
                os.fchmod(stage_fd, 0o700)
                for item, node in measured:
                    _copy_input(
                        task_fd,
                        item.relative_path,
                        stage_fd,
                        item,
                        node,
                        stage_ledger,
                    )
                if _STAGE_VERIFY_HOOK is not None:
                    _STAGE_VERIFY_HOOK()
                current_stage = os.stat(
                    "staged-context",
                    dir_fd=run_fd,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(current_stage.st_mode)
                    or _identity(current_stage) != stage_node
                ):
                    raise ValueError("stage root changed before verification")
                reopened_stage = _open_dir("staged-context", run_fd)
                try:
                    if _identity(_directory(reopened_stage)) != stage_node:
                        raise ValueError("stage root changed before verification")
                finally:
                    _close(reopened_stage)
                _verify_stage(stage_fd, stage_ledger)
                _lock_stage(stage_fd, stage_ledger)
                locked_stage = os.stat(
                    "staged-context",
                    dir_fd=run_fd,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(locked_stage.st_mode)
                    or _identity(locked_stage) != stage_node
                ):
                    raise ValueError("stage root changed during locking")
                staged = run_path / "staged-context"
            except BaseException:
                try:
                    _close(stage_fd)
                except BaseException:
                    pass
                stage_fd = None
                try:
                    _cleanup_stage(
                        run_fd,
                        "staged-context",
                        stage_node,
                        stage_ledger,
                    )
                except BaseException:
                    pass
                try:
                    _close(task_fd)
                except BaseException:
                    pass
                task_fd = None
                try:
                    _close(run_fd)
                except BaseException:
                    pass
                run_fd = None
                raise
            finally:
                _close(stage_fd)

        return PreparedScope(
            task_path,
            run_path,
            task_path / str(validate_relative_path(prompt_rel)),
            prompt.sha256,
            files,
            hashlib.sha256(rows).hexdigest(),
            staged,
        )
    finally:
        _close(task_fd)
        _close(run_fd)


def _open_verified_parent(
    root_fd: int,
    parts: tuple[str, ...],
    owned: dict[tuple[str, ...], tuple[int, int]],
) -> int:
    fd = os.dup(root_fd)
    _directory(fd)
    traversed: list[str] = []
    try:
        for component in parts:
            traversed.append(component)
            child = _open_dir(component, fd)
            expected = owned.get(tuple(traversed))
            if expected is not None and _identity(_directory(child)) != expected:
                _close(child)
                raise ValueError("created output parent changed")
            _close(fd)
            fd = child
        return fd
    except BaseException:
        _close(fd)
        raise


def _remove_created(root_fd: int, created: list[_OwnedDirectory]) -> None:
    owned = {entry.parts: entry.identity for entry in created}
    for entry in reversed(created):
        parent: int | None = None
        try:
            parent = _open_verified_parent(root_fd, entry.parts[:-1], owned)
            info = os.stat(entry.parts[-1], dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _identity(info) != entry.identity:
                continue
            child = _open_dir(entry.parts[-1], parent)
            try:
                if _identity(_directory(child)) != entry.identity:
                    continue
                os.fchmod(child, 0o700)
            finally:
                _close(child)
            current = os.stat(entry.parts[-1], dir_fd=parent, follow_symlinks=False)
            if stat.S_ISDIR(current.st_mode) and _identity(current) == entry.identity:
                os.rmdir(entry.parts[-1], dir_fd=parent)
        except (OSError, ValueError):
            pass
        finally:
            _close(parent)


def _unlink_owned_leaf(
    parent_fd: int,
    leaf: str,
    expected_node: tuple[int, int] | None,
) -> None:
    if expected_node is None:
        return
    try:
        info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISREG(info.st_mode) and _identity(info) == expected_node:
        os.unlink(leaf, dir_fd=parent_fd)


def open_output_leaf(
    run_root: Path,
    relative_path: str,
    mode: int = 0o600,
) -> BinaryIO:
    run_fd: int | None = None
    parent_fd: int | None = None
    fd: int | None = None
    created: list[_OwnedDirectory] = []
    leaf = ""
    leaf_node: tuple[int, int] | None = None
    try:
        _, run_fd, _ = _root(run_root)
        rel = validate_relative_path(relative_path)
        if type(mode) is not int or mode < 0 or mode > 0o777:
            raise ValueError("invalid output mode")
        try:
            parent_fd, leaf = _open_parent(run_fd, rel, create=True, created=created)
            if _COMPONENT_SWAP_HOOK is not None:
                _COMPONENT_SWAP_HOOK(leaf)
            fd = os.open(
                leaf,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                mode,
                dir_fd=parent_fd,
            )
            raw_info = os.fstat(fd)
            if stat.S_ISREG(raw_info.st_mode):
                leaf_node = _identity(raw_info)
            info = _regular_descriptor(fd)
            if leaf_node is None or _identity(info) != leaf_node:
                raise ValueError("output leaf changed during validation")
            os.fchmod(fd, mode)
            stream = os.fdopen(fd, "wb")
            fd = None
            return stream
        except (OSError, ValueError):
            try:
                _close(fd)
            except BaseException:
                pass
            fd = None
            if parent_fd is not None:
                try:
                    _unlink_owned_leaf(parent_fd, leaf, leaf_node)
                except BaseException:
                    pass
            try:
                _remove_created(run_fd, created)
            except BaseException:
                pass
            try:
                _close(parent_fd)
            except BaseException:
                pass
            parent_fd = None
            try:
                _close(run_fd)
            except BaseException:
                pass
            run_fd = None
            raise
    finally:
        _close(fd)
        _close(parent_fd)
        _close(run_fd)
