"""Explicit, bounded gh credential snapshot; never expose raw output."""
from __future__ import annotations

import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import time


_GH_TIMEOUT_SECONDS = 10.0
_MAX_TOKEN_BYTES = 2048
_GH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"


class GhAuthError(ValueError):
    """Credential acquisition failed without exposing diagnostic output."""


def _find_gh() -> str:
    executable = shutil.which("gh", path=_GH_PATH)
    if not executable:
        raise GhAuthError("GitHub CLI credential unavailable")
    resolved = Path(executable).resolve(strict=True)
    info = resolved.stat()
    trusted_roots = (Path("/opt/homebrew"), Path("/usr/local"), Path("/usr/bin"))
    if (not any(resolved.is_relative_to(root) for root in trusted_roots)
            or not stat.S_ISREG(info.st_mode) or info.st_mode & stat.S_IWOTH):
        raise GhAuthError("GitHub CLI credential unavailable")
    return str(resolved)


def _run_gh(executable: str, args: list[str]) -> bytes:
    """One child; bounded output and deadline; never retain stderr."""
    process = None
    try:
        if not Path(executable).is_absolute():
            raise GhAuthError("GitHub CLI credential unavailable")
        # Child-only environment excludes secret overrides and debug settings.
        env = {"HOME": str(Path.home()), "PATH": _GH_PATH, "LANG": "C",
               "GH_NO_UPDATE_NOTIFIER": "1", "GH_PROMPT_DISABLED": "1",
               "GH_TELEMETRY": "0", "DO_NOT_TRACK": "1"}
        process = subprocess.Popen(
            [executable, *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env,
        )
        deadline = time.monotonic() + _GH_TIMEOUT_SECONDS
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise GhAuthError("GitHub CLI credential unavailable")
                chunk = os.read(process.stdout.fileno(), _MAX_TOKEN_BYTES + 1 - len(output))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > _MAX_TOKEN_BYTES:
                    raise GhAuthError("GitHub CLI credential unavailable")
        remaining = deadline - time.monotonic()
        if remaining <= 0 or process.wait(timeout=remaining) != 0:
            raise GhAuthError("GitHub CLI credential unavailable")
        return bytes(output)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise GhAuthError("GitHub CLI credential unavailable") from None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except (OSError, subprocess.SubprocessError):
                    # Cleanup is unconfirmed; retain the original failure and stop.
                    pass
            if process.stdout is not None:
                process.stdout.close()


def load_secrets(category: str, account: str) -> tuple[str, str]:
    """Load one selected gh credential in memory, without refresh or fallback."""
    if category != "github" or type(account) is not str or re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", account
    ) is None:
        raise GhAuthError("GitHub CLI credential unavailable")
    # Do not silently select the default gh store when the host selected another.
    if os.getenv("GH_CONFIG_DIR") or os.getenv("XDG_CONFIG_HOME"):
        raise GhAuthError("GitHub CLI credential unavailable")
    try:
        executable = _find_gh()
        version_output = _run_gh(executable, ["--version"])
        match = re.match(rb"\Agh version ([0-9][0-9A-Za-z.+-]{0,63})(?: |\n)", version_output)
        if match is None:
            raise GhAuthError("GitHub CLI credential unavailable")
        raw = _run_gh(executable, ["auth", "token", "--hostname", "github.com",
                                   "--user", account, "--no-refresh"])
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        if not raw or any(c < 33 or c > 126 for c in raw):
            raise GhAuthError("GitHub CLI credential unavailable")
        return raw.decode("ascii"), match.group(1).decode("ascii")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise GhAuthError("GitHub CLI credential unavailable") from None
