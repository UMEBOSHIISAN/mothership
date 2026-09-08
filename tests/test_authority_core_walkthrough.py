from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
WALKTHROUGH = ROOT / "examples/authority_core_walkthrough.py"
GUARDED_CHILD_BOOTSTRAP = """\
import runpy
import socket
import sys
from unittest import mock
attempts = []
def blocked(*args, **kwargs):
    attempts.append(True)
    raise RuntimeError("walkthrough socket attempt blocked")
try:
    with mock.patch.object(socket, "socket", side_effect=blocked), mock.patch.object(socket, "getaddrinfo", side_effect=blocked):
        exec(sys.argv[1], {"__name__": "__main__", "runpy": runpy, "socket": socket})
finally:
    if attempts:
        raise SystemExit(97)
"""
REAL_WALKTHROUGH_SOURCE = (
    f"runpy.run_path({str(WALKTHROUGH)!r}, run_name='__main__')"
)
SOCKET_SOURCE = "socket.socket()"
GETADDRINFO_SOURCE = 'socket.getaddrinfo("example.invalid", 443)'
SWALLOWED_SOCKET_SOURCE = """\
try:
    socket.socket()
except RuntimeError:
    pass
"""


class AuthorityCoreWalkthroughTests(unittest.TestCase):
    def _run_guarded(self, source: str) -> subprocess.CompletedProcess[str]:
        environment = {
            "HOME": str(ROOT / ".test-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "7",
        }
        return subprocess.run(
            [sys.executable, "-c", GUARDED_CHILD_BOOTSTRAP, source],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

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
        completed = self._run_guarded(REAL_WALKTHROUGH_SOURCE)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertIn("操作を固定", completed.stdout)
        self.assertIn("合成した承認記録", completed.stdout)
        self.assertIn("人間の承認ではありません", completed.stdout)
        self.assertIn("consume: 成功", completed.stdout)
        self.assertIn("replay: 拒否", completed.stdout)
        self.assertIn("外部通信: なし", completed.stdout)
        self.assertIn("外部操作: なし", completed.stdout)

    def test_socket_constructor_is_rejected(self) -> None:
        completed = self._run_guarded(SOCKET_SOURCE)

        self.assertEqual(97, completed.returncode, completed.stderr)

    def test_getaddrinfo_is_rejected(self) -> None:
        completed = self._run_guarded(GETADDRINFO_SOURCE)

        self.assertEqual(97, completed.returncode, completed.stderr)

    def test_swallowed_socket_failure_is_still_rejected(self) -> None:
        completed = self._run_guarded(SWALLOWED_SOCKET_SOURCE)

        self.assertEqual(97, completed.returncode, completed.stderr)
