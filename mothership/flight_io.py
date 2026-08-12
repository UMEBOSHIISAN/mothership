"""Safe, dependency-free loading and Generic JSONL import for Flight bundles."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
from importlib import resources
import os
from pathlib import Path, PurePosixPath
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
_COMPONENT_OPEN_HOOK = None
_MEMBERSHIP_VERIFY_HOOK = None


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


def _normalized_absolute_path(path: Path) -> Path:
    if not isinstance(path, Path):
        _file_error()
    try:
        text = os.fspath(path)
    except TypeError:
        _file_error()
    if (
        type(text) is not str
        or not os.path.isabs(text)
        or text.startswith("//")
        or os.path.normpath(text) != text
        or PurePosixPath(text).as_posix() != text
    ):
        _file_error()
    return Path(text)


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _directory_info(descriptor: int) -> os.stat_result:
    try:
        info = os.fstat(descriptor)
    except OSError:
        _file_error()
    if not stat.S_ISDIR(info.st_mode):
        _file_error()
    return info


def _open_child_directory(directory_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        if _COMPONENT_OPEN_HOOK is not None:
            _COMPONENT_OPEN_HOOK(name)
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        _directory_info(descriptor)
        return descriptor
    except FlightError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        _file_error()
    raise AssertionError("unreachable")


def _open_directory(path: Path) -> int:
    """Open an absolute directory without following any path component."""

    absolute = _normalized_absolute_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(os.sep, flags)
        _directory_info(descriptor)
        for component in absolute.parts[1:]:
            child = _open_child_directory(descriptor, component)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except FlightError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        _file_error()
    raise AssertionError("unreachable")


def _open_parent(path: Path) -> tuple[int, str]:
    absolute = _normalized_absolute_path(path)
    parts = PurePosixPath(os.fspath(absolute)).parts
    if len(parts) < 2:
        _file_error()
    parent = Path(os.sep).joinpath(*parts[1:-1])
    return _open_directory(parent), parts[-1]


def _stat_member(directory_fd: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except (OSError, TypeError, ValueError):
        _file_error()
    raise AssertionError("unreachable")


def _open_existing_directory(
    directory_fd: int,
    name: str,
    expected_identity: tuple[int, int] | None = None,
) -> tuple[int, tuple[int, int]]:
    before = _stat_member(directory_fd, name)
    if not stat.S_ISDIR(before.st_mode):
        _file_error()
    identity = _identity(before)
    if expected_identity is not None and identity != expected_identity:
        _file_error()
    descriptor = _open_child_directory(directory_fd, name)
    try:
        if _identity(_directory_info(descriptor)) != identity:
            _file_error()
        current = _stat_member(directory_fd, name)
        if not stat.S_ISDIR(current.st_mode) or _identity(current) != identity:
            _file_error()
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _verify_directory_member(
    directory_fd: int,
    name: str,
    descriptor: int,
    identity: tuple[int, int],
    *,
    mode: int | None = None,
) -> None:
    current = _stat_member(directory_fd, name)
    opened = _directory_info(descriptor)
    if (
        not stat.S_ISDIR(current.st_mode)
        or _identity(current) != identity
        or _identity(opened) != identity
        or (mode is not None and stat.S_IMODE(opened.st_mode) != mode)
    ):
        _file_error()


def _read_regular_member(directory_fd: int, name: str) -> tuple[bytes, tuple[int, int]]:
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
        return raw, _identity(before)
    except FlightError:
        raise
    except (OSError, TypeError, ValueError):
        _file_error()
    finally:
        if descriptor is not None:
            os.close(descriptor)
    raise AssertionError("unreachable")


def _read_regular(directory_fd: int, name: str) -> bytes:
    raw, _member_identity = _read_regular_member(directory_fd, name)
    return raw


def _read_json_member(directory_fd: int, name: str) -> tuple[object, tuple[int, int]]:
    raw, identity = _read_regular_member(directory_fd, name)
    try:
        return loads_strict(raw), identity
    except ContractError:
        _file_error()
    raise AssertionError("unreachable")


def _snapshot_directory(directory_fd: int) -> dict[str, tuple[int, int, int]]:
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError:
        _file_error()
    snapshot: dict[str, tuple[int, int, int]] = {}
    for name in names:
        info = _stat_member(directory_fd, name)
        snapshot[name] = (stat.S_IFMT(info.st_mode), info.st_dev, info.st_ino)
    return snapshot


def _verify_membership(
    directory_fd: int,
    expected: dict[str, tuple[int, int, int]],
    label: str,
) -> None:
    if _MEMBERSHIP_VERIFY_HOOK is not None:
        _MEMBERSHIP_VERIFY_HOOK(label)
    if _snapshot_directory(directory_fd) != expected:
        _file_error()


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


def _artifact_rows(directory_fd: int, prefix: str = "artifacts") -> list[tuple[str, int, str]]:
    expected = _snapshot_directory(directory_fd)
    rows: list[tuple[str, int, str]] = []
    for name, member in expected.items():
        path = f"{prefix}/{name}"
        if member[0] == stat.S_IFDIR:
            child_fd, child_identity = _open_existing_directory(
                directory_fd,
                name,
                (member[1], member[2]),
            )
            try:
                rows.extend(_artifact_rows(child_fd, path))
                _verify_directory_member(directory_fd, name, child_fd, child_identity)
            finally:
                os.close(child_fd)
            continue
        if member[0] != stat.S_IFREG or not name.endswith(".json"):
            _file_error()
        raw, identity = _read_regular_member(directory_fd, name)
        if identity != (member[1], member[2]):
            _file_error()
        try:
            validate_safe_metadata(loads_strict(raw))
        except ContractError:
            _file_error()
        rows.append((path, len(raw), hashlib.sha256(raw).hexdigest()))
    _verify_membership(directory_fd, expected, prefix)
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

    root = _normalized_absolute_path(path)
    root_parent_fd, root_name = _open_parent(root)
    root_fd: int | None = None
    try:
        root_fd, root_identity = _open_existing_directory(root_parent_fd, root_name)
        root_snapshot = _snapshot_directory(root_fd)
        entries = set(root_snapshot)
        if {"flight.json", "events.jsonl", "artifacts"} - entries or entries - _ROOT_ENTRIES:
            _file_error()
        if (
            root_snapshot["flight.json"][0] != stat.S_IFREG
            or root_snapshot["events.jsonl"][0] != stat.S_IFREG
            or root_snapshot["artifacts"][0] != stat.S_IFDIR
        ):
            _file_error()
        index_value, index_identity = _read_json_member(root_fd, "flight.json")
        if index_identity != root_snapshot["flight.json"][1:]:
            _file_error()
        try:
            index = validate_flight_index(index_value)
        except FlightError:
            raise
        if index["protocol_registry_sha256"] != _packaged_registry_sha256():
            _registry_error()
        events_bytes, events_identity = _read_regular_member(root_fd, "events.jsonl")
        if events_identity != root_snapshot["events.jsonl"][1:]:
            _file_error()
        events = _parse_jsonl(events_bytes, validate_flight_event)
        artifacts_fd, artifacts_identity = _open_existing_directory(
            root_fd,
            "artifacts",
            root_snapshot["artifacts"][1:],
        )
        try:
            if index["privacy_profile"] == "metadata-only":
                artifact_snapshot = _snapshot_directory(artifacts_fd)
                if artifact_snapshot:
                    _privacy_error()
                _verify_membership(artifacts_fd, artifact_snapshot, "artifacts")
                artifacts: tuple[tuple[str, int, str], ...] = ()
            else:
                artifacts = tuple(sorted(_artifact_rows(artifacts_fd)))
            _verify_directory_member(root_fd, "artifacts", artifacts_fd, artifacts_identity)
        finally:
            os.close(artifacts_fd)
        _validate_bundle_relationships(index, events, artifacts)
        if index["bundle_sha256"] != bundle_digest(index, events_bytes, artifacts):
            raise FlightError("INVALID", "FLIGHT.INVALID.DIGEST")
        _verify_membership(root_fd, root_snapshot, "root")
        _verify_directory_member(root_parent_fd, root_name, root_fd, root_identity)
        return FlightBundle(root, index, events, events_bytes, artifacts)
    finally:
        if root_fd is not None:
            os.close(root_fd)
        os.close(root_parent_fd)


def _read_source(source: Path) -> bytes:
    absolute = _normalized_absolute_path(source)
    parent_fd, name = _open_parent(absolute)
    try:
        return _read_regular(parent_fd, name)
    finally:
        os.close(parent_fd)


def _create_directory(directory_fd: int, name: str, mode: int) -> tuple[int, tuple[int, int]]:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except (OSError, TypeError, ValueError):
        _file_error()
    else:
        _file_error()
    try:
        os.mkdir(name, mode, dir_fd=directory_fd)
    except (OSError, TypeError, ValueError):
        _file_error()
    created = _stat_member(directory_fd, name)
    if not stat.S_ISDIR(created.st_mode):
        _file_error()
    identity = _identity(created)
    descriptor, opened_identity = _open_existing_directory(directory_fd, name, identity)
    try:
        if opened_identity != identity:
            _file_error()
        os.fchmod(descriptor, mode)
        _verify_directory_member(directory_fd, name, descriptor, identity, mode=mode)
        return descriptor, identity
    except FlightError:
        os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError):
        os.close(descriptor)
        _file_error()
    raise AssertionError("unreachable")


def _write_new_file(directory_fd: int, name: str, raw: bytes) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _file_error()
            offset += written
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != len(raw):
            _file_error()
        return _identity(info)
    except FlightError:
        raise
    except (OSError, TypeError, ValueError):
        _file_error()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def import_generic_jsonl(source: Path, output: Path) -> FlightBundle:
    """Import bounded Generic JSONL into a new metadata-only Flight bundle."""

    target = _normalized_absolute_path(output)
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

    parent_fd, target_name = _open_parent(target)
    output_fd: int | None = None
    artifacts_fd: int | None = None
    try:
        output_fd, output_identity = _create_directory(parent_fd, target_name, 0o700)
        artifacts_fd, artifacts_identity = _create_directory(output_fd, "artifacts", 0o700)
        flight_identity = _write_new_file(output_fd, "flight.json", canonical_json_bytes(index))
        events_identity = _write_new_file(output_fd, "events.jsonl", events_bytes)
        output_snapshot = _snapshot_directory(output_fd)
        if set(output_snapshot) != {"flight.json", "events.jsonl", "artifacts"}:
            _file_error()
        if (
            output_snapshot["flight.json"] != (stat.S_IFREG, *flight_identity)
            or output_snapshot["events.jsonl"] != (stat.S_IFREG, *events_identity)
            or output_snapshot["artifacts"] != (stat.S_IFDIR, *artifacts_identity)
        ):
            _file_error()
        _verify_membership(artifacts_fd, {}, "output-artifacts")
        _verify_directory_member(output_fd, "artifacts", artifacts_fd, artifacts_identity, mode=0o700)
        _verify_directory_member(parent_fd, target_name, output_fd, output_identity, mode=0o700)
    except FlightError:
        raise
    except (OSError, TypeError, ValueError):
        _file_error()
    finally:
        if artifacts_fd is not None:
            os.close(artifacts_fd)
        if output_fd is not None:
            os.close(output_fd)
        os.close(parent_fd)
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
