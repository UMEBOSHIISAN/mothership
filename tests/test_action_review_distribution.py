from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
import zipfile


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BUILD_PYTHON = Path(sys.executable)
HAS_BUILD = importlib.util.find_spec("build") is not None


@unittest.skipUnless(HAS_BUILD, "the existing local build environment is required")
class ActionReviewDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name).resolve()
        cls.source = cls.root / "source"
        shutil.copytree(
            PACKAGE_ROOT,
            cls.source,
            ignore=shutil.ignore_patterns(
                ".git",
                ".worktrees",
                "__pycache__",
                "*.pyc",
                "build",
                "dist",
                "*.egg-info",
            ),
        )
        cls.dist = cls.root / "dist"
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                str(BUILD_PYTHON),
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(cls.dist),
            ],
            cwd=cls.source,
            env=environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr.decode("utf-8", "replace"))
        wheels = tuple(cls.dist.glob("*.whl"))
        if len(wheels) != 1:
            raise AssertionError("build must produce exactly one wheel")
        cls.wheel = wheels[0]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_wheel_contains_action_review_facade_and_schemas(self) -> None:
        with zipfile.ZipFile(self.wheel) as archive:
            names = set(archive.namelist())
            self.assertIn("mothership/action_review.py", names)
            self.assertIn("orchestration/lib/action_review.py", names)
            self.assertIn(
                "evidence/contracts/authority-action-review-request.v0.schema.json", names
            )
            self.assertIn(
                "evidence/contracts/authority-action-review-response.v0.schema.json", names
            )

    def test_installed_wheel_exports_and_validates_action_review_without_source_path(self) -> None:
        environment = self.root / "wheel-env"
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        binary = environment / "bin/python"
        install_environment = dict(os.environ)
        install_environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                str(binary),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(self.wheel),
            ],
            cwd=self.root,
            env=install_environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", "replace"))
        script = r'''
from mothership.action_review import ActionReviewError, build_review_request, validate_review_response
from mothership.action_authority import freeze_action
from mothership.contracts import validate_contract

parameters = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}
context = {
    "host_id": "wheel-host",
    "session_id": "wheel-session",
    "actor_id": "wheel-actor",
    "runtime_generation": "wheel-runtime",
    "scope": ["github.merge_pr"],
}
frozen = freeze_action("act-wheel-review", "github.merge_pr", parameters)
request = build_review_request(frozen, request_id="review-wheel", host_context=context)
validate_contract("authority-action-review-request", request)
response = {
    "schema_version": "authority-action-review-response.v0",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "action_id": frozen.action["action_id"],
    "action_sha256": frozen.action_sha256,
    "decision": "approve",
}
assert validate_review_response(
    frozen, request, response, current_host_context=context
) == {
    "decision": "approve",
    "action_id": "act-wheel-review",
    "action_sha256": frozen.action_sha256,
}
assert ActionReviewError.__name__ == "ActionReviewError"
print("ACTION_REVIEW_WHEEL_OK")
'''
        run_environment = {
            "HOME": str(self.root),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = subprocess.run(
            [str(binary), "-I", "-c", script],
            cwd=self.root,
            env=run_environment,
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"ACTION_REVIEW_WHEEL_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
