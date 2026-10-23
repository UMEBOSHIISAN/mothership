"""Run the real, explicitly selected Harness fixture suite without successful skips.

This developer-only runner fetches nothing and changes no installation or host.
All Mothership imports come from this checkout; the test admits exact Harness
revisions and source hashes before importing the fixture's runtime modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_REVISIONS = frozenset({
    "d7640a03b4b823d960f6e382607ad04aa8678c84",  # historical engineering fixture
    "9d88a091a56e9a5fb76c3c901a1da75b01c5c110",  # public v0.1.7 release fixture
})
EXPECTED_SOURCES = {
    "local_execution_lease.py": "fcbc7b571f6033ea64b584468bd16e198e59abeb162fb8fbffb02bcba14b16d9",
    "local_execution_lease_state.py": "1e19380e036ad1b622b3aebce82c3cc6b97e2008bdaf0e382b0367dabffe94e2",
}


def check_fixture(fixture_revision, sources, dirty):
    if fixture_revision not in QUALIFIED_REVISIONS or sources != EXPECTED_SOURCES or dirty:
        raise RuntimeError("Harness fixture revision, sources or clean checkout differs from qualification")


def qualified_coverage(bridge_count, owner_count):
    return bridge_count >= 19 and owner_count >= 19


def run_suite(suite: unittest.TestSuite, *, stream=sys.stderr) -> dict[str, object]:
    discovered = suite.countTestCases()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {
        "discovered": discovered,
        "tests_run": result.testsRun,
        "skipped": len(result.skipped),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "qualified": bool(discovered and result.testsRun and result.wasSuccessful() and not result.skipped),
    }


def revision(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()


def fixture_metadata(root: Path) -> dict[str, object]:
    return {
        "fixture_revision": revision(root),
        "fixture_source_sha256": {
            name: hashlib.sha256((root / "runtime" / name).read_bytes()).hexdigest()
            for name in EXPECTED_SOURCES
        },
        "fixture_dirty": bool(subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"], check=True,
            capture_output=True, timeout=10,
        ).stdout),
    }


def check_checkout(root: Path) -> dict[str, object]:
    metadata = fixture_metadata(root)
    check_fixture(metadata["fixture_revision"], metadata["fixture_source_sha256"], metadata["fixture_dirty"])
    return metadata


def _test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _test_ids(test)
        else:
            yield test.id()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-root", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {
        "qualified": False, "discovered": 0, "tests_run": 0, "skipped": 0,
        "failures": 0, "errors": 0, "source_revision": None, "fixture_revision": None,
    }
    try:
        report["source_revision"] = revision(ROOT)
        report["source_dirty"] = bool(subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"], check=True,
            capture_output=True, timeout=10,
        ).stdout)
        fixture = args.harness_root.resolve(strict=True)
        report.update(fixture_metadata(fixture))
        check_fixture(report["fixture_revision"], report["fixture_source_sha256"], report["fixture_dirty"])
        os.environ["MOTHERSHIP_HARNESS_ROOT"] = str(fixture)
        for source in (ROOT, ROOT / "packages/mothership-github", ROOT / "packages/mothership-adapters"):
            sys.path.insert(0, str(source))
        suite = unittest.TestLoader().discover(
            str(ROOT / "packages/mothership-adapters/tests"), pattern="test_harness*.py",
        )
        identifiers = list(_test_ids(suite))
        report["bridge_tests"] = sum(name.startswith("test_harness.HarnessBridgeTests.") for name in identifiers)
        report["owner_tests"] = sum(name.startswith("test_harness_owner.HarnessReferenceOwnerTests.")
                                    for name in identifiers)
        report.update(run_suite(suite))
        if not qualified_coverage(report["bridge_tests"], report["owner_tests"]):
            report.update(qualified=False, coverage_error="required bridge or reference-owner cases missing")
    except Exception:
        # Missing checkout/hash/source is a failed qualification, never a skip.
        report.update(qualified=False, setup_error="fixture or source qualification unavailable")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
