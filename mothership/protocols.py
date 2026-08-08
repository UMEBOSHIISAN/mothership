"""Fail-closed inspection and validation for ecosystem protocol documents."""

from __future__ import annotations

import hashlib
from importlib import resources
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import loads_strict


_MAX_BYTES = 1_048_576
_CHUNK_BYTES = 65_536
_NOFOLLOW = getattr(os, "O_NOFOLLOW", None)
_DIRECTORY = getattr(os, "O_DIRECTORY", None)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_RESOURCE_PACKAGE = "mothership.resources"
_KINDS = (
    "frontdoor-task",
    "governance-handoff",
    "router-manifest",
    "observation-snapshot",
)
_ENTRY_KEYS = frozenset(
    {
        "authority_capable",
        "bundled_schema_path",
        "execution_capable",
        "frozen_in_mothership",
        "kind",
        "owner_repository",
        "predecessors",
        "schema_sha256",
        "schema_version",
        "successors",
        "upstream_source_path",
    }
)
_SCHEMA_KEYWORDS = frozenset(
    {
        "$id",
        "$schema",
        "additionalProperties",
        "const",
        "description",
        "enum",
        "items",
        "minimum",
        "minItems",
        "minLength",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
    }
)
_TYPES = frozenset({"array", "boolean", "integer", "null", "number", "object", "string"})
_FORBIDDEN_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "command",
        "credential",
        "model_output",
        "password",
        "private_key",
        "private_path",
        "prompt",
        "provider_endpoint",
        "refresh_token",
        "secret",
    }
)
_DIGEST = re.compile(r"[0-9a-f]{64}")
_WINDOWS_ABSOLUTE = re.compile(r"[A-Za-z]:[\\/]")
_COMPONENT_OPEN_HOOK = None


class ProtocolError(ValueError):
    """A protocol resource, document, or path failed a closed check."""


def _error(path: str, reason: str) -> ProtocolError:
    return ProtocolError(f"{path}: {reason}")


def _resource_bytes(relative_path: str) -> bytes:
    try:
        parsed = PurePosixPath(relative_path)
        if (
            not relative_path
            or parsed.is_absolute()
            or parsed.as_posix() != relative_path
            or any(part in ("", ".", "..") for part in parsed.parts)
        ):
            raise ValueError
        return resources.files(_RESOURCE_PACKAGE).joinpath(relative_path).read_bytes()
    except (FileNotFoundError, OSError, TypeError, ValueError):
        raise _error("$", "packaged protocol resource is unavailable") from None


def _strict_resource_json(relative_path: str) -> object:
    try:
        return loads_strict(_resource_bytes(relative_path))
    except ContractError:
        raise _error("$", "packaged protocol resource is invalid") from None


def _load_registry() -> dict[str, object]:
    value = _strict_resource_json("protocols/registry.json")
    if type(value) is not dict or set(value) != {"schema_version", "protocols"}:
        raise _error("$", "protocol registry shape is invalid")
    if value.get("schema_version") != "mothership.protocol-registry.v1":
        raise _error("$.schema_version", "protocol registry version is unsupported")
    if type(value.get("protocols")) is not list:
        raise _error("$.protocols", "protocol registry entries must be an array")
    return value


def _safe_relative_resource(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    parsed = PurePosixPath(value)
    return (
        not parsed.is_absolute()
        and parsed.as_posix() == value
        and all(part not in ("", ".", "..") for part in parsed.parts)
    )


def _registry_entries() -> tuple[dict[str, object], ...]:
    raw_entries = _load_registry()["protocols"]
    entries: list[dict[str, object]] = []
    for index, raw in enumerate(raw_entries):
        path = f"$.protocols[{index}]"
        if type(raw) is not dict or set(raw) != _ENTRY_KEYS:
            raise _error(path, "protocol registry entry shape is invalid")
        entry = dict(raw)
        if type(entry["kind"]) is not str:
            raise _error(f"{path}.kind", "protocol kind is invalid")
        for name in (
            "schema_version",
            "owner_repository",
            "upstream_source_path",
            "bundled_schema_path",
            "frozen_in_mothership",
        ):
            if type(entry[name]) is not str or not entry[name]:
                raise _error(f"{path}.{name}", "protocol registry text is invalid")
        if not _safe_relative_resource(entry["upstream_source_path"]):
            raise _error(f"{path}.upstream_source_path", "protocol source path is unsafe")
        if not _safe_relative_resource(entry["bundled_schema_path"]):
            raise _error(f"{path}.bundled_schema_path", "bundled schema path is unsafe")
        if type(entry["schema_sha256"]) is not str or _DIGEST.fullmatch(entry["schema_sha256"]) is None:
            raise _error(f"{path}.schema_sha256", "schema digest is invalid")
        for name in ("predecessors", "successors"):
            links = entry[name]
            if (
                type(links) is not list
                or any(type(item) is not str for item in links)
                or len(set(links)) != len(links)
            ):
                raise _error(f"{path}.{name}", "protocol links are invalid")
        for name in ("authority_capable", "execution_capable"):
            if entry[name] is not False:
                raise _error(f"{path}.{name}", "initial protocol effect capability must be false")
        entries.append(entry)

    if tuple(entry["kind"] for entry in entries) != _KINDS:
        raise _error("$.protocols", "protocol order is invalid")
    by_kind = {entry["kind"]: entry for entry in entries}
    if len(by_kind) != len(entries):
        raise _error("$.protocols", "protocol kinds must be unique")
    for entry in entries:
        kind = entry["kind"]
        for predecessor in entry["predecessors"]:
            if predecessor not in by_kind or kind not in by_kind[predecessor]["successors"]:
                raise _error("$.protocols", "protocol predecessor edge is invalid")
        for successor in entry["successors"]:
            if successor not in by_kind or kind not in by_kind[successor]["predecessors"]:
                raise _error("$.protocols", "protocol successor edge is invalid")
    return tuple(entries)


def _load_schema(entry: dict[str, object]) -> dict[str, object]:
    relative_path = entry["bundled_schema_path"]
    raw = _resource_bytes(relative_path)
    if hashlib.sha256(raw).hexdigest() != entry["schema_sha256"]:
        raise _error("$", "bundled schema digest does not match registry")
    try:
        schema = loads_strict(raw)
    except ContractError:
        raise _error("$", "bundled protocol schema is invalid") from None
    if type(schema) is not dict:
        raise _error("$", "bundled protocol schema must be an object")
    return schema


def _audit_schema(schema: object, path: str = "$") -> None:
    if type(schema) is not dict:
        raise _error(path, "schema node must be an object")
    unknown = sorted(set(schema) - _SCHEMA_KEYWORDS)
    if unknown:
        raise _error(path, "unsupported schema keyword")
    declared_type = schema.get("type")
    if declared_type is not None and (type(declared_type) is not str or declared_type not in _TYPES):
        raise _error(path, "schema type declaration is invalid")
    if "required" in schema:
        required = schema["required"]
        if (
            type(required) is not list
            or any(type(name) is not str for name in required)
            or len(set(required)) != len(required)
        ):
            raise _error(path, "schema required declaration is invalid")
    properties = schema.get("properties")
    if properties is not None:
        if type(properties) is not dict or any(type(name) is not str for name in properties):
            raise _error(path, "schema properties declaration is invalid")
        for name in sorted(properties):
            _audit_schema(properties[name], f"{path}.properties.{name}")
    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        raise _error(path, "schema additionalProperties must be false")
    if "oneOf" in schema:
        variants = schema["oneOf"]
        if type(variants) is not list or len(variants) < 2:
            raise _error(path, "schema oneOf declaration is invalid")
        for index, variant in enumerate(variants):
            _audit_schema(variant, f"{path}.oneOf[{index}]")
    if "items" in schema:
        _audit_schema(schema["items"], f"{path}.items")
    for name in ("minLength", "minItems"):
        if name in schema and (type(schema[name]) is not int or schema[name] < 0):
            raise _error(path, f"schema {name} declaration is invalid")
    if "minimum" in schema and type(schema["minimum"]) not in (int, float):
        raise _error(path, "schema minimum declaration is invalid")
    if "enum" in schema and (type(schema["enum"]) is not list or not schema["enum"]):
        raise _error(path, "schema enum declaration is invalid")
    if "pattern" in schema:
        if type(schema["pattern"]) is not str:
            raise _error(path, "schema pattern declaration is invalid")
        try:
            re.compile(schema["pattern"])
        except re.error:
            raise _error(path, "schema pattern declaration is invalid") from None


def _verified_entries() -> tuple[tuple[dict[str, object], dict[str, object]], ...]:
    verified = []
    for entry in _registry_entries():
        schema = _load_schema(entry)
        _audit_schema(schema)
        verified.append((entry, schema))
    return tuple(verified)


def list_protocols() -> tuple[dict[str, object], ...]:
    """Return detached metadata for the verified bundled protocol chain."""

    return tuple(dict(entry) for entry, _schema in _verified_entries())


def _json_equal(left: object, right: object) -> bool:
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left == right
    if type(left) in (int, float) and type(right) in (int, float):
        if type(left) is float and not math.isfinite(left):
            return False
        if type(right) is float and not math.isfinite(right):
            return False
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(
            _json_equal(item, other)
            for item, other in zip(left, right, strict=True)
        )
    if type(left) is dict:
        return set(left) == set(right) and all(
            _json_equal(left[name], right[name]) for name in left
        )
    return left == right


def _matches_type(value: object, declared: str) -> bool:
    if declared == "object":
        return type(value) is dict
    if declared == "array":
        return type(value) is list
    if declared == "string":
        return type(value) is str
    if declared == "integer":
        return type(value) is int
    if declared == "number":
        return type(value) in (int, float) and type(value) is not bool and math.isfinite(value)
    if declared == "boolean":
        return type(value) is bool
    if declared == "null":
        return value is None
    return False


def _validate_node(value: object, schema: dict[str, object], path: str) -> None:
    if "oneOf" in schema:
        matches = 0
        for variant in schema["oneOf"]:
            try:
                _validate_node(value, variant, path)
            except ProtocolError:
                continue
            matches += 1
        if matches != 1:
            raise _error(path, "value does not match exactly one allowed shape")
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise _error(path, "value does not match the required constant")
    if "enum" in schema and not any(_json_equal(value, option) for option in schema["enum"]):
        raise _error(path, "value is outside the allowed enumeration")
    if "type" in schema and not _matches_type(value, schema["type"]):
        raise _error(path, "value has the wrong type")

    if type(value) is dict:
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                raise _error(f"{path}.{name}", "required field is missing")
        properties = schema.get("properties", {})
        unknown = sorted(set(value) - set(properties))
        if schema.get("additionalProperties") is False and unknown:
            raise _error(f"{path}.*", "unknown field is not permitted")
        for name in sorted(value):
            if name in properties:
                _validate_node(value[name], properties[name], f"{path}.{name}")
    elif type(value) is list:
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise _error(path, "array is shorter than permitted")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_node(item, schema["items"], f"{path}[{index}]")
    elif type(value) is str:
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise _error(path, "string is shorter than permitted")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise _error(path, "string does not match the required pattern")
    elif type(value) in (int, float) and type(value) is not bool:
        if "minimum" in schema and value < schema["minimum"]:
            raise _error(path, "number is below the minimum")


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _child_path(path: str, name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
        return f"{path}.*"
    return f"{path}.{name}"


def _scan_safe_metadata(value: object, path: str = "$") -> None:
    if type(value) is dict:
        if any(type(name) is not str for name in value):
            raise _error(f"{path}.*", "object keys must be strings")
        for name in sorted(value):
            child_path = _child_path(path, name)
            if _normalized_key(name) in _FORBIDDEN_KEYS:
                raise _error(child_path, "forbidden sensitive or raw-content key")
            _scan_safe_metadata(value[name], child_path)
    elif type(value) is list:
        for index, item in enumerate(value):
            _scan_safe_metadata(item, f"{path}[{index}]")
    elif type(value) is str:
        if value.startswith(("/", "~/")) or _WINDOWS_ABSOLUTE.match(value):
            raise _error(path, "private absolute path is not permitted")


def _entry_for_kind(kind: object) -> tuple[dict[str, object], dict[str, object]]:
    if type(kind) is not str or kind not in _KINDS:
        raise _error("$", "protocol kind is unknown")
    for entry, schema in _verified_entries():
        if entry["kind"] == kind:
            return entry, schema
    raise _error("$", "protocol kind is unknown")


def validate_protocol(kind: str, document: object) -> dict[str, object]:
    """Validate one decoded protocol document and return a detached object."""

    entry, schema = _entry_for_kind(kind)
    if type(document) is not dict:
        raise _error("$", "protocol document must be an object")
    if document.get("schema_version") != entry["schema_version"]:
        raise _error("$.schema_version", "protocol version is unsupported")
    _scan_safe_metadata(document)
    _validate_node(document, schema, "$")
    return dict(document)


def _open_directory(name: str, parent: int | None = None) -> int:
    if _NOFOLLOW is None or _DIRECTORY is None:
        raise _error("$", "no-follow protocol file access is unavailable")
    if _COMPONENT_OPEN_HOOK is not None:
        _COMPONENT_OPEN_HOOK(name)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC,
            dir_fd=parent,
        )
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError
        return descriptor
    except (OSError, TypeError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        raise _error("$", "protocol file could not be opened") from None


def _load_protocol_file(path: Path) -> object:
    if _NOFOLLOW is None:
        raise _error("$", "no-follow protocol file access is unavailable")
    if not isinstance(path, Path):
        raise _error("$", "protocol path must be a pathlib.Path")
    text = os.fspath(path)
    if (
        type(text) is not str
        or not os.path.isabs(text)
        or os.path.normpath(text) != text
        or PurePosixPath(text).as_posix() != text
        or text == "/"
    ):
        raise _error("$", "protocol path must be an absolute normalized path")

    parent: int | None = None
    descriptor: int | None = None
    try:
        parent = _open_directory("/")
        parts = PurePosixPath(text).parts[1:]
        for component in parts[:-1]:
            child = _open_directory(component, parent)
            os.close(parent)
            parent = child
        if _COMPONENT_OPEN_HOOK is not None:
            _COMPONENT_OPEN_HOOK(parts[-1])
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY | _NOFOLLOW | _NONBLOCK | _CLOEXEC,
                dir_fd=parent,
            )
        except (OSError, TypeError, ValueError):
            raise _error("$", "protocol file could not be opened") from None
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _error("$", "protocol input must be a regular file")
        if info.st_size > _MAX_BYTES:
            raise _error("$", "protocol file exceeds 1 MiB")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(_CHUNK_BYTES, _MAX_BYTES + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > _MAX_BYTES:
                raise _error("$", "protocol file exceeds 1 MiB")
        final = os.fstat(descriptor)
        if (info.st_dev, info.st_ino, info.st_size) != (final.st_dev, final.st_ino, final.st_size):
            raise _error("$", "protocol file changed while being read")
    except ProtocolError:
        raise
    except OSError:
        raise _error("$", "protocol file could not be read") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)
    try:
        return loads_strict(b"".join(chunks))
    except ContractError:
        raise _error("$", "protocol JSON is invalid") from None


def validate_protocol_file(kind: str, path: Path) -> dict[str, object]:
    """Load and validate one explicit absolute local protocol file."""

    _entry_for_kind(kind)
    return validate_protocol(kind, _load_protocol_file(path))


__all__ = (
    "ProtocolError",
    "list_protocols",
    "validate_protocol",
    "validate_protocol_file",
)
