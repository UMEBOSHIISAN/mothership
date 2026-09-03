from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
JAPANESE_GUIDE = ROOT / "docs/ja/README.md"
INSTALLATION = ROOT / "docs/installation.md"
RELEASE_CHECKLIST = ROOT / "RELEASE_CHECKLIST.md"
QUICKSTART = (
    "python3 -m venv .venv",
    ". .venv/bin/activate",
    "python -m pip install .",
    "mothership verify",
    "mothership demo",
)


def _shell_blocks(path: Path) -> tuple[tuple[str, ...], ...]:
    blocks = re.findall(r"```(?:sh|bash)\n(.*?)\n```", path.read_text("utf-8"), re.DOTALL)
    return tuple(
        tuple(line.strip() for line in block.splitlines() if line.strip())
        for block in blocks
    )


def _minimal_environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "7",
    }


class DocumentationCommandTests(unittest.TestCase):
    def test_japanese_root_readme_has_the_tested_quickstart_sequence(self) -> None:
        self.assertEqual((QUICKSTART,), _shell_blocks(README))
        self.assertEqual((), _shell_blocks(JAPANESE_GUIDE))
        self.assertIn("../../README.md", JAPANESE_GUIDE.read_text("utf-8"))

    def test_installation_commands_match_the_supported_lifecycle(self) -> None:
        version = (ROOT / "VERSION").read_text("utf-8").strip()
        blocks = _shell_blocks(INSTALLATION)
        self.assertEqual(5, len(blocks))
        self.assertEqual(
            (
                "git clone https://github.com/UMEBOSHIISAN/mothership.git",
                "cd mothership",
                *QUICKSTART,
            ),
            blocks[0],
        )
        self.assertEqual(
            (
                "python3 -m venv .venv",
                ". .venv/bin/activate",
                f"python -m pip install --no-deps mothership_control_plane-{version}-py3-none-any.whl",
                "mothership verify",
            ),
            blocks[1],
        )
        self.assertEqual(
            (
                "python3 -m venv .venv",
                ". .venv/bin/activate",
                'python -m pip install -e ".[test]"',
                "PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v",
            ),
            blocks[2],
        )
        self.assertEqual(
            (
                "mothership verify",
                "mothership demo",
                "python tools/run_evaluation.py",
                "PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v",
            ),
            blocks[3],
        )
        self.assertEqual(("python -m pip uninstall mothership-control-plane",), blocks[4])

    def test_safe_verification_commands_execute_with_exact_tracked_outputs(self) -> None:
        expected = {
            ("-m", "mothership", "verify"): ROOT / "docs/generated/verify-output.json",
            ("-m", "mothership", "demo"): ROOT / "docs/generated/demo-output.json",
            ("tools/run_evaluation.py",): ROOT / "evaluation/results/mothership-0.4.1.json",
        }
        with tempfile.TemporaryDirectory() as directory:
            environment = _minimal_environment(Path(directory))
            for arguments, result in expected.items():
                with self.subTest(arguments=arguments):
                    completed = subprocess.run(
                        [sys.executable, *arguments],
                        cwd=ROOT,
                        env=environment,
                        input=b"",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=15,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr)
                    self.assertEqual(b"", completed.stderr)
                    self.assertEqual(json.loads(result.read_bytes()), json.loads(completed.stdout))

    def test_documented_shell_commands_do_not_hide_privilege_or_network_execution(self) -> None:
        commands = [
            command
            for path in (README, JAPANESE_GUIDE, INSTALLATION, ROOT / "CONTRIBUTING.md")
            for block in _shell_blocks(path)
            for command in block
        ]
        for command in commands:
            lowered = command.casefold()
            self.assertNotIn("sudo ", lowered)
            self.assertNotIn("curl ", lowered)
            self.assertNotIn("wget ", lowered)
            self.assertNotIn("--force", lowered)
            self.assertNotIn("$home", lowered)
            self.assertNotRegex(lowered, r"(?:token|password|secret)=")

    def test_release_checklist_uses_the_same_portable_test_command(self) -> None:
        text = RELEASE_CHECKLIST.read_text("utf-8")
        portable = "PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v"
        self.assertIn(f"`{portable}`", text)
        self.assertNotIn("/opt/homebrew", text)


if __name__ == "__main__":
    unittest.main()
