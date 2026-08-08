"""Strict JSON decoding for public data-only contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from .errors import ContractError


_CHUNK_SIZE = 64 * 1024


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError("JSON object contains a duplicate key")
        value[key] = item
    return value


def _reject_nonfinite(_value: str) -> None:
    raise ContractError("JSON contains a non-finite number")


def loads_strict(raw: bytes | str) -> object:
    """Decode one UTF-8 JSON document with duplicate and NaN rejection."""

    if type(raw) is bytes:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ContractError("JSON is not valid UTF-8") from None
    elif type(raw) is str:
        text = raw
    else:
        raise ContractError("JSON input must be bytes or text")
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, ValueError):
        raise ContractError("JSON document is invalid") from None


def load_strict(path: Path) -> object:
    """Stream and strictly decode one regular JSON file without following a final symlink."""

    if not isinstance(path, Path):
        raise ContractError("JSON path must be a pathlib.Path")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ContractError("no-follow file access is unavailable")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, TypeError, ValueError):
        raise ContractError("JSON file could not be opened") from None
    chunks: list[bytes] = []
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ContractError("JSON input must be a regular file")
        while True:
            block = os.read(descriptor, _CHUNK_SIZE)
            if not block:
                break
            chunks.append(block)
    except ContractError:
        raise
    except OSError:
        raise ContractError("JSON file could not be read") from None
    finally:
        os.close(descriptor)
    return loads_strict(b"".join(chunks))
