from __future__ import annotations

import importlib.util
import json
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
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
HAS_BUILD = importlib.util.find_spec("build") is not None
COPY_IGNORES = shutil.ignore_patterns(
    ".git",
    ".worktrees",
    ".venv",
    "venv",
    "__pycache__",
    "*.pyc",
    "build",
    "dist",
    "*.egg-info",
)


def _environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "XDG_CONFIG_HOME": str(home / "config"),
    }


def _run(
    argv: list[object],
    *,
    cwd: Path,
    home: Path,
    timeout: int,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(argument) for argument in argv],
        cwd=cwd,
        env=_environment(home),
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def _failure(result: subprocess.CompletedProcess[bytes]) -> str:
    return (
        f"returncode={result.returncode}\n"
        f"stdout={result.stdout.decode('utf-8', 'replace')}\n"
        f"stderr={result.stderr.decode('utf-8', 'replace')}"
    )


def _wheel_metadata(wheel: Path) -> tuple[str, set[str]]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_names = sorted(name for name in names if name.endswith(".dist-info/METADATA"))
        if len(metadata_names) != 1:
            raise AssertionError(f"wheel must contain one METADATA file: {wheel}")
        return archive.read(metadata_names[0]).decode("utf-8"), names


@unittest.skipUnless(HAS_BUILD, "install the test extra to run distribution verification")
class BuiltCompanionDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="mothership-companion-wheel-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.core_source = cls.root / "core-source"
        cls.companion_source = cls.root / "companion-source"
        shutil.copytree(REPOSITORY_ROOT, cls.core_source, ignore=COPY_IGNORES)
        shutil.copytree(PACKAGE_ROOT, cls.companion_source, ignore=COPY_IGNORES)
        cls.core_dist = cls.root / "core-dist"
        cls.companion_dist = cls.root / "companion-dist"
        cls.core_wheel = cls._build_wheel(cls.core_source, cls.core_dist)
        cls.companion_wheel = cls._build_wheel(cls.companion_source, cls.companion_dist)

    @classmethod
    def _build_wheel(cls, source: Path, output: Path) -> Path:
        output.mkdir(parents=True, exist_ok=True)
        result = _run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                output,
            ],
            cwd=source,
            home=cls.root,
            timeout=180,
        )
        if result.returncode != 0:
            raise AssertionError(f"wheel build failed for {source}:\n{_failure(result)}")
        wheels = sorted(output.glob("*.whl"))
        if len(wheels) != 1:
            raise AssertionError(f"expected one wheel in {output}, found {wheels}")
        return wheels[0]

    def _environment(self, name: str, wheels: tuple[Path, ...]) -> tuple[Path, Path]:
        environment = self.root / name
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        binary = environment / "bin" / "python"
        install = _run(
            [
                binary,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--disable-pip-version-check",
                *wheels,
            ],
            cwd=self.root,
            home=environment,
            timeout=120,
        )
        self.assertEqual(0, install.returncode, _failure(install))
        check = _run(
            [binary, "-m", "pip", "check"],
            cwd=self.root,
            home=environment,
            timeout=60,
        )
        self.assertEqual(0, check.returncode, _failure(check))
        return environment, binary

    def _python(self, binary: Path, script: str, home: Path) -> subprocess.CompletedProcess[bytes]:
        return _run(
            [binary, "-I", "-c", script],
            cwd=self.root,
            home=home,
            timeout=60,
        )

    def test_wheel_metadata_declares_exact_dependency_and_modules(self) -> None:
        core_metadata, _core_names = _wheel_metadata(self.core_wheel)
        companion_metadata, companion_names = _wheel_metadata(self.companion_wheel)
        core_requirements = [
            line
            for line in core_metadata.splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
        companion_requirements = [
            line
            for line in companion_metadata.splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
        self.assertEqual([], core_requirements)
        self.assertEqual(
            ["Requires-Dist: mothership-control-plane==0.4.3.dev0"],
            companion_requirements,
        )
        for module in (
            "mothership_github/verification.py",
            "mothership_github/external_action.py",
            "mothership_github/executor.py",
        ):
            self.assertIn(module, companion_names)

    def test_core_only_environment_has_no_companion(self) -> None:
        environment, binary = self._environment("core-only", (self.core_wheel,))
        result = self._python(
            binary,
            """
import importlib
from pathlib import Path
import sysconfig

purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
for name in ("mothership", "orchestration"):
    module = importlib.import_module(name)
    origin = Path(module.__file__).resolve()
    assert purelib in origin.parents, (name, origin, purelib)
try:
    importlib.import_module("mothership_github")
except ModuleNotFoundError as error:
    assert error.name == "mothership_github", error
else:
    raise AssertionError("Core-only environment unexpectedly imported companion")
print("CORE_ONLY_NO_COMPANION")
""",
            environment,
        )
        self.assertEqual(0, result.returncode, _failure(result))
        self.assertIn(b"CORE_ONLY_NO_COMPANION", result.stdout)

    def test_pair_imports_core_and_companion_only_from_site_packages(self) -> None:
        environment, binary = self._environment(
            "pair-origins", (self.core_wheel, self.companion_wheel)
        )
        result = self._python(
            binary,
            """
import importlib
from pathlib import Path
import sysconfig

purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
for name in (
    "mothership",
    "orchestration",
    "mothership_github",
    "mothership_github.verification",
    "mothership_github.external_action",
    "mothership_github.executor",
):
    module = importlib.import_module(name)
    origin = Path(module.__file__).resolve()
    assert purelib in origin.parents, (name, origin, purelib)
print("WHEEL_IMPORT_ORIGINS_OK")
""",
            environment,
        )
        self.assertEqual(0, result.returncode, _failure(result))
        self.assertIn(b"WHEEL_IMPORT_ORIGINS_OK", result.stdout)

    def test_installed_pair_runs_copied_pipeline_and_verification_suites(self) -> None:
        environment, binary = self._environment(
            "pair-suites", (self.core_wheel, self.companion_wheel)
        )
        fixture = self.root / "copied-tests"
        fixture.mkdir()
        for name in ("test_pipeline.py", "test_verification.py"):
            shutil.copy2(PACKAGE_ROOT / "tests" / name, fixture / name)
        suite_script = """
import sys
import unittest

fixture, pattern = sys.argv[1:3]
suite = unittest.defaultTestLoader.discover(
    fixture,
    pattern=pattern,
    top_level_dir=fixture,
)
count = suite.countTestCases()
if count <= 0:
    raise SystemExit("copied suite discovered no tests")
result = unittest.TextTestRunner(verbosity=0).run(suite)
print(f"SUITE_COUNT={count}")
print(f"SKIPPED={len(result.skipped)}")
if not result.wasSuccessful() or result.skipped:
    raise SystemExit(1)
"""
        for name in ("test_pipeline.py", "test_verification.py"):
            with self.subTest(module=name):
                result = _run(
                    [
                        binary,
                        "-I",
                        "-c",
                        suite_script,
                        fixture,
                        name,
                    ],
                    cwd=self.root,
                    home=environment,
                    timeout=120,
                )
                self.assertEqual(0, result.returncode, _failure(result))
                marker = result.stdout.decode("utf-8", "replace").splitlines()
                count_line = next(line for line in marker if line.startswith("SUITE_COUNT="))
                skipped_line = next(line for line in marker if line.startswith("SKIPPED="))
                count = int(count_line.split("=", 1)[1])
                self.assertGreater(count, 0)
                self.assertEqual("SKIPPED=0", skipped_line)
                print(f"copied {name}: {count} tests, skipped=0")

    def test_installed_pair_cli_help_and_core_verify_demo_are_offline(self) -> None:
        environment, binary = self._environment(
            "pair-cli", (self.core_wheel, self.companion_wheel)
        )
        for script_name in ("mothership", "mothership-github"):
            with self.subTest(script=script_name):
                result = _run(
                    [binary, "-I", environment / "bin" / script_name, "--help"],
                    cwd=self.root,
                    home=environment,
                    timeout=60,
                )
                self.assertEqual(0, result.returncode, _failure(result))
                self.assertIn(b"usage:", result.stdout.lower())
        for command in ("verify", "demo"):
            with self.subTest(command=command):
                result = _run(
                    [binary, "-I", "-m", "mothership", command],
                    cwd=self.root,
                    home=environment,
                    timeout=60,
                )
                self.assertEqual(0, result.returncode, _failure(result))
                document = json.loads(result.stdout.decode("utf-8"))
                self.assertEqual("passed", document["status"])
                self.assertIs(False, document["authority_effect"])
                self.assertIs(False, document["execution_effect"])

    def test_missing_verification_module_cannot_fall_back_to_source(self) -> None:
        negative_source = self.root / "negative-companion-source"
        shutil.copytree(self.companion_source, negative_source, ignore=COPY_IGNORES)
        (negative_source / "mothership_github" / "verification.py").unlink()
        negative_wheel = self._build_wheel(negative_source, self.root / "negative-dist")
        environment, binary = self._environment(
            "negative-import", (self.core_wheel, negative_wheel)
        )
        result = _run(
            [
                binary,
                "-I",
                "-c",
                """
import importlib

try:
    importlib.import_module("mothership_github.verification")
except ModuleNotFoundError as error:
    if error.name != "mothership_github.verification":
        raise
    print("EXPECTED_MISSING_VERIFICATION")
    raise SystemExit(17)
else:
    raise AssertionError("verification module unexpectedly imported")
""",
            ],
            cwd=self.root,
            home=environment,
            timeout=60,
        )
        self.assertEqual(17, result.returncode, _failure(result))
        self.assertIn(b"EXPECTED_MISSING_VERIFICATION", result.stdout)
        combined = result.stdout + result.stderr
        self.assertNotIn(str(self.companion_source).encode(), combined)

if __name__ == "__main__":
    unittest.main()
