from __future__ import annotations

import subprocess
from pathlib import Path
import unittest

EXCLUDED_DIRECTORIES = frozenset({"__pycache__", ".git"})


class PublicPackageTests(unittest.TestCase):
    def test_staged_package_has_no_private_absolute_paths(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        private_absolute_prefix = b"/private" + b"/"
        # Only the git-tracked package surface is shipped; untracked
        # development artifacts (e.g. logs/codex/) must not fail validation.
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=package_root,
            check=True,
            capture_output=True,
        ).stdout
        for name in tracked.split(b"\0"):
            if not name:
                continue
            path = package_root / name.decode("utf-8", "surrogateescape")
            if not path.is_file() or EXCLUDED_DIRECTORIES.intersection(path.parts):
                continue
            with self.subTest(path=path.relative_to(package_root)):
                self.assertNotIn(private_absolute_prefix, path.read_bytes())
