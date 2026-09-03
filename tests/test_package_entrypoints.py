from __future__ import annotations

import importlib
from importlib import metadata
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class PackageEntrypointTests(unittest.TestCase):
    def test_version_contract_uses_distribution_then_clone_fallback(self) -> None:
        import mothership

        expected = (PACKAGE_ROOT / "VERSION").read_text("utf-8").strip()
        self.assertEqual("0.4.1", expected)
        self.assertEqual(expected, mothership.__version__)

        with mock.patch.object(metadata, "version", return_value="9.8.7"):
            self.assertEqual("9.8.7", importlib.reload(mothership).__version__)
        with mock.patch.object(
            metadata,
            "version",
            side_effect=metadata.PackageNotFoundError("mothership-control-plane"),
        ):
            self.assertEqual(expected, importlib.reload(mothership).__version__)
        importlib.reload(mothership)

    def test_build_metadata_has_no_runtime_dependencies(self) -> None:
        project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text("utf-8"))[
            "project"
        ]
        self.assertEqual("mothership-control-plane", project["name"])
        self.assertEqual(["version"], project["dynamic"])
        self.assertEqual(">=3.12", project["requires-python"])
        self.assertEqual([], project["dependencies"])
        self.assertEqual("mothership.cli:main", project["scripts"]["mothership"])

    def test_module_help_is_successful_and_side_effect_free(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "mothership", "--help"],
            cwd=PACKAGE_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("verify", result.stdout)
        self.assertIn("doctor", result.stdout)
        self.assertIn("protocol", result.stdout)
        self.assertIn("demo", result.stdout)
        self.assertEqual("", result.stderr)

    def test_main_accepts_explicit_argv(self) -> None:
        from mothership.cli import main
        from mothership.verify import verify_installation
        from orchestration.lib.canonical import canonical_json_bytes

        with mock.patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(0, main(["verify"]))
        self.assertEqual(
            canonical_json_bytes(verify_installation()).decode("utf-8") + "\n",
            stdout.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
