#!/usr/bin/env python3
"""Audit four explicit companion roots against the frozen Mothership 0.2 suite."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import TextIO


ROOT = Path(__file__).resolve().parents[1]
if os.fspath(ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(ROOT))

from mothership.protocols import ProtocolError, validate_protocol
from orchestration.lib.canonical import canonical_json_bytes
from orchestration.lib.errors import ContractError
from orchestration.lib.jsonio import loads_strict


RESOURCE_ROOT = ROOT / "mothership/resources"
MANIFEST_PATH = "suite/mothership-0.2-conformance.json"
MAX_ARTIFACT_BYTES = 1_048_576
MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "suite_release",
        "repository",
        "protocol_kind",
        "protocol_version",
        "schema_path",
        "schema_sha256",
        "example_path",
        "authority_effect",
        "execution_effect",
    }
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


class ConformanceError(ValueError):
    """One explicit companion root failed the closed suite audit."""


@dataclass(frozen=True)
class Owner:
    repository: str
    protocol_kind: str
    protocol_version: str
    schema_path: str
    bundled_schema_path: str
    example_path: str
    commit: str


OWNERS = (
    Owner(
        repository="agent-frontdoor",
        protocol_kind="frontdoor-task",
        protocol_version="intake.v0",
        schema_path="src/frontdoor/schema/intake.v0.json",
        bundled_schema_path="protocols/schemas/frontdoor-task.intake.v0.schema.json",
        example_path="examples/mothership-task.json",
        commit="296c49be801b6573abf54daa81b828df95e8e84f",
    ),
    Owner(
        repository="workflow-governance-model",
        protocol_kind="governance-handoff",
        protocol_version="1.1",
        schema_path="schemas/workflow-handoff.1.1.schema.json",
        bundled_schema_path="protocols/schemas/governance-handoff.1.1.schema.json",
        example_path="examples/handoff.valid.json",
        commit="faec3725781547cc64e58b3eb14177885bd315f6",
    ),
    Owner(
        repository="mothership-router",
        protocol_kind="router-manifest",
        protocol_version="1.0",
        schema_path="src/mothership_router/schema/router-manifest.1.0.schema.json",
        bundled_schema_path="protocols/schemas/router-manifest.1.0.schema.json",
        example_path="examples/router-manifest.json",
        commit="e4669fb9534bf97030134d4305caa492c87f7ed3",
    ),
    Owner(
        repository="secretary-tui",
        protocol_kind="observation-snapshot",
        protocol_version="1.0",
        schema_path="schemas/observation-snapshot.1.0.schema.json",
        bundled_schema_path="protocols/schemas/observation-snapshot.1.0.schema.json",
        example_path="examples/observation-snapshot.json",
        commit="bd933d5dee7dbe4b9ca8057f7848c2ef70261b2d",
    ),
)


def _safe_relative_path(value: object) -> str:
    if type(value) is not str or not value:
        raise ConformanceError("unsafe artifact path")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != value
        or any(part in ("", ".", "..") for part in parsed.parts)
    ):
        raise ConformanceError("unsafe artifact path")
    return value


def _safe_root(root: object) -> Path:
    if not isinstance(root, Path):
        raise ConformanceError("companion root must be a pathlib.Path")
    text = os.fspath(root)
    if (
        not os.path.isabs(text)
        or os.path.normpath(text) != text
        or root == Path("/")
    ):
        raise ConformanceError("companion root is not absolute and normalized")
    try:
        if root.resolve(strict=True) != root or not stat.S_ISDIR(root.stat().st_mode):
            raise ConformanceError("companion root is not a real directory")
    except OSError:
        raise ConformanceError("companion root is unavailable") from None
    return root


def _read_regular_file(root: Path, relative_path: object) -> bytes:
    safe = _safe_relative_path(relative_path)
    candidate = root.joinpath(*PurePosixPath(safe).parts)
    try:
        if candidate.resolve(strict=True) != candidate:
            raise ConformanceError("artifact path contains a symbolic link")
        info = candidate.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
            raise ConformanceError("artifact is not a bounded regular file")
        data = candidate.read_bytes()
    except ConformanceError:
        raise
    except OSError:
        raise ConformanceError("artifact is unavailable") from None
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ConformanceError("artifact exceeds the byte limit")
    return data


def _read_document(root: Path, relative_path: object) -> dict[str, object]:
    try:
        document = loads_strict(_read_regular_file(root, relative_path))
    except ContractError:
        raise ConformanceError("artifact JSON is invalid") from None
    if type(document) is not dict:
        raise ConformanceError("artifact JSON must be an object")
    return document


def _git_head(root: Path) -> str:
    environment = {
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise ConformanceError("companion commit is unavailable") from None
    head = result.stdout.strip()
    if result.returncode != 0 or COMMIT_PATTERN.fullmatch(head) is None:
        raise ConformanceError("companion commit is unavailable")
    return head


def _validate_manifest(
    root: Path,
    owner: Owner,
) -> tuple[dict[str, object], bytes, dict[str, object]]:
    manifest = _read_document(root, MANIFEST_PATH)
    if set(manifest) != MANIFEST_KEYS:
        raise ConformanceError("conformance manifest shape drifted")
    expected = {
        "schema_version": "mothership.conformance.v1",
        "suite_release": "0.2.0",
        "repository": owner.repository,
        "protocol_kind": owner.protocol_kind,
        "protocol_version": owner.protocol_version,
        "schema_path": owner.schema_path,
        "example_path": owner.example_path,
        "authority_effect": False,
        "execution_effect": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value or type(manifest.get(key)) is not type(value):
            raise ConformanceError("conformance manifest identity drifted")
    digest = manifest.get("schema_sha256")
    if type(digest) is not str or DIGEST_PATTERN.fullmatch(digest) is None:
        raise ConformanceError("conformance schema digest is invalid")

    owner_schema = _read_regular_file(root, manifest["schema_path"])
    if hashlib.sha256(owner_schema).hexdigest() != digest:
        raise ConformanceError("owner schema digest drifted")
    bundled_schema = _read_regular_file(RESOURCE_ROOT, owner.bundled_schema_path)
    if owner_schema != bundled_schema:
        raise ConformanceError("owner schema differs from the frozen snapshot")

    example = _read_document(root, manifest["example_path"])
    try:
        validated = validate_protocol(owner.protocol_kind, example)
    except ProtocolError:
        raise ConformanceError("owner example failed Mothership validation") from None
    return manifest, owner_schema, validated


def _validate_chain(
    documents: tuple[dict[str, object], ...],
    secretary_root: Path,
    router_root: Path,
) -> dict[str, object]:
    frontdoor, governance, router, observation = documents
    task_id = frontdoor.get("request_id")
    capability = frontdoor.get("predicted_worker_capability")
    if task_id != "demo-review-001" or capability != "code-review":
        raise ConformanceError("synthetic chain identity drifted")
    if governance.get("task_id") != task_id or governance.get("capability") != capability:
        raise ConformanceError("frontdoor-to-governance continuity failed")
    if router.get("task_id") != task_id or router.get("capability") != capability:
        raise ConformanceError("governance-to-router continuity failed")
    if router.get("status") != "approval_required":
        raise ConformanceError("synthetic Router status drifted")
    if (
        observation.get("task_id") != task_id
        or observation.get("source_kind") != "router-manifest"
        or observation.get("source_schema_version") != router.get("schema_version")
        or observation.get("status") != router.get("status")
    ):
        raise ConformanceError("router-to-observation continuity failed")
    if (
        router.get("authority_effect") is not False
        or router.get("execution_effect") is not False
        or observation.get("authority_effect") is not False
        or observation.get("execution_effect") is not False
    ):
        raise ConformanceError("effect escalation detected")

    secretary_router = _read_regular_file(secretary_root, "examples/router-manifest.json")
    owner_router = _read_regular_file(router_root, OWNERS[2].example_path)
    if secretary_router != owner_router:
        raise ConformanceError("Secretary Router input differs from the owner example")
    summary = observation.get("summary")
    candidate = router.get("recommended_alias")
    expected_lines = {"authority: none", "execution: none", "local snapshot"}
    if type(candidate) is str:
        expected_lines.add(f"candidate: {candidate}")
    if type(summary) is not list or not expected_lines.issubset(set(summary)):
        raise ConformanceError("observation summary continuity failed")
    return {
        "status": "passed",
        "task_id": task_id,
        "capability": capability,
        "authority_effect": False,
        "execution_effect": False,
    }


def audit_companions(roots: tuple[Path, ...]) -> dict[str, object]:
    """Audit exactly four ordered, explicit roots and return a path-free report."""

    if type(roots) is not tuple or len(roots) != len(OWNERS):
        raise ConformanceError("exactly four companion roots are required")
    safe_roots = tuple(_safe_root(root) for root in roots)
    reports: list[dict[str, object]] = []
    documents: list[dict[str, object]] = []
    for root, owner in zip(safe_roots, OWNERS, strict=True):
        head = _git_head(root)
        if head != owner.commit:
            raise ConformanceError("companion commit does not match the frozen suite")
        manifest, owner_schema, document = _validate_manifest(root, owner)
        reports.append(
            {
                "repository": owner.repository,
                "commit": head,
                "protocol_kind": owner.protocol_kind,
                "protocol_version": owner.protocol_version,
                "schema_sha256": hashlib.sha256(owner_schema).hexdigest(),
                "valid": True,
            }
        )
        documents.append(document)
        if manifest["authority_effect"] is not False or manifest["execution_effect"] is not False:
            raise ConformanceError("conformance manifest escalates effects")
    chain = _validate_chain(
        tuple(documents),
        secretary_root=safe_roots[3],
        router_root=safe_roots[2],
    )
    return {
        "schema_version": "mothership.companion-conformance.v1",
        "status": "passed",
        "suite_release": "0.2.0",
        "owners": reports,
        "chain": chain,
    }


def _parse_arguments(arguments: list[str]) -> tuple[Path, ...] | None:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--frontdoor-root")
    parser.add_argument("--wgm-root")
    parser.add_argument("--router-root")
    parser.add_argument("--secretary-root")
    try:
        values, unknown = parser.parse_known_args(arguments)
    except (argparse.ArgumentError, SystemExit):
        return None
    raw = (
        values.frontdoor_root,
        values.wgm_root,
        values.router_root,
        values.secretary_root,
    )
    if unknown or any(value is None for value in raw):
        return None
    return tuple(Path(value) for value in raw)


def main(
    arguments: list[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    roots = _parse_arguments(sys.argv[1:] if arguments is None else arguments)
    if roots is None:
        stderr.write("usage_error: four explicit companion roots are required\n")
        return 2
    try:
        report = audit_companions(roots)
    except (ConformanceError, OSError, ValueError):
        stderr.write("conformance_error: companion audit failed\n")
        return 1
    stdout.write((canonical_json_bytes(report) + b"\n").decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
