"""Safe, dependency-free loading and Generic JSONL import for Flight bundles."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
from importlib import resources
import os
from pathlib import Path
import stat

from orchestration.lib.canonical import canonical_json_bytes, canonical_json_sha256, sha256_bytes
from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import loads_strict

from .flight_contracts import (
    FlightError,
    REQUIRED_STAGES,
    validate_flight_event,
    validate_flight_index,
    validate_generic_event,
    validate_safe_metadata,
)


MAX_FILE_BYTES = 1_048_576
MAX_EVENTS = 256
CHUNK_BYTES = 65_536
_PACKAGED_REGISTRY_SHA256 = "cb5000ca90a1395c5efdf7362b5d9928fea70915a96af3c3b10542a7abbf0a14"
_ROOT_ENTRIES = frozenset({"flight.json", "events.jsonl", "artifacts", "report.md"})


@dataclass(frozen=True)
class FlightBundle:
    root: Path
    index: dict[str, object]
    events: tuple[dict[str, object], ...]
    events_bytes: bytes
    artifacts: tuple[tuple[str, int, str], ...]


def _file_error() -> None:
    raise FlightError("INVALID", "FLIGHT.INVALID.FILE")


def _registry_error() -> None:
    raise FlightError("INVALID", "FLIGHT.INVALID.REGISTRY")


def _privacy_error() -> None:
    raise FlightError("INVALID", "FLIGHT.INVALID.PRIVACY")


def _absolute_path(path: Path) -> Path:
    if not isinstance(path, Path):
        _file_error()
    try:
        return Path(os.path.abspath(os.fspath(path)))
    except (OSError, TypeError, ValueError):
        _file_error()
    raise AssertionError("unreachable")


def _open_directory(path: Path) -> int:
    """Open an absolute directory without following any path component."""

    absolute = _absolute_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(os.sep, flags)
        for component in absolute.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, TypeError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        _file_error()
    raise AssertionError("unreachable")


def _read_regular(directory_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            _file_error()
        remaining = MAX_FILE_BYTES + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == 0 and os.read(descriptor, 1):
            _file_error()
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, before.st_size)
            != (after.st_dev, after.st_ino, after.st_size)
            or len(raw) != before.st_size
        ):
            _file_error()
        return raw
    except FlightError:
        raise
    except (OSError, TypeError, ValueError):
        _file_error()
    finally:
        if descriptor is not None:
            os.close(descriptor)
    raise AssertionError("unreachable")


def _read_json(directory_fd: int, name: str) -> object:
    raw = _read_regular(directory_fd, name)
    try:
        return loads_strict(raw)
    except ContractError:
        _file_error()
    raise AssertionError("unreachable")


def _parse_jsonl(raw: bytes, validator: object) -> tuple[dict[str, object], ...]:
    if not raw or not raw.endswith(b"\n"):
        _file_error()
    rows = raw.splitlines(keepends=True)
    if not rows or len(rows) > MAX_EVENTS or any(not row.endswith(b"\n") for row in rows):
        _file_error()
    events: list[dict[str, object]] = []
    for row in rows:
        try:
            value = loads_strict(row[:-1])
        except ContractError:
            _file_error()
        try:
            event = validator(value)  # type: ignore[operator]
        except FlightError:
            raise
        if type(event) is not dict:
            _file_error()
        events.append(event)
    return tuple(events)


def _packaged_registry_sha256() -> str:
    try:
        registry_bytes = resources.files("mothership.resources").joinpath("protocols/registry.json").read_bytes()
        digest = sha256_bytes(registry_bytes)
    except (ModuleNotFoundError, OSError, TypeError, ValueError, ContractError):
        _registry_error()
    if digest != _PACKAGED_REGISTRY_SHA256:
        _registry_error()
    return digest


def _open_child_directory(directory_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        return os.open(name, flags, dir_fd=directory_fd)
    except (OSError, TypeError, ValueError):
        _file_error()
    raise AssertionError("unreachable")


def _artifact_rows(directory_fd: int, prefix: str = "artifacts") -> list[tuple[str, int, str]]:
    try:
        names = os.listdir(directory_fd)
    except OSError:
        _file_error()
    rows: list[tuple[str, int, str]] = []
    for name in sorted(names):
        try:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError:
            _file_error()
        path = f"{prefix}/{name}"
        if stat.S_ISDIR(info.st_mode):
            child_fd = _open_child_directory(directory_fd, name)
            try:
                rows.extend(_artifact_rows(child_fd, path))
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(info.st_mode) or not name.endswith(".json"):
            _file_error()
        raw = _read_regular(directory_fd, name)
        try:
            validate_safe_metadata(loads_strict(raw))
        except ContractError:
            _file_error()
        rows.append((path, len(raw), hashlib.sha256(raw).hexdigest()))
    return rows


def bundle_digest(index: dict[str, object], events_bytes: bytes, artifacts: tuple[tuple[str, int, str], ...]) -> str:
    """Calculate the non-self-referential digest for a complete Flight bundle."""

    index_input = copy.deepcopy(index)
    index_input["bundle_sha256"] = None
    index_input["declared_verdict"] = None
    payload = {
        "index": index_input,
        "events_sha256": sha256_bytes(events_bytes),
        "artifacts": [
            {"path": path, "size": size, "sha256": digest}
            for path, size, digest in sorted(artifacts)
        ],
    }
    return canonical_json_sha256(payload)


def _validate_bundle_relationships(
    index: dict[str, object], events: tuple[dict[str, object], ...], artifacts: tuple[tuple[str, int, str], ...]
) -> None:
    if [event["event_id"] for event in events] != index["event_ids"]:
        raise FlightError("INVALID", "FLIGHT.INVALID.SCHEMA")
    if any(event["run_id"] != index["run_id"] for event in events):
        raise FlightError("INVALID", "FLIGHT.INVALID.SCHEMA")
    profile = index["privacy_profile"]
    if profile == "metadata-only":
        if artifacts or any(event["subject"]["storage"] != "external" for event in events):  # type: ignore[index]
            _privacy_error()
        return
    artifact_digests = {path: digest for path, _size, digest in artifacts}
    referenced: set[str] = set()
    for event in events:
        subject = event["subject"]
        if subject["storage"] == "bundled":  # type: ignore[index]
            location = subject["location"]  # type: ignore[index]
            digest = subject["sha256"]  # type: ignore[index]
            if location not in artifact_digests or artifact_digests[location] != digest:
                _privacy_error()
            referenced.add(location)
    if referenced != set(artifact_digests):
        _privacy_error()


def load_flight_bundle(path: Path) -> FlightBundle:
    """Safely load and validate an explicit Flight bundle directory."""

    root = _absolute_path(path)
    root_fd = _open_directory(root)
    try:
        try:
            entries = set(os.listdir(root_fd))
        except OSError:
            _file_error()
        if {"flight.json", "events.jsonl", "artifacts"} - entries or entries - _ROOT_ENTRIES:
            _file_error()
        index_value = _read_json(root_fd, "flight.json")
        try:
            index = validate_flight_index(index_value)
        except FlightError:
            raise
        if index["protocol_registry_sha256"] != _packaged_registry_sha256():
            _registry_error()
        events_bytes = _read_regular(root_fd, "events.jsonl")
        events = _parse_jsonl(events_bytes, validate_flight_event)
        artifacts_fd = _open_child_directory(root_fd, "artifacts")
        try:
            artifacts = tuple(sorted(_artifact_rows(artifacts_fd)))
        finally:
            os.close(artifacts_fd)
        _validate_bundle_relationships(index, events, artifacts)
        if index["bundle_sha256"] != bundle_digest(index, events_bytes, artifacts):
            raise FlightError("INVALID", "FLIGHT.INVALID.DIGEST")
        return FlightBundle(root, index, events, events_bytes, artifacts)
    finally:
        os.close(root_fd)


def _read_source(source: Path) -> bytes:
    absolute = _absolute_path(source)
    parent, name = os.path.split(os.fspath(absolute))
    if not name:
        _file_error()
    parent_fd = _open_directory(Path(parent))
    try:
        return _read_regular(parent_fd, name)
    finally:
        os.close(parent_fd)


def _write_new_file(directory_fd: int, name: str, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _file_error()
            offset += written
    except FlightError:
        raise
    except (OSError, TypeError, ValueError):
        _file_error()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def import_generic_jsonl(source: Path, output: Path) -> FlightBundle:
    """Import bounded Generic JSONL into a new metadata-only Flight bundle."""

    source_bytes = _read_source(source)
    generic_events = _parse_jsonl(source_bytes, validate_generic_event)
    if not generic_events:
        _file_error()
    if any(event["subject"]["storage"] != "external" for event in generic_events):  # type: ignore[index]
        _privacy_error()
    run_id = generic_events[0]["run_id"]
    if any(event["run_id"] != run_id for event in generic_events):
        raise FlightError("INVALID", "FLIGHT.INVALID.SCHEMA")
    registry_digest = _packaged_registry_sha256()
    events_bytes = b"".join(canonical_json_bytes(event) + b"\n" for event in generic_events)
    index: dict[str, object] = {
        "schema_version": "mothership.flight-index.v1",
        "run_id": run_id,
        "created_at": generic_events[0]["occurred_at"],
        "producer_class": "importer",
        "event_ids": [event["event_id"] for event in generic_events],
        "required_stages": list(REQUIRED_STAGES),
        "protocol_registry_sha256": registry_digest,
        "privacy_profile": "metadata-only",
        "bundle_sha256": None,
        "declared_verdict": None,
    }
    index["bundle_sha256"] = bundle_digest(index, events_bytes, ())
    index = validate_flight_index(index)

    target = _absolute_path(output)
    if os.path.lexists(target):
        _file_error()
    try:
        os.mkdir(target, 0o700)
    except (OSError, TypeError, ValueError):
        _file_error()
    output_fd: int | None = None
    try:
        output_fd = _open_directory(target)
        os.mkdir("artifacts", 0o700, dir_fd=output_fd)
        _write_new_file(output_fd, "flight.json", canonical_json_bytes(index))
        _write_new_file(output_fd, "events.jsonl", events_bytes)
    except FlightError:
        raise
    except (OSError, TypeError, ValueError):
        _file_error()
    finally:
        if output_fd is not None:
            os.close(output_fd)
    return FlightBundle(target, index, generic_events, events_bytes, ())


__all__ = (
    "CHUNK_BYTES",
    "MAX_EVENTS",
    "MAX_FILE_BYTES",
    "FlightBundle",
    "bundle_digest",
    "import_generic_jsonl",
    "load_flight_bundle",
)
