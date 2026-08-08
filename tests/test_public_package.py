from __future__ import annotations

from pathlib import Path
import unittest


class PublicPackageTests(unittest.TestCase):
    def test_staged_package_has_no_private_absolute_paths(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        private_absolute_prefix = b"/private" + b"/"
        for path in package_root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                with self.subTest(path=path.relative_to(package_root)):
                    self.assertNotIn(private_absolute_prefix, path.read_bytes())
