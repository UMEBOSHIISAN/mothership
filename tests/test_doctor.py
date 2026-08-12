from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from orchestration.lib.canonical import canonical_json_bytes


FIXTURE_ROOT = Path(tempfile.gettempdir()).resolve() / "mothership-doctor-tests"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_CLI = PACKAGE_ROOT / "orchestration" / "bin" / "llm-doctor"
WRAPPER = PACKAGE_ROOT / "bootstrap" / "doctor.sh"
ALIASES = ("claude-code-agent", "codex-cli", "ollama-local")
LIMITATIONS = [
    "authentication-external",
    "binary-trust-external",
    "managed-policy-external",
]
REQUIRED = {
    "codex-cli": (
        "-a", "--cd", "--color", "--ephemeral", "--ignore-rules",
        "--ignore-user-config", "--sandbox", "--skip-git-repo-check",
        "--strict-config", "-c",
    ),
    "claude-code-agent": (
        "--disable-slash-commands", "--mcp-config", "--no-chrome",
        "--no-session-persistence", "--output-format", "--permission-mode",
        "--print", "--safe-mode", "--strict-mcp-config", "--tools",
    ),
}
PROBES = {
    "codex-cli": (("codex", "--version"), ("codex", "exec", "--help")),
    "claude-code-agent": (("claude", "--version"), ("claude", "--help")),
    "ollama-local": (("ollama", "--version"), ("ollama", "list")),
}
_CF_USER_TEXT_ENCODING = re.compile(
    r"0x[0-9A-Fa-f]+:0x[0-9A-Fa-f]+:0x[0-9A-Fa-f]+"
)


class _Result:
    def __init__(self, returncode: int = 0, stdout: bytes | str = b"", stderr: bytes | str = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
        os.chmod(FIXTURE_ROOT, 0o700)
        self.temp = tempfile.TemporaryDirectory(dir=FIXTURE_ROOT)
        self.root = Path(self.temp.name)
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir(mode=0o700)
        (self.root / "tmp").mkdir(mode=0o700)
        self.record = self.root / "diagnostic-records.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()
        FIXTURE_ROOT.rmdir()

    def _scripted(self, responses: list[object]):
        transcript: list[tuple[str, ...]] = []

        def runner(argv: tuple[str, ...]):
            transcript.append(argv)
            response = responses[len(transcript) - 1]
            if isinstance(response, BaseException):
                raise response
            return response

        return transcript, runner

    def _parent_environment(self, fake_bin: Path) -> dict[str, str]:
        return {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "HOME": "/diagnostic-home",
            "TMPDIR": str(self.root / "tmp"),
            "LANG": "C",
            "LC_ALL": "C",
            "LC_CTYPE": "C",
            "LC_CUSTOM": "kept",
            "CODEX_HOME": "/must-not-pass",
            "FRIEND_MOTHERSHIP_CALL_DEPTH": "99",
            "SECRET": "must-not-pass",
            "HTTPS_PROXY": "must-not-pass",
            "PYTHONPATH": "must-not-pass",
            "BASH_FUNC_x%%": "must-not-pass",
            "__CF_USER_TEXT_ENCODING": "must-not-pass",
        }

    def _package_bytecode_artifacts(self) -> tuple[str, ...]:
        return tuple(sorted(
            path.relative_to(PACKAGE_ROOT).as_posix()
            for path in PACKAGE_ROOT.rglob("*")
            if path.name == "__pycache__" or path.suffix == ".pyc"
        ))

    def _assert_package_bytecode_unchanged(self, before: tuple[str, ...]) -> None:
        self.assertEqual(before, self._package_bytecode_artifacts())

    def _normalized_recorded_environment(self, value: object) -> dict[str, object]:
        self.assertIsInstance(value, dict)
        environment = dict(value)
        injected = environment.pop("__CF_USER_TEXT_ENCODING", None)
        if injected is not None:
            self.assertEqual("darwin", sys.platform)
            self.assertIsInstance(injected, str)
            self.assertIsNotNone(_CF_USER_TEXT_ENCODING.fullmatch(injected))
        return environment

    def _install_fake(self, name: str, detail_bytes: bytes) -> Path:
        detail_argv = {
            "claude": ["--help"],
            "codex": ["exec", "--help"],
            "ollama": ["list"],
        }[name]
        path = self.fake_bin / name
        source = f"""#!{sys.executable}
import json
import os
import sys

stdin_bytes = sys.stdin.buffer.read()
record = {{
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "env": dict(os.environ),
    "name": {name!r},
    "stdin_bytes": len(stdin_bytes),
}}
with open({str(self.record)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\\n")
if sys.argv[1:] == ["--version"]:
    sys.stdout.buffer.write({(name + " 1\n").encode("utf-8")!r})
    raise SystemExit(0)
if sys.argv[1:] == {detail_argv!r}:
    sys.stdout.buffer.write({detail_bytes!r})
    raise SystemExit(0)
raise SystemExit(9)
"""
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)
        return path

    def _read_records(self) -> list[dict[str, object]]:
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text("utf-8").splitlines()]

    def _expected_available_results(self) -> list[dict[str, object]]:
        binaries = {
            "claude-code-agent": "claude",
            "codex-cli": "codex",
            "ollama-local": "ollama",
        }
        results: list[dict[str, object]] = []
        for alias in ALIASES:
            results.append({
                "schema_version": "0.1.0",
                "adapter_id": alias,
                "status": "available",
                "required_flags": {
                    flag: True for flag in sorted(REQUIRED.get(alias, ()))
                },
                "local_model_present": True if alias == "ollama-local" else None,
                "version_sha256": hashlib.sha256(
                    f"{binaries[alias]} 1".encode("utf-8")
                ).hexdigest(),
                "limitations": list(LIMITATIONS),
                "authority_effect": "none",
            })
        return results

    def test_doctor_runs_only_fixed_diagnostics_and_returns_closed_available_result(self) -> None:
        # Issuing a model command, changing tuple order, or adding output fields must fail this.
        from orchestration.lib.adapters import doctor_adapter

        cases = {
            "codex-cli": (PROBES["codex-cli"][0], PROBES["codex-cli"][1], b"codex 1\n", b"-a --ignore-user-config --ignore-rules --strict-config -c --ephemeral --sandbox --skip-git-repo-check --cd --color"),
            "claude-code-agent": (PROBES["claude-code-agent"][0], PROBES["claude-code-agent"][1], b"claude 1\n", b"--print --safe-mode --tools --permission-mode --no-session-persistence --no-chrome --disable-slash-commands --strict-mcp-config --mcp-config --output-format"),
            "ollama-local": (("ollama", "--version"), ("ollama", "list"), b"ollama 1\n", b"NAME ID SIZE\nfriend-core-advisory abc\n"),
        }
        for alias, (version, help_command, raw_version, raw_help) in cases.items():
            transcript: list[tuple[str, ...]] = []
            def runner(argv: tuple[str, ...]) -> _Result:
                transcript.append(argv)
                return _Result(stdout=raw_version if argv == version else raw_help)
            with self.subTest(alias=alias):
                result = doctor_adapter(alias, runner)
                self.assertEqual([version, help_command], transcript)
                self.assertEqual(
                    {"schema_version", "adapter_id", "status", "required_flags", "local_model_present", "version_sha256", "limitations", "authority_effect"},
                    set(result),
                )
                self.assertEqual("available", result["status"])
                self.assertEqual(hashlib.sha256(raw_version.strip()).hexdigest(), result["version_sha256"])
                self.assertEqual(LIMITATIONS, result["limitations"])
                self.assertEqual("none", result["authority_effect"])

    def test_doctor_fails_closed_without_a_third_call(self) -> None:
        # Retrying a failed probe or treating malformed/invalid output as available must fail this.
        from orchestration.lib.adapters import doctor_adapter

        for alias, version in (("codex-cli", ("codex", "--version")), ("claude-code-agent", ("claude", "--version")), ("ollama-local", ("ollama", "--version"))):
            transcript: list[tuple[str, ...]] = []
            def bad_version(argv: tuple[str, ...]) -> _Result:
                transcript.append(argv)
                return _Result(returncode=1, stderr=b"missing")
            with self.subTest(alias=alias, branch="version"):
                result = doctor_adapter(alias, bad_version)
                self.assertEqual([version], transcript)
                self.assertEqual("unavailable", result["status"])
                self.assertIsNone(result["version_sha256"])
        transcript = []
        def missing_flag(argv: tuple[str, ...]) -> _Result:
            transcript.append(argv)
            return _Result(stdout=b"v" if len(transcript) == 1 else b"--print")
        result = doctor_adapter("claude-code-agent", missing_flag)
        self.assertEqual([("claude", "--version"), ("claude", "--help")], transcript)
        self.assertEqual("unavailable", result["status"])
        self.assertIsNotNone(result["version_sha256"])
        for alias in ("invalid", "", "codex-cli "):
            with self.subTest(alias=alias):
                with self.assertRaises(ValueError):
                    doctor_adapter(alias, lambda argv: _Result())

    def test_environment_policies_are_exact_and_parent_is_immutable(self) -> None:
        from orchestration.lib import adapters

        parent = self._parent_environment(self.root / "bin")
        before = dict(parent)
        adapter = adapters._sanitized_environment(parent, include_codex_home=True)
        self.assertEqual(
            {
                "PATH": parent["PATH"], "HOME": parent["HOME"],
                "TMPDIR": parent["TMPDIR"], "LANG": "C", "LC_ALL": "C",
                "LC_CTYPE": "C", "LC_CUSTOM": "kept",
                "CODEX_HOME": "/must-not-pass",
                "FRIEND_MOTHERSHIP_CALL_DEPTH": "1",
            },
            adapter,
        )
        diagnostic = adapters._diagnostic_environment(parent)
        self.assertEqual(
            {
                "PATH": parent["PATH"], "HOME": parent["HOME"],
                "TMPDIR": parent["TMPDIR"], "LANG": "C", "LC_ALL": "C",
                "LC_CTYPE": "C", "LC_CUSTOM": "kept",
            },
            diagnostic,
        )
        self.assertIsNot(diagnostic, parent)
        self.assertEqual(before, parent)
        for bad in (None, {"PATH": 1}, {1: "value"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    adapters._diagnostic_environment(bad)

    def test_required_help_options_are_exact_tokens_and_fail_independently(self) -> None:
        from orchestration.lib.adapters import doctor_adapter

        for alias in ("codex-cli", "claude-code-agent"):
            version_command, detail_command = PROBES[alias]
            flags = REQUIRED[alias]
            for removed in flags:
                detail = " ".join(
                    f"[{flag}=VALUE]," for flag in flags if flag != removed
                ).encode("utf-8")
                transcript, runner = self._scripted([
                    _Result(stdout=b"version\n"),
                    _Result(stdout=detail),
                ])
                with self.subTest(alias=alias, removed=removed):
                    result = doctor_adapter(alias, runner)
                    self.assertEqual([version_command, detail_command], transcript)
                    self.assertEqual("unavailable", result["status"])
                    self.assertFalse(result["required_flags"][removed])

            complete = " ".join(
                f"[{flag}=VALUE]," for flag in flags
            ).encode("utf-8")
            transcript, runner = self._scripted([
                _Result(stdout=b"version\n"),
                _Result(stdout=complete),
            ])
            with self.subTest(alias=alias, complete=True):
                result = doctor_adapter(alias, runner)
                self.assertEqual([version_command, detail_command], transcript)
                self.assertEqual("available", result["status"])
                self.assertTrue(all(result["required_flags"].values()))

    def test_every_runner_failure_branch_has_a_closed_transcript(self) -> None:
        from orchestration.lib.adapters import doctor_adapter

        closed_keys = {
            "schema_version", "adapter_id", "status", "required_flags",
            "local_model_present", "version_sha256", "limitations",
            "authority_effect",
        }
        version_failures = [
            RuntimeError("version"),
            object(),
            _Result(returncode=1, stderr=b"bad"),
            _Result(stdout=b" \t\r\n"),
        ]
        detail_failures = [
            RuntimeError("detail"),
            object(),
            _Result(returncode=1, stderr=b"bad"),
            _Result(stdout=b"\xff"),
        ]
        for alias, (version_command, detail_command) in PROBES.items():
            for index, response in enumerate(version_failures):
                transcript, runner = self._scripted([response])
                with self.subTest(alias=alias, branch="version", case=index):
                    result = doctor_adapter(alias, runner)
                    self.assertEqual([version_command], transcript)
                    self.assertEqual(closed_keys, set(result))
                    self.assertEqual("unavailable", result["status"])
                    self.assertIsNone(result["version_sha256"])
                    self.assertEqual(LIMITATIONS, result["limitations"])
                    self.assertEqual("none", result["authority_effect"])
            for index, response in enumerate(detail_failures):
                transcript, runner = self._scripted([
                    _Result(stdout=b"version\n"),
                    response,
                ])
                with self.subTest(alias=alias, branch="detail", case=index):
                    result = doctor_adapter(alias, runner)
                    self.assertEqual([version_command, detail_command], transcript)
                    self.assertEqual(closed_keys, set(result))
                    self.assertEqual("unavailable", result["status"])
                    self.assertEqual(
                        hashlib.sha256(b"version").hexdigest(),
                        result["version_sha256"],
                    )
                    self.assertEqual(LIMITATIONS, result["limitations"])
                    self.assertEqual("none", result["authority_effect"])

    def test_ollama_requires_exact_first_column_model_alias(self) -> None:
        from orchestration.lib.adapters import doctor_adapter

        cases = (
            (b"NAME ID SIZE\nfriend-core-advisory abc 1GB\n", True),
            (b"friend-core-advisory:latest abc 1GB\n", False),
            (b"friend-core-advisory-extra abc 1GB\n", False),
            (b"other friend-core-advisory 1GB\n", False),
        )
        for detail, expected in cases:
            transcript, runner = self._scripted([
                _Result(stdout=b"ollama 1\n"),
                _Result(stdout=detail),
            ])
            with self.subTest(detail=detail):
                result = doctor_adapter("ollama-local", runner)
                self.assertEqual(list(PROBES["ollama-local"]), transcript)
                self.assertIs(expected, result["local_model_present"])
                self.assertEqual("available" if expected else "unavailable", result["status"])

    def test_cli_records_exact_diagnostic_process_boundary(self) -> None:
        self._install_fake(
            "claude",
            " ".join(f"[{flag}=VALUE]," for flag in REQUIRED["claude-code-agent"]).encode("utf-8"),
        )
        self._install_fake(
            "codex",
            " ".join(f"[{flag}=VALUE]," for flag in REQUIRED["codex-cli"]).encode("utf-8"),
        )
        self._install_fake("ollama", b"NAME ID SIZE\nfriend-core-advisory abc 1GB\n")
        parent = self._parent_environment(self.fake_bin)
        before = dict(parent)
        bytecode_before = self._package_bytecode_artifacts()
        completed = subprocess.run(
            [sys.executable, "-B", str(DOCTOR_CLI)],
            shell=False,
            cwd=self.root,
            env=dict(parent),
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self._assert_package_bytecode_unchanged(bytecode_before)
        self.assertEqual(0, completed.returncode)
        self.assertEqual(b"", completed.stderr)
        self.assertEqual(before, parent)
        self.assertEqual(
            canonical_json_bytes(self._expected_available_results()) + b"\n",
            completed.stdout,
        )
        records = self._read_records()
        self.assertEqual(
            [
                ("claude", ("--version",)),
                ("claude", ("--help",)),
                ("codex", ("--version",)),
                ("codex", ("exec", "--help")),
                ("ollama", ("--version",)),
                ("ollama", ("list",)),
            ],
            [(record["name"], tuple(record["argv"])) for record in records],
        )
        self.assertEqual(["/"] * 6, [record["cwd"] for record in records])
        self.assertEqual([0] * 6, [record["stdin_bytes"] for record in records])
        expected_env = {
            "PATH": parent["PATH"],
            "HOME": parent["HOME"],
            "TMPDIR": parent["TMPDIR"],
            "LANG": "C",
            "LC_ALL": "C",
            "LC_CTYPE": "C",
            "LC_CUSTOM": "kept",
        }
        self.assertEqual(
            [expected_env] * 6,
            [self._normalized_recorded_environment(record["env"]) for record in records],
        )

    def test_cli_fails_closed_before_or_after_fixed_probes(self) -> None:
        parent = self._parent_environment(self.fake_bin)
        invalid_cases = (
            ["invalid"],
            ["codex-cli", "codex-cli"],
        )
        for arguments in invalid_cases:
            with self.subTest(arguments=arguments):
                bytecode_before = self._package_bytecode_artifacts()
                completed = subprocess.run(
                    [sys.executable, "-B", str(DOCTOR_CLI), *arguments],
                    shell=False,
                    cwd=self.root,
                    env=dict(parent),
                    input=b"",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self._assert_package_bytecode_unchanged(bytecode_before)
                self.assertEqual(2, completed.returncode)
                self.assertEqual(b"", completed.stdout)
                self.assertEqual(b"", completed.stderr)
                self.assertEqual([], self._read_records())

        missing_safe_mode = " ".join(
            f"[{flag}=VALUE],"
            for flag in REQUIRED["claude-code-agent"]
            if flag != "--safe-mode"
        ).encode("utf-8")
        self._install_fake("claude", missing_safe_mode)
        bytecode_before = self._package_bytecode_artifacts()
        completed = subprocess.run(
            [sys.executable, "-B", str(DOCTOR_CLI), "claude-code-agent"],
            shell=False,
            cwd=self.root,
            env=dict(parent),
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self._assert_package_bytecode_unchanged(bytecode_before)
        expected = dict(self._expected_available_results()[0])
        expected["status"] = "unavailable"
        expected["required_flags"] = dict(expected["required_flags"])
        expected["required_flags"]["--safe-mode"] = False
        self.assertEqual(2, completed.returncode)
        self.assertEqual(b"", completed.stderr)
        self.assertEqual(canonical_json_bytes([expected]) + b"\n", completed.stdout)
        records = self._read_records()
        self.assertEqual(
            [("claude", ("--version",)), ("claude", ("--help",))],
            [(record["name"], tuple(record["argv"])) for record in records],
        )

    def test_wrapper_resolves_once_and_rejects_unsafe_surfaces(self) -> None:
        counter = 0

        def package_fixture(name: str | None = None):
            nonlocal counter
            counter += 1
            package = self.root / (name if name is not None else f"package-{counter}")
            wrapper = package / "bootstrap" / "doctor.sh"
            doctor = package / "orchestration" / "bin" / "llm-doctor"
            wrapper.parent.mkdir(parents=True)
            doctor.parent.mkdir(parents=True)
            shutil.copyfile(WRAPPER, wrapper)
            wrapper.chmod(0o755)
            record = package / "wrapper-records.jsonl"
            doctor.write_text(
                f"""#!{sys.executable}
import json
import sys
with open({str(record)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"argv": sys.argv[1:]}}, sort_keys=True, separators=(",", ":")) + "\\n")
""",
                encoding="utf-8",
            )
            doctor.chmod(0o755)
            return package, wrapper, doctor, record

        def records(path: Path) -> list[dict[str, object]]:
            if not path.exists():
                return []
            return [json.loads(line) for line in path.read_text("utf-8").splitlines()]

        def invoke(argv: list[str], cwd: Path, path: Path | None = None):
            environment = {
                "PATH": f"{path}:/usr/bin:/bin" if path is not None else "/usr/bin:/bin",
                "HOME": str(self.root),
                "TMPDIR": str(self.root / "tmp"),
                "LANG": "C",
            }
            return subprocess.run(
                argv,
                shell=False,
                cwd=cwd,
                env=environment,
                input=b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        package, wrapper, _, record = package_fixture()
        self.assertEqual(WRAPPER.read_bytes(), wrapper.read_bytes())
        direct = invoke([str(wrapper), "direct", "one"], self.root)
        relative = invoke(["./bootstrap/doctor.sh", "relative"], package)
        through_path = invoke(["doctor.sh", "path", "two"], self.root, wrapper.parent)
        for completed in (direct, relative, through_path):
            self.assertEqual(0, completed.returncode)
            self.assertEqual(b"", completed.stdout)
            self.assertEqual(b"", completed.stderr)
        self.assertEqual(
            [
                {"argv": ["direct", "one"]},
                {"argv": ["relative"]},
                {"argv": ["path", "two"]},
            ],
            records(record),
        )

        package, wrapper, _, record = package_fixture()
        self.assertEqual(WRAPPER.read_bytes(), wrapper.read_bytes())
        wrapper_link = self.root / "wrapper-link"
        wrapper_link.symlink_to(wrapper)
        completed = invoke([str(wrapper_link), "blocked"], self.root)
        self.assertEqual(2, completed.returncode)
        self.assertEqual([], records(record))

        package, wrapper, doctor, record = package_fixture()
        self.assertEqual(WRAPPER.read_bytes(), wrapper.read_bytes())
        real_doctor = doctor.with_name("real-doctor")
        shutil.copyfile(doctor, real_doctor)
        real_doctor.chmod(0o755)
        doctor.unlink()
        doctor.symlink_to(real_doctor.name)
        completed = invoke([str(wrapper), "blocked"], self.root)
        self.assertEqual(2, completed.returncode)
        self.assertEqual([], records(record))

        package, wrapper, doctor, record = package_fixture()
        self.assertEqual(WRAPPER.read_bytes(), wrapper.read_bytes())
        doctor.unlink()
        doctor.mkdir()
        completed = invoke([str(wrapper), "blocked"], self.root)
        self.assertEqual(2, completed.returncode)
        self.assertEqual([], records(record))

        package, wrapper, doctor, record = package_fixture()
        self.assertEqual(WRAPPER.read_bytes(), wrapper.read_bytes())
        doctor.chmod(0o644)
        completed = invoke([str(wrapper), "blocked"], self.root)
        self.assertEqual(2, completed.returncode)
        self.assertEqual([], records(record))

        package, wrapper, _, record = package_fixture("newline\npackage")
        self.assertEqual(WRAPPER.read_bytes(), wrapper.read_bytes())
        completed = invoke([str(wrapper), "blocked"], self.root)
        self.assertEqual(2, completed.returncode)
        self.assertEqual([], records(record))


if __name__ == "__main__":
    unittest.main()
