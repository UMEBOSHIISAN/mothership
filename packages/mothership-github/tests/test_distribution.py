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
ADAPTERS_ROOT = REPOSITORY_ROOT / "packages" / "mothership-adapters"
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
    input_bytes: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(argument) for argument in argv],
        cwd=cwd,
        env=_environment(home),
        input=input_bytes,
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
        cls.source_snapshot = cls.root / "source-snapshot"
        shutil.copytree(REPOSITORY_ROOT, cls.source_snapshot, ignore=COPY_IGNORES)
        cls.core_source = cls.source_snapshot
        cls.companion_source = cls.source_snapshot / "packages" / "mothership-github"
        cls.adapters_source = cls.source_snapshot / "packages" / "mothership-adapters"
        cls.core_dist = cls.root / "core-dist"
        cls.companion_dist = cls.root / "companion-dist"
        cls.adapter_dist = cls.root / "adapter-dist"
        cls.core_wheel = cls._build_wheel(cls.core_source, cls.core_dist)
        cls.companion_wheel = cls._build_wheel(cls.companion_source, cls.companion_dist)
        cls.adapter_wheel = cls._build_wheel(cls.adapters_source, cls.adapter_dist)

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
            ["Requires-Dist: mothership-control-plane==0.5.0.dev0"],
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
import importlib.util
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
        for name in ("test_pipeline.py", "test_verification.py", "test_process_boundaries.py"):
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
        for name in ("test_pipeline.py", "test_verification.py", "test_process_boundaries.py"):
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

    def test_three_wheel_metadata_and_imports_are_site_package_only(self) -> None:
        adapter_metadata, adapter_names = _wheel_metadata(self.adapter_wheel)
        adapter_requirements = [
            line
            for line in adapter_metadata.splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
        self.assertEqual(
            [
                "Requires-Dist: mothership-control-plane==0.5.0.dev0",
                "Requires-Dist: mothership-github==0.3.0.dev0",
            ],
            adapter_requirements,
        )
        for module in (
            "mothership_adapters/cli.py",
            "mothership_adapters/saved_result.py",
        ):
            self.assertIn(module, adapter_names)

        environment, binary = self._environment(
            "three-wheel-origins",
            (self.core_wheel, self.companion_wheel, self.adapter_wheel),
        )
        result = self._python(
            binary,
            """
import importlib
from pathlib import Path
import sysconfig
from orchestration.lib import contracts

purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
for name in (
    "mothership",
    "orchestration",
    "mothership_github",
    "mothership_github.verification",
    "mothership_adapters",
    "mothership_adapters.cli",
    "mothership_adapters.saved_result",
):
    module = importlib.import_module(name)
    origin = Path(module.__file__).resolve()
    assert purelib in origin.parents, (name, origin, purelib)
for kind, schema_path in contracts._SCHEMAS.items():
    resource = Path(schema_path).resolve()
    assert purelib in resource.parents and resource.is_file(), (kind, resource, purelib)
print("THREE_WHEEL_IMPORT_ORIGINS_OK")
""",
            environment,
        )
        self.assertEqual(0, result.returncode, _failure(result))
        self.assertIn(b"THREE_WHEEL_IMPORT_ORIGINS_OK", result.stdout)

    def test_installed_reader_matches_source_for_original_six_cases(self) -> None:
        environment, binary = self._environment(
            "three-wheel-six-cases",
            (self.core_wheel, self.companion_wheel, self.adapter_wheel),
        )
        cases_root = REPOSITORY_ROOT / "examples" / "saved-results"
        names = tuple(f"case-{number:02d}.jsonl" for number in range(1, 7))
        self.assertEqual(
            names,
            tuple(path.name for path in sorted(cases_root.glob("case-*.jsonl"))),
        )
        expected_statuses = {
            "case-01.jsonl": ("success", "SUCCESS", "CONFIRMED"),
            "case-02.jsonl": ("success", None, None),
            "case-03.jsonl": ("success", "SUCCESS", "UNKNOWN"),
            "case-04.jsonl": (None, None, None),
            "case-05.jsonl": ("reconciliation_required", None, None),
        }
        for name in names:
            path = cases_root / name
            raw = path.read_bytes()
            before = bytes(raw)
            for args in (("inspect-result",), ("inspect-result", "--human")):
                with self.subTest(case=name, mode="human" if len(args) == 2 else "json"):
                    source = self._source_cli(binary, environment, args, raw)
                    installed = self._installed_cli(binary, environment, args, raw)
                    self.assertEqual(source.returncode, installed.returncode, _failure(installed))
                    self.assertEqual(source.stdout, installed.stdout, _failure(installed))
                    self.assertEqual(source.stderr, installed.stderr, _failure(installed))
                    if name == "case-06.jsonl":
                        self.assertEqual(2, installed.returncode, _failure(installed))
                        self.assertEqual(b"", installed.stdout)
                        self.assertEqual(b"invalid bounded evidence input\n", installed.stderr)
                    elif args == ("inspect-result",):
                        self.assertEqual(0, installed.returncode, _failure(installed))
                        view = json.loads(installed.stdout.decode("utf-8"))
                        self.assertEqual(
                            expected_statuses[name],
                            (
                                view["execution_status"],
                                view["receipt_status"],
                                view["verification_status"],
                            ),
                        )
            self.assertEqual(before, raw)
            self.assertEqual(before, path.read_bytes())

    def test_installed_saved_result_suite_covers_v1_and_expected_action_guards(self) -> None:
        environment, binary = self._environment(
            "three-wheel-saved-result-suite",
            (self.core_wheel, self.companion_wheel, self.adapter_wheel),
        )
        fixture_root = self.root / "installed-saved-result-fixture"
        test_root = fixture_root / "packages" / "mothership-adapters" / "tests"
        test_root.mkdir(parents=True)
        for name in ("test_cli.py", "test_evidence.py"):
            shutil.copy2(ADAPTERS_ROOT / "tests" / name, test_root / name)
        examples_root = fixture_root / "examples"
        examples_root.mkdir()
        shutil.copytree(
            REPOSITORY_ROOT / "examples" / "saved-results",
            examples_root / "saved-results",
            ignore=COPY_IGNORES,
        )
        suite_script = """
import sys
import unittest

fixture_root, test_root = sys.argv[1:3]
sys.path[:0] = [test_root, fixture_root]
suite = unittest.defaultTestLoader.loadTestsFromName("test_cli.SavedResultCLITests")
suite = unittest.TestSuite(
    # These source-layout/example-producer cases are covered by their source
    # suite; installed-package provenance is covered by the origin test above,
    # and the guarded installed CLI test below covers no paths or effects.
    test
    for test in suite
    if not any(test.id().endswith(suffix) for suffix in (
        "test_no_implicit_paths_authority_network_or_input_mutation",
        "test_real_consumer_saved_file_round_trip_is_offline_and_unchanged",
        "test_actual_missing_finish_save_remains_unknown_without_reading_ledger",
    ))
)
count = suite.countTestCases()
if count <= 0:
    raise SystemExit("saved-result suite discovered no tests")
result = unittest.TextTestRunner(verbosity=0).run(suite)
print(f"SAVED_RESULT_SUITE_COUNT={count}")
print("EXCLUDED_SOURCE_LAYOUT_AND_EXAMPLE_PRODUCER_TESTS=3")
print(f"SKIPPED={len(result.skipped)}")
if not result.wasSuccessful() or result.skipped:
    raise SystemExit(1)
"""
        result = _run(
            [binary, "-I", "-c", suite_script, fixture_root, test_root],
            cwd=self.root,
            home=environment,
            timeout=180,
        )
        self.assertEqual(0, result.returncode, _failure(result))
        self.assertIn(b"SAVED_RESULT_SUITE_COUNT=", result.stdout)
        self.assertIn(b"EXCLUDED_SOURCE_LAYOUT_AND_EXAMPLE_PRODUCER_TESTS=3", result.stdout)
        self.assertIn(b"SKIPPED=0", result.stdout)

    def test_installed_cli_reads_saved_result_without_network_or_authority_effects(self) -> None:
        environment, binary = self._environment(
            "three-wheel-controlled-cli",
            (self.core_wheel, self.companion_wheel, self.adapter_wheel),
        )
        fixture_path = REPOSITORY_ROOT / "examples" / "saved-results" / "case-01.jsonl"
        original_raw = fixture_path.read_bytes()
        sentinel_root = self.root / "reader-ledger-sentinels"
        sentinel_root.mkdir()
        sentinel_paths = {
            "authority": sentinel_root / "authority.jsonl",
            "attempts": sentinel_root / "attempts.jsonl",
        }
        sentinel_contents = {
            sentinel_paths["authority"]: b"AUTHORITY_SENTINEL\n",
            sentinel_paths["attempts"]: b"ATTEMPTS_SENTINEL\n",
        }
        for path, contents in sentinel_contents.items():
            path.write_bytes(contents)
        before_sentinels = {path: path.read_bytes() for path in sentinel_contents}
        raw = original_raw.replace(
            b"/not-to-open/authority.jsonl", os.fsencode(sentinel_paths["authority"])
        ).replace(
            b"/not-to-open/attempts.jsonl", os.fsencode(sentinel_paths["attempts"])
        )
        script = """
import builtins
import io
import os
from pathlib import Path
import socket
import sys
import sysconfig

from mothership_adapters.cli import main
from mothership_adapters import saved_result  # force installed module import before guards
import mothership_github.executor as executor
import orchestration.lib.action_authority as authority
import orchestration.lib.action_authority_ledger as ledger

def forbidden(*_args, **_kwargs):
    raise AssertionError("reader attempted a live or authority operation")

socket.socket = forbidden
authority.freeze_action = forbidden
ledger.consume_action = forbidden
executor.execute_action_merge_pr = forbidden
purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
sentinel_paths = tuple(Path(value).resolve() for value in sys.argv[1:3])
assert len(sentinel_paths) == 2, sentinel_paths
real_os_open = os.open
real_os_fdopen = os.fdopen
real_builtin_open = builtins.open
real_io_open = io.open
real_path_open = Path.open
real_path_read_bytes = Path.read_bytes
real_path_write_bytes = Path.write_bytes
real_path_read_text = Path.read_text
real_path_write_text = Path.write_text

def raw_bytes(path):
    descriptor = real_os_open(path, os.O_RDONLY)
    try:
        chunks = []
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                return b"".join(chunks)
            chunks.append(block)
    finally:
        os.close(descriptor)

before_sentinels = {path: raw_bytes(path) for path in sentinel_paths}

def mode_writes(mode):
    return type(mode) is not str or any(flag in mode for flag in "wax+")

def guard_path(path, mode):
    if mode_writes(mode):
        raise AssertionError(f"reader opened a path for writing: {path!r}, mode={mode!r}")
    if isinstance(path, int):
        return
    target = Path(path).resolve()
    if purelib not in target.parents:
        raise AssertionError(f"reader opened an input path: {target}")

def guarded_open(path, flags, *args, **kwargs):
    write_flags = (
        os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND |
        getattr(os, "O_EXCL", 0) | getattr(os, "O_TMPFILE", 0)
    )
    if flags & write_flags:
        raise AssertionError(f"reader opened a path for writing: {path!r}, flags={flags}")
    target = Path(path).resolve()
    if purelib not in target.parents:
        raise AssertionError(f"reader opened an input path: {target}")
    return real_os_open(path, flags, *args, **kwargs)

def guarded_fdopen(descriptor, mode="r", *args, **kwargs):
    if mode_writes(mode):
        raise AssertionError(f"reader opened a descriptor for writing: mode={mode!r}")
    return real_os_fdopen(descriptor, mode, *args, **kwargs)

def guarded_builtin_open(path, mode="r", *args, **kwargs):
    guard_path(path, mode)
    return real_builtin_open(path, mode, *args, **kwargs)

def guarded_io_open(path, mode="r", *args, **kwargs):
    guard_path(path, mode)
    return real_io_open(path, mode, *args, **kwargs)

def guarded_path_open(path, mode="r", *args, **kwargs):
    guard_path(path, mode)
    return real_path_open(path, mode, *args, **kwargs)

def guarded_path_read_bytes(path):
    guard_path(path, "rb")
    return real_path_read_bytes(path)

def guarded_path_write_bytes(path, data):
    guard_path(path, "wb")
    return real_path_write_bytes(path, data)

def guarded_path_read_text(path, *args, **kwargs):
    guard_path(path, "r")
    return real_path_read_text(path, *args, **kwargs)

def guarded_path_write_text(path, data, *args, **kwargs):
    guard_path(path, "w")
    return real_path_write_text(path, data, *args, **kwargs)

os.open = guarded_open
os.fdopen = guarded_fdopen
builtins.open = guarded_builtin_open
io.open = guarded_io_open
Path.open = guarded_path_open
Path.read_bytes = guarded_path_read_bytes
Path.write_bytes = guarded_path_write_bytes
Path.read_text = guarded_path_read_text
Path.write_text = guarded_path_write_text

def expect_rejected(label, operation):
    try:
        operation()
    except AssertionError:
        return
    raise AssertionError(f"{label} unexpectedly accessed a sentinel")

read_probes = (
    ("builtins.open", lambda: builtins.open(sentinel_paths[0], "rb")),
    ("io.open", lambda: io.open(sentinel_paths[0], "rb")),
    ("Path.open", lambda: sentinel_paths[0].open("rb")),
    ("Path.read_bytes", lambda: sentinel_paths[0].read_bytes()),
    ("Path.read_text", lambda: sentinel_paths[0].read_text()),
    ("os.open", lambda: os.open(sentinel_paths[0], os.O_RDONLY)),
)
write_probes = (
    ("builtins.open", lambda: builtins.open(sentinel_paths[1], "wb")),
    ("io.open", lambda: io.open(sentinel_paths[1], "wb")),
    ("Path.open", lambda: sentinel_paths[1].open("wb")),
    ("Path.write_bytes", lambda: sentinel_paths[1].write_bytes(b"MUTATED")),
    ("Path.write_text", lambda: sentinel_paths[1].write_text("MUTATED")),
    ("os.open", lambda: os.open(sentinel_paths[1], os.O_WRONLY | os.O_CREAT)),
)
for label, operation in (*read_probes, *write_probes):
    expect_rejected(label, operation)
read_fd, write_fd = os.pipe()
os.close(write_fd)
reader = os.fdopen(read_fd, "rb")
reader.close()
unused_read_fd, write_fd = os.pipe()
os.close(unused_read_fd)
expect_rejected("os.fdopen", lambda: os.fdopen(write_fd, "wb"))
os.close(write_fd)
assert before_sentinels == {path: raw_bytes(path) for path in sentinel_paths}

raise SystemExit(main(["inspect-result", "--human"]))
"""
        result = _run(
            [binary, "-I", "-c", script, sentinel_paths["authority"], sentinel_paths["attempts"]],
            cwd=self.root,
            home=environment,
            timeout=60,
            input_bytes=raw,
        )
        self.assertEqual(0, result.returncode, _failure(result))
        self.assertIn(b"verification: CONFIRMED", result.stdout)
        self.assertEqual(b"", result.stderr)
        self.assertNotIn(str(self.source_snapshot).encode(), result.stdout + result.stderr)
        self.assertEqual(
            original_raw,
            fixture_path.read_bytes(),
        )
        self.assertEqual(
            before_sentinels,
            {path: path.read_bytes() for path in sentinel_contents},
        )

    def test_missing_saved_result_module_cannot_fall_back_to_source(self) -> None:
        negative_source = self.root / "negative-adapter-source"
        shutil.copytree(self.adapters_source, negative_source, ignore=COPY_IGNORES)
        (negative_source / "mothership_adapters" / "saved_result.py").unlink()
        negative_wheel = self._build_wheel(negative_source, self.root / "negative-adapter-dist")
        metadata, names = _wheel_metadata(negative_wheel)
        self.assertNotIn("mothership_adapters/saved_result.py", names)
        self.assertIn("Name: mothership-adapters", metadata)
        environment, binary = self._environment(
            "negative-adapter-import",
            (self.core_wheel, self.companion_wheel, negative_wheel),
        )
        result = _run(
            [
                binary,
                "-I",
                environment / "bin" / "mothership-evidence",
                "inspect-result",
                "--human",
            ],
            cwd=self.root,
            home=environment,
            timeout=60,
            input_bytes=b"{}\n",
        )
        self.assertNotEqual(0, result.returncode, _failure(result))
        self.assertIn(b"No module named 'mothership_adapters.saved_result'", result.stderr)
        combined = result.stdout + result.stderr
        self.assertNotIn(str(self.source_snapshot).encode(), combined)
        self.assertNotIn(str(self.adapters_source).encode(), combined)

    def _installed_cli(
        self,
        binary: Path,
        environment: Path,
        args: tuple[str, ...],
        raw: bytes,
    ) -> subprocess.CompletedProcess[bytes]:
        return _run(
            [binary, "-I", environment / "bin" / "mothership-evidence", *args],
            cwd=self.root,
            home=environment,
            timeout=60,
            input_bytes=raw,
        )

    def _source_cli(
        self,
        binary: Path,
        environment: Path,
        args: tuple[str, ...],
        raw: bytes,
    ) -> subprocess.CompletedProcess[bytes]:
        script = """
import sys

core_source, companion_source, adapters_source = sys.argv[1:4]
sys.path[:0] = [adapters_source, companion_source, core_source]
from mothership_adapters.cli import main

raise SystemExit(main(sys.argv[4:]))
"""
        return _run(
            [
                binary,
                "-I",
                "-c",
                script,
                self.core_source,
                self.companion_source,
                self.adapters_source,
                *args,
            ],
            cwd=self.root,
            home=environment,
            timeout=60,
            input_bytes=raw,
        )

if __name__ == "__main__":
    unittest.main()
