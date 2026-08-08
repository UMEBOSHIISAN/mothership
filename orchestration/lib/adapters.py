"""Immutable local adapter projections and fail-closed diagnostics."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from .paths import PreparedScope, ScopeFile, validate_relative_path


_ALIASES = ("claude-code-agent", "codex-cli", "ollama-local")
_LIMITATIONS = [
    "authentication-external",
    "binary-trust-external",
    "managed-policy-external",
]
_ENV_KEYS = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE")
_HELP_OPTION = re.compile(
    r"(?<![A-Za-z0-9_-])-{1,2}[A-Za-z0-9][A-Za-z0-9_-]*(?![A-Za-z0-9_-])"
)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", None)
_COMPONENT_SWAP_HOOK = None


@dataclass(frozen=True)
class AdapterPlan:
    alias: str
    argv: tuple[str, ...]
    stdin_bytes: bytes
    cwd: Path
    env: dict[str, str]


@dataclass(frozen=True)
class AdapterPlanPreview:
    alias: str
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]


def _check_alias(alias: str) -> None:
    if type(alias) is not str or alias not in _ALIASES:
        raise ValueError("adapter alias is invalid")


def _copied_environment(parent_env: Mapping[str, str], include_codex_home: bool) -> dict[str, str]:
    if not isinstance(parent_env, Mapping):
        raise ValueError("parent environment is invalid")
    result: dict[str, str] = {}
    allowed = set(_ENV_KEYS)
    if include_codex_home:
        allowed.add("CODEX_HOME")
    for key, value in parent_env.items():
        if type(key) is not str or type(value) is not str:
            raise ValueError("parent environment is invalid")
        if key in allowed or key.startswith("LC_"):
            result[key] = value
    return result


def _sanitized_environment(parent_env: Mapping[str, str], include_codex_home: bool) -> dict[str, str]:
    result = _copied_environment(parent_env, include_codex_home)
    result["FRIEND_MOTHERSHIP_CALL_DEPTH"] = "1"
    return result


def _diagnostic_environment(parent_env: Mapping[str, str]) -> dict[str, str]:
    return _copied_environment(parent_env, include_codex_home=False)


def _open_real_directory(path: Path) -> int:
    """Open an absolute directory without traversing any symlink component."""

    if _NOFOLLOW is None or not isinstance(path, Path):
        raise ValueError("staged root is invalid")
    text = os.fspath(path)
    if not os.path.isabs(text) or os.path.normpath(text) != text:
        raise ValueError("staged root is invalid")
    flags = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open("/", flags)
        for component in PurePosixPath(text).parts[1:]:
            if _COMPONENT_SWAP_HOOK is not None:
                _COMPONENT_SWAP_HOOK(component)
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ValueError("staged root is invalid")
        return descriptor
    except (OSError, TypeError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("staged root is invalid") from None


def _read_staged_file(root_fd: int, item: ScopeFile) -> bytes:
    if type(item) is not ScopeFile:
        raise ValueError("scope file is invalid")
    if type(item.relative_path) is not str or type(item.size) is not int or type(item.sha256) is not str:
        raise ValueError("scope file is invalid")
    if item.size < 0 or len(item.sha256) != 64 or any(char not in "0123456789abcdef" for char in item.sha256):
        raise ValueError("scope file is invalid")
    try:
        relative = validate_relative_path(item.relative_path)
    except ValueError:
        raise ValueError("scope file is invalid") from None
    parent = os.dup(root_fd)
    descriptor: int | None = None
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        for component in relative.parts[:-1]:
            if _COMPONENT_SWAP_HOOK is not None:
                _COMPONENT_SWAP_HOOK(component)
            child = os.open(component, directory_flags, dir_fd=parent)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise ValueError("staged context is unsafe")
            os.close(parent)
            parent = child
        if _COMPONENT_SWAP_HOOK is not None:
            _COMPONENT_SWAP_HOOK(relative.parts[-1])
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | _NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("staged context is unsafe")
        chunks: list[bytes] = []
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                break
            chunks.append(block)
        raw = b"".join(chunks)
    except (OSError, ValueError):
        raise ValueError("staged context is unsafe") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)
    if len(raw) != item.size or hashlib.sha256(raw).hexdigest() != item.sha256:
        raise ValueError("staged context does not match scope")
    return raw


def _checked_staged_root(scope: PreparedScope) -> tuple[Path, int]:
    if type(scope) is not PreparedScope or scope.staged_root is None or not isinstance(scope.staged_root, Path):
        raise ValueError("prepared scope has no staged root")
    return scope.staged_root, _open_real_directory(scope.staged_root)


def _projection(alias: str, cwd: Path, parent_env: Mapping[str, str]) -> tuple[tuple[str, ...], dict[str, str]]:
    _check_alias(alias)
    env = _sanitized_environment(parent_env, include_codex_home=True)
    if alias == "codex-cli":
        argv = (
            "codex", "-a", "never", "exec", "--ignore-user-config", "--ignore-rules",
            "--strict-config", "-c", 'web_search="disabled"', "-c", "features.apps=false",
            "-c", "features.hooks=false", "-c", "features.memories=false", "--ephemeral",
            "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(cwd),
            "--color", "never", "-",
        )
    elif alias == "claude-code-agent":
        argv = (
            "claude", "--print", "--safe-mode", "--tools", "", "--permission-mode", "plan",
            "--no-session-persistence", "--no-chrome", "--disable-slash-commands",
            "--strict-mcp-config", "--mcp-config", "{}", "--output-format", "json",
        )
    else:
        argv = ("ollama", "run", "friend-core-advisory")
    return argv, env


def _envelope(prompt: bytes, files: tuple[ScopeFile, ...], root_fd: int) -> bytes:
    if type(prompt) is not bytes or type(files) is not tuple:
        raise ValueError("adapter inputs are invalid")
    paths = [item.relative_path if type(item) is ScopeFile else None for item in files]
    if any(path is None for path in paths) or paths != sorted(paths, key=lambda path: path.encode("utf-8")):
        raise ValueError("scope files are not in strict UTF-8 order")
    if len(set(paths)) != len(paths):
        raise ValueError("scope files are duplicated")
    chunks = [
        b"FRIEND-MOTHERSHIP-ENVELOPE/1\n",
        f"prompt-bytes:{len(prompt)}\n".encode("ascii"),
        f"prompt-sha256:{hashlib.sha256(prompt).hexdigest()}\n\n".encode("ascii"),
        prompt,
        f"\ncontext-files:{len(files)}\n".encode("ascii"),
    ]
    for item in files:
        raw = _read_staged_file(root_fd, item)
        path = item.relative_path.encode("utf-8")
        chunks.extend((
            f"file-path-bytes:{len(path)}\n".encode("ascii"),
            b"file-path:" + path + b"\n",
            f"file-bytes:{len(raw)}\n".encode("ascii"),
            f"file-sha256:{hashlib.sha256(raw).hexdigest()}\n\n".encode("ascii"),
            raw,
            b"\n",
        ))
    chunks.append(b"END\n")
    return b"".join(chunks)


def build_adapter_plan(alias: str, prompt: bytes, scope: PreparedScope, parent_env: Mapping[str, str]) -> AdapterPlan:
    """Build one immutable local projection without launching it."""

    if type(prompt) is not bytes:
        raise ValueError("prompt must be bytes")
    cwd, root_fd = _checked_staged_root(scope)
    try:
        argv, env = _projection(alias, cwd, parent_env)
        stdin_bytes = prompt if alias == "codex-cli" else _envelope(prompt, scope.files, root_fd)
        return AdapterPlan(alias, argv, stdin_bytes, cwd, env)
    finally:
        os.close(root_fd)


def build_adapter_plan_preview(
    alias: str,
    prospective_staged_root: Path,
    parent_env: Mapping[str, str],
) -> AdapterPlanPreview:
    """Validate a future stage projection without reading or creating it."""

    _check_alias(alias)
    if not isinstance(prospective_staged_root, Path):
        raise ValueError("prospective staged root is invalid")
    text = os.fspath(prospective_staged_root)
    if (
        not os.path.isabs(text)
        or os.path.normpath(text) != text
        or prospective_staged_root.name != "staged-context"
    ):
        raise ValueError("prospective staged root is invalid")
    parent_fd = _open_real_directory(prospective_staged_root.parent)
    try:
        parent_info = os.fstat(parent_fd)
        if stat.S_IMODE(parent_info.st_mode) != 0o700:
            raise ValueError("prospective run root mode is invalid")
        try:
            os.stat("staged-context", dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("prospective staged root already exists")
    except OSError:
        raise ValueError("prospective staged root is invalid") from None
    finally:
        os.close(parent_fd)
    argv, env = _projection(alias, prospective_staged_root, parent_env)
    return AdapterPlanPreview(alias, argv, prospective_staged_root, env)


def _result(alias: str, status: str, required_flags: dict[str, bool], local_model_present: bool | None, version_sha256: str | None) -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "adapter_id": alias,
        "status": status,
        "required_flags": required_flags,
        "local_model_present": local_model_present,
        "version_sha256": version_sha256,
        "limitations": list(_LIMITATIONS),
        "authority_effect": "none",
    }


def _output_bytes(result: object, select_version: bool) -> bytes | None:
    if type(getattr(result, "returncode", None)) is not int or getattr(result, "returncode") != 0:
        return None
    stdout = getattr(result, "stdout", None)
    stderr = getattr(result, "stderr", None)
    if type(stdout) not in (bytes, str) or type(stderr) not in (bytes, str):
        return None
    chosen: bytes | str = stdout if stdout else stderr
    raw = chosen.encode("utf-8") if type(chosen) is str else chosen
    if select_version:
        raw = raw.strip(b" \t\r\n\v\f")
    return raw or None


def _doctor_definition(alias: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if alias == "codex-cli":
        return (
            ("codex", "--version"),
            ("codex", "exec", "--help"),
            ("-a", "--cd", "--color", "--ephemeral", "--ignore-rules", "--ignore-user-config", "--sandbox", "--skip-git-repo-check", "--strict-config", "-c"),
        )
    if alias == "claude-code-agent":
        return (
            ("claude", "--version"),
            ("claude", "--help"),
            ("--disable-slash-commands", "--mcp-config", "--no-chrome", "--no-session-persistence", "--output-format", "--permission-mode", "--print", "--safe-mode", "--strict-mcp-config", "--tools"),
        )
    return (("ollama", "--version"), ("ollama", "list"), ())


def _help_options(text: str) -> frozenset[str]:
    return frozenset(_HELP_OPTION.findall(text))


def doctor_adapter(alias: str, runner: Callable[[tuple[str, ...]], Any]) -> dict[str, object]:
    """Inspect one local CLI with at most a version and help/list probe."""

    _check_alias(alias)
    version_command, detail_command, flags = _doctor_definition(alias)
    required_flags = {flag: False for flag in sorted(flags)}
    local_model = False if alias == "ollama-local" else None
    try:
        version_raw = _output_bytes(runner(version_command), select_version=True)
    except Exception:
        version_raw = None
    if version_raw is None:
        return _result(alias, "unavailable", required_flags, local_model, None)
    version_digest = hashlib.sha256(version_raw).hexdigest()
    try:
        detail_raw = _output_bytes(runner(detail_command), select_version=False)
    except Exception:
        detail_raw = None
    if detail_raw is None:
        return _result(alias, "unavailable", required_flags, local_model, version_digest)
    try:
        detail = detail_raw.decode("utf-8")
    except UnicodeDecodeError:
        return _result(alias, "unavailable", required_flags, local_model, version_digest)
    if alias == "ollama-local":
        local_model = any(line.split() and line.split()[0] == "friend-core-advisory" for line in detail.splitlines())
        available = local_model
    else:
        options = _help_options(detail)
        required_flags = {flag: flag in options for flag in sorted(flags)}
        available = all(required_flags.values())
    return _result(alias, "available" if available else "unavailable", required_flags, local_model, version_digest)
