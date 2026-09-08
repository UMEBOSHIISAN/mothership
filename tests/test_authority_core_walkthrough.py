from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryFile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WALKTHROUGH = ROOT / "examples/authority_core_walkthrough.py"
GUARDED_CHILD_BOOTSTRAP = """\
import os
import sys
def install_audit_guard(write, fd, watched_events):
    def audit(event, _args, write=write, fd=fd, watched_events=watched_events):
        if event in watched_events:
            write(fd, (event + "\\n").encode("ascii"))
            raise RuntimeError("walkthrough socket attempt blocked")
    sys.addaudithook(audit)
install_audit_guard(
    os.write,
    int(os.environ["MOTHERSHIP_AUDIT_FD"]),
    {"socket.__new__", "socket.getaddrinfo"},
)
exec(compile(sys.argv[1], "<guarded>", "exec"), {"__name__": "__main__"})
"""
REAL_WALKTHROUGH_SOURCE = (
    f"import runpy\nrunpy.run_path({str(WALKTHROUGH)!r}, run_name='__main__')"
)
SOCKET_SOURCE = "import socket\nsocket.socket()"
GETADDRINFO_SOURCE = 'import socket\nsocket.getaddrinfo("example.invalid", 443)'
SWALLOWED_SOCKET_SOURCE = """\
import socket
try:
    socket.socket()
except RuntimeError:
    pass
"""
SSL_SOCKET_SOURCE = """\
import unittest.mock
import ssl
ssl.socket()
"""
ATEXIT_SOCKET_SOURCE = """\
import atexit
import socket
def create_socket_at_exit():
    socket.socket()
atexit.register(create_socket_at_exit)
"""
ATEXIT_SWALLOWED_SOCKET_SOURCE = """\
import atexit
import socket
def create_socket_at_exit():
    try:
        socket.socket()
    except RuntimeError:
        pass
atexit.register(create_socket_at_exit)
"""
IMPORT_ONLY_SSL_SOURCE = "import ssl"
IMPORT_ONLY_HTTP_CLIENT_SOURCE = "import http.client"
IMPORT_ONLY_UNITTEST_MOCK_SOURCE = "import unittest.mock"
NOOP_SOURCE = "pass"


@dataclass(frozen=True)
class GuardedResult:
    completed: subprocess.CompletedProcess[str]
    audit_events: tuple[str, ...]


class AuthorityCoreWalkthroughTests(unittest.TestCase):
    def _run_guarded(self, source: str) -> GuardedResult:
        environment = {
            "HOME": str(ROOT / ".test-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "7",
        }
        with TemporaryFile(mode="w+b") as evidence:
            environment["MOTHERSHIP_AUDIT_FD"] = str(evidence.fileno())
            completed = subprocess.run(
                [sys.executable, "-c", GUARDED_CHILD_BOOTSTRAP, source],
                cwd=ROOT,
                env=environment,
                pass_fds=(evidence.fileno(),),
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            evidence.seek(0)
            audit_events = tuple(
                line.decode("ascii")
                for line in evidence.read().splitlines()
                if line
            )
        return GuardedResult(completed, audit_events)

    def test_walkthrough_is_offline_and_rejects_replay(self) -> None:
        environment = {
            "HOME": str(ROOT / ".test-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "7",
        }
        completed = subprocess.run(
            [sys.executable, str(WALKTHROUGH)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertIn("操作を固定", completed.stdout)
        self.assertIn("合成した承認記録", completed.stdout)
        self.assertIn("人間の承認ではありません", completed.stdout)
        self.assertIn("consume: 成功", completed.stdout)
        self.assertIn("replay: 拒否", completed.stdout)
        self.assertIn("外部通信: なし", completed.stdout)
        self.assertIn("外部操作: なし", completed.stdout)

    def test_guarded_walkthrough_is_offline(self) -> None:
        result = self._run_guarded(REAL_WALKTHROUGH_SOURCE)
        completed = result.completed

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual((), result.audit_events)
        self.assertEqual("", completed.stderr)
        self.assertIn("操作を固定", completed.stdout)
        self.assertIn("合成した承認記録", completed.stdout)
        self.assertIn("人間の承認ではありません", completed.stdout)
        self.assertIn("consume: 成功", completed.stdout)
        self.assertIn("replay: 拒否", completed.stdout)
        self.assertIn("外部通信: なし", completed.stdout)
        self.assertIn("外部操作: なし", completed.stdout)

    def test_socket_constructor_is_rejected(self) -> None:
        result = self._run_guarded(SOCKET_SOURCE)

        self.assertNotEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual(("socket.__new__",), result.audit_events)

    def test_getaddrinfo_is_rejected(self) -> None:
        result = self._run_guarded(GETADDRINFO_SOURCE)

        self.assertNotEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual(("socket.getaddrinfo",), result.audit_events)

    def test_swallowed_socket_failure_is_still_rejected(self) -> None:
        result = self._run_guarded(SWALLOWED_SOCKET_SOURCE)

        self.assertEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual(("socket.__new__",), result.audit_events)

    def test_ssl_socket_alias_is_rejected(self) -> None:
        result = self._run_guarded(SSL_SOCKET_SOURCE)

        self.assertNotEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual(("socket.__new__",), result.audit_events)

    def test_atexit_socket_is_rejected(self) -> None:
        result = self._run_guarded(ATEXIT_SOCKET_SOURCE)

        self.assertEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual(("socket.__new__",), result.audit_events)

    def test_atexit_swallowed_socket_failure_is_still_rejected(self) -> None:
        result = self._run_guarded(ATEXIT_SWALLOWED_SOCKET_SOURCE)

        self.assertEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual(("socket.__new__",), result.audit_events)

    def test_import_only_sources_are_allowed(self) -> None:
        for source in (
            IMPORT_ONLY_SSL_SOURCE,
            IMPORT_ONLY_HTTP_CLIENT_SOURCE,
            IMPORT_ONLY_UNITTEST_MOCK_SOURCE,
        ):
            with self.subTest(source=source):
                result = self._run_guarded(source)

                self.assertEqual(0, result.completed.returncode, result.completed.stderr)
                self.assertEqual((), result.audit_events)

    def test_noop_source_is_allowed(self) -> None:
        result = self._run_guarded(NOOP_SOURCE)

        self.assertEqual(0, result.completed.returncode, result.completed.stderr)
        self.assertEqual((), result.audit_events)
