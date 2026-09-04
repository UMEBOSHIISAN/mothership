from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
WALKTHROUGH = ROOT / "examples/authority_core_walkthrough.py"


class AuthorityCoreWalkthroughTests(unittest.TestCase):
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
        self.assertIn("人間の判断を記録", completed.stdout)
        self.assertIn("consume: 成功", completed.stdout)
        self.assertIn("replay: 拒否", completed.stdout)
        self.assertIn("外部通信: なし", completed.stdout)
        self.assertIn("外部操作: なし", completed.stdout)
