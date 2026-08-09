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
CHUNK_BYTES = 65_536
NOFOLLOW = getattr(os, "O_NOFOLLOW", None)
DIRECTORY = getattr(os, "O_DIRECTORY", None)
NONBLOCK = getattr(os, "O_NONBLOCK", 0)
CLOEXEC = getattr(os, "O_CLOEXEC", 0)
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
        commit="4bcfcb6c1868a87076502999a38127e28e275e70",
    ),
    Owner(
        repository="workflow-governance-model",
        protocol_kind="governance-handoff",
        protocol_version="1.1",
        schema_path="schemas/workflow-handoff.1.1.schema.json",
        bundled_schema_path="protocols/schemas/governance-handoff.1.1.schema.json",
        example_path="examples/handoff.valid.json",
        commit="98576b4f3f755aceccc657bc83df7c94260d4fc0",
    ),
    Owner(
        repository="mothership-router",
        protocol_kind="router-manifest",
        protocol_version="1.0",
        schema_path="src/mothership_router/schema/router-manifest.1.0.schema.json",
        bundled_schema_path="protocols/schemas/router-manifest.1.0.schema.json",
        example_path="examples/router-manifest.json",
        commit="a23f4b651e1a8baf39a1266a66188bec21c3265c",
    ),
    Owner(
        repository="secretary-tui",
        protocol_kind="observation-snapshot",
        protocol_version="1.0",
        schema_path="schemas/observation-snapshot.1.0.schema.json",
        bundled_schema_path="protocols/schemas/observation-snapshot.1.0.schema.json",
        example_path="examples/observation-snapshot.json",
        commit="f3cb61e61bc88e7c4cfd09efe93006c812258fe9",
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
    safe_root = _safe_root(root)
    if NOFOLLOW is None or DIRECTORY is None:
        raise ConformanceError("no-follow artifact access is unavailable")
    parent: int | None = None
    descriptor: int | None = None
    try:
        parent = os.open(
            os.fspath(safe_root),
            os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC,
        )
        if not stat.S_ISDIR(os.fstat(parent).st_mode):
            raise ConformanceError("artifact root is not a real directory")
        parts = PurePosixPath(safe).parts
        for component in parts[:-1]:
            child = os.open(
                component,
                os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC,
                dir_fd=parent,
            )
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise ConformanceError("artifact path contains a non-directory component")
            os.close(parent)
            parent = child
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | NOFOLLOW | NONBLOCK | CLOEXEC,
            dir_fd=parent,
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
            raise ConformanceError("artifact is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(CHUNK_BYTES, MAX_ARTIFACT_BYTES + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > MAX_ARTIFACT_BYTES:
                raise ConformanceError("artifact exceeds the byte limit")
        final = os.fstat(descriptor)
        if (info.st_dev, info.st_ino, info.st_size) != (
            final.st_dev,
            final.st_ino,
            final.st_size,
        ):
            raise ConformanceError("artifact changed while being read")
    except ConformanceError:
        raise
    except (OSError, TypeError, ValueError):
        raise ConformanceError("artifact is unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)
    return b"".join(chunks)


def _git_environment() -> dict[str, str]:
    return {
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }


def _run_git(root: Path, arguments: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", os.fspath(root), *arguments],
            check=False,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        raise ConformanceError("companion commit artifact is unavailable") from None


def _read_commit_file(root: Path, commit: object, relative_path: object) -> bytes:
    safe_root = _safe_root(root)
    safe = _safe_relative_path(relative_path)
    if type(commit) is not str or COMMIT_PATTERN.fullmatch(commit) is None:
        raise ConformanceError("companion commit is unavailable")
    listing = _run_git(safe_root, ("ls-tree", "-z", commit, "--", safe))
    if listing.returncode != 0 or not listing.stdout.endswith(b"\0"):
        raise ConformanceError("companion commit artifact is unavailable")
    records = listing.stdout[:-1].split(b"\0")
    if len(records) != 1 or b"\t" not in records[0]:
        raise ConformanceError("companion commit artifact is unavailable")
    identity, path = records[0].split(b"\t", 1)
    fields = identity.split(b" ")
    if (
        len(fields) != 3
        or fields[0] not in {b"100644", b"100755"}
        or fields[1] != b"blob"
        or path != safe.encode("utf-8")
    ):
        raise ConformanceError("companion commit artifact is not a regular file")
    oid = fields[2].decode("ascii", "strict")
    size_result = _run_git(safe_root, ("cat-file", "-s", oid))
    try:
        size = int(size_result.stdout.strip())
    except ValueError:
        raise ConformanceError("companion commit artifact is unavailable") from None
    if size_result.returncode != 0 or size < 0 or size > MAX_ARTIFACT_BYTES:
        raise ConformanceError("companion commit artifact exceeds the byte limit")
    content = _run_git(safe_root, ("cat-file", "blob", oid))
    if content.returncode != 0 or len(content.stdout) != size:
        raise ConformanceError("companion commit artifact is unavailable")
    return content.stdout


def _read_document(root: Path, relative_path: object) -> dict[str, object]:
    try:
        document = loads_strict(_read_regular_file(root, relative_path))
    except ContractError:
        raise ConformanceError("artifact JSON is invalid") from None
    if type(document) is not dict:
        raise ConformanceError("artifact JSON must be an object")
    return document


def _read_commit_document(
    root: Path,
    commit: str,
    relative_path: object,
) -> dict[str, object]:
    try:
        document = loads_strict(_read_commit_file(root, commit, relative_path))
    except ContractError:
        raise ConformanceError("artifact JSON is invalid") from None
    if type(document) is not dict:
        raise ConformanceError("artifact JSON must be an object")
    return document


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=_git_environment(),
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
    commit: str,
) -> tuple[dict[str, object], bytes, dict[str, object]]:
    manifest = _read_commit_document(root, commit, MANIFEST_PATH)
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

    owner_schema = _read_commit_file(root, commit, manifest["schema_path"])
    if hashlib.sha256(owner_schema).hexdigest() != digest:
        raise ConformanceError("owner schema digest drifted")
    bundled_schema = _read_regular_file(RESOURCE_ROOT, owner.bundled_schema_path)
    if owner_schema != bundled_schema:
        raise ConformanceError("owner schema differs from the frozen snapshot")

    example = _read_commit_document(root, commit, manifest["example_path"])
    try:
        validated = validate_protocol(owner.protocol_kind, example)
    except ProtocolError:
        raise ConformanceError("owner example failed Mothership validation") from None
    return manifest, owner_schema, validated


def _validate_chain(
    documents: tuple[dict[str, object], ...],
    secretary_root: Path,
    router_root: Path,
    secretary_commit: str,
    router_commit: str,
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

    secretary_router = _read_commit_file(
        secretary_root,
        secretary_commit,
        "examples/router-manifest.json",
    )
    owner_router = _read_commit_file(router_root, router_commit, OWNERS[2].example_path)
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
        manifest, owner_schema, document = _validate_manifest(root, owner, head)
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
        secretary_commit=OWNERS[3].commit,
        router_commit=OWNERS[2].commit,
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
