"""Canonical JSON and bounded regular-file hashing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from .errors import ContractError


_CHUNK_SIZE = 64 * 1024


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON data as compact, sorted UTF-8 canonical bytes."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ContractError("value cannot be encoded as canonical JSON") from None


def sha256_bytes(raw: bytes) -> str:
    """Return the lowercase SHA-256 digest of exact bytes."""

    if type(raw) is not bytes:
        raise ContractError("hash input must be bytes")
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a regular file in bounded chunks without following a final symlink."""

    if not isinstance(path, Path):
        raise ContractError("hash path must be a pathlib.Path")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ContractError("no-follow file access is unavailable")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, TypeError, ValueError):
        raise ContractError("hash input could not be opened") from None
    digest = hashlib.sha256()
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ContractError("hash input must be a regular file")
        while True:
            block = os.read(descriptor, _CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    except ContractError:
        raise
    except OSError:
        raise ContractError("hash input could not be read") from None
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def canonical_json_sha256(value: object) -> str:
    """Return the lowercase SHA-256 digest of canonical JSON bytes."""

    return sha256_bytes(canonical_json_bytes(value))
