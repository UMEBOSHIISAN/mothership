"""Read-only integrity verification for installed Mothership resources."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import PurePosixPath
import re

from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import loads_strict

from . import __version__
from .demo import DemoError, run_demo
from .protocols import ProtocolError, list_protocols


_RESOURCE_PACKAGE = "mothership.resources"
_DIGEST = re.compile(r"[0-9a-f]{64}")
_CHECK_NAMES = (
    "executor_example",
    "golden_path",
    "inventory",
    "protocol_registry",
    "schema_digests",
)


class _VerificationFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _safe_relative(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    parsed = PurePosixPath(value)
    return (
        not parsed.is_absolute()
        and parsed.as_posix() == value
        and all(part not in ("", ".", "..") for part in parsed.parts)
    )


def _json_paths(root: object, prefix: str = "") -> tuple[str, ...]:
    found: list[str] = []
    try:
        children = sorted(root.iterdir(), key=lambda child: child.name)
    except (AttributeError, OSError):
        raise _VerificationFailure("inventory_shape_mismatch") from None
    for child in children:
        relative = f"{prefix}/{child.name}" if prefix else child.name
        try:
            if hasattr(child, "is_symlink") and child.is_symlink():
                raise _VerificationFailure("inventory_shape_mismatch")
            if child.is_dir():
                found.extend(_json_paths(child, relative))
            elif child.is_file() and child.name.endswith(".json") and relative != "inventory.json":
                found.append(relative)
        except OSError:
            raise _VerificationFailure("inventory_shape_mismatch") from None
    return tuple(found)


def _read_json(root: object, relative_path: str, failure_code: str) -> object:
    try:
        raw = root.joinpath(relative_path).read_bytes()
        return loads_strict(raw)
    except (AttributeError, ContractError, FileNotFoundError, OSError, TypeError, ValueError):
        raise _VerificationFailure(failure_code) from None


def _verify_inventory(root: object) -> None:
    inventory = _read_json(root, "inventory.json", "inventory_shape_mismatch")
    if (
        type(inventory) is not dict
        or set(inventory) != {"schema_version", "resources"}
        or inventory.get("schema_version") != "mothership.inventory.v1"
        or type(inventory.get("resources")) is not list
    ):
        raise _VerificationFailure("inventory_shape_mismatch")
    entries = inventory["resources"]
    paths: list[str] = []
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"path", "sha256", "size"}:
            raise _VerificationFailure("inventory_shape_mismatch")
        if not _safe_relative(entry["path"]):
            raise _VerificationFailure("inventory_shape_mismatch")
        if (
            type(entry["size"]) is not int
            or entry["size"] < 0
            or type(entry["sha256"]) is not str
            or _DIGEST.fullmatch(entry["sha256"]) is None
        ):
            raise _VerificationFailure("inventory_shape_mismatch")
        paths.append(entry["path"])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise _VerificationFailure("inventory_shape_mismatch")
    if tuple(paths) != _json_paths(root):
        raise _VerificationFailure("inventory_shape_mismatch")
    for entry in entries:
        try:
            raw = root.joinpath(entry["path"]).read_bytes()
        except (AttributeError, FileNotFoundError, OSError, TypeError, ValueError):
            raise _VerificationFailure("inventory_shape_mismatch") from None
        if len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise _VerificationFailure("inventory_digest_mismatch")


def _verify_executor_examples(root: object) -> None:
    blank = _read_json(root, "config/executors.example.json", "executor_example_invalid")
    if type(blank) is not dict or tuple(sorted(blank)) != ("local-advisory", "manual-review"):
        raise _VerificationFailure("executor_example_invalid")
    if any(type(row) is not dict or row != {"command": []} for row in blank.values()):
        raise _VerificationFailure("executor_example_invalid")

    staged = _read_json(root, "config/executors.json", "executor_example_invalid")
    expected_aliases = ("claude-code-agent", "codex-cli", "ollama-local")
    if type(staged) is not dict or tuple(sorted(staged)) != expected_aliases:
        raise _VerificationFailure("executor_example_invalid")
    for alias in expected_aliases:
        row = staged[alias]
        expected_keys = {"adapter_id", "capabilities", "state"}
        if alias == "ollama-local":
            expected_keys.add("model_alias")
        if (
            type(row) is not dict
            or set(row) != expected_keys
            or row.get("adapter_id") != alias
            or row.get("state") != "staged"
            or row.get("capabilities") != ["read-only", "advisory"]
        ):
            raise _VerificationFailure("executor_example_invalid")
        if alias == "ollama-local" and row.get("model_alias") != "friend-core-advisory":
            raise _VerificationFailure("executor_example_invalid")


def _failed(checks: dict[str, str], code: str) -> dict[str, object]:
    return {
        "schema_version": "mothership.verify.v1",
        "status": "failed",
        "version": __version__,
        "checks": checks,
        "errors": [code],
        "authority_effect": False,
        "execution_effect": False,
    }


def verify_installation() -> dict[str, object]:
    """Verify immutable installed resources without reading user state."""

    checks = {name: "not_run" for name in _CHECK_NAMES}
    try:
        root = resources.files(_RESOURCE_PACKAGE)
        _verify_inventory(root)
    except _VerificationFailure as failure:
        checks["inventory"] = "failed"
        checks["schema_digests"] = "failed"
        return _failed(checks, failure.code)
    checks["inventory"] = "passed"
    checks["schema_digests"] = "passed"

    try:
        list_protocols()
    except ProtocolError:
        checks["protocol_registry"] = "failed"
        return _failed(checks, "protocol_registry_invalid")
    checks["protocol_registry"] = "passed"

    try:
        _verify_executor_examples(root)
    except _VerificationFailure as failure:
        checks["executor_example"] = "failed"
        return _failed(checks, failure.code)
    checks["executor_example"] = "passed"

    try:
        run_demo()
    except (DemoError, ProtocolError):
        checks["golden_path"] = "failed"
        return _failed(checks, "golden_path_invalid")
    checks["golden_path"] = "passed"

    return {
        "schema_version": "mothership.verify.v1",
        "status": "passed",
        "version": __version__,
        "checks": checks,
        "authority_effect": False,
        "execution_effect": False,
    }


__all__ = ("verify_installation",)
