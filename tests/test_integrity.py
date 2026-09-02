from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CHECKSUM_MANIFEST = "SHA256SUMS"


class ChecksumManifestTests(unittest.TestCase):
    def test_sha256sums_matches_every_tracked_file_except_itself(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=PACKAGE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=10,
        )
        tracked = {
            raw.decode("utf-8")
            for raw in completed.stdout.split(b"\0")
            if raw
        }
        expected_paths = tracked - {CHECKSUM_MANIFEST}

        manifest: dict[str, str] = {}
        for line in (PACKAGE_ROOT / CHECKSUM_MANIFEST).read_text("utf-8").splitlines():
            digest, separator, relative = line.partition("  ")
            self.assertEqual("  ", separator, f"invalid checksum line: {line!r}")
            self.assertNotIn(relative, manifest, f"duplicate checksum entry: {relative}")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            manifest[relative] = digest

        self.assertEqual(expected_paths, set(manifest))
        actual = {
            relative: hashlib.sha256((PACKAGE_ROOT / relative).read_bytes()).hexdigest()
            for relative in expected_paths
        }
        self.assertEqual(actual, manifest)


if __name__ == "__main__":
    unittest.main()
