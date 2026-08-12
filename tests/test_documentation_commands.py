from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
JAPANESE_README = ROOT / "docs/ja/README.md"
INSTALLATION = ROOT / "docs/installation.md"
QUICKSTART = (
    "python3 -m venv .venv",
    ". .venv/bin/activate",
    "python -m pip install .",
    "mothership verify",
    "mothership demo safe",
)


def _shell_blocks(path: Path) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(line.strip() for line in block.splitlines() if line.strip())
        for block in re.findall(r"```(?:sh|bash)\n(.*?)\n```", path.read_text("utf-8"), re.DOTALL)
    )


class DocumentationCommandTests(unittest.TestCase):
    def test_both_readme_quickstarts_are_the_same_tested_sequence(self) -> None:
        self.assertEqual((QUICKSTART,), _shell_blocks(README))
        self.assertEqual((QUICKSTART,), _shell_blocks(JAPANESE_README))

    def test_installation_documents_the_explicit_flight_commands(self) -> None:
        text = INSTALLATION.read_text("utf-8")
        for command in (
            "mothership import generic events.jsonl --out ./flight-001",
            "mothership verify run ./flight-001",
            "mothership replay ./flight-001",
            "mothership report ./flight-001 --format markdown",
        ):
            self.assertIn(command, text)
        self.assertIn("zero runtime dependencies", text.casefold())
        self.assertIn("build", text.casefold())

    def test_documented_shell_commands_do_not_hide_privilege_or_network_execution(self) -> None:
        commands = [
            command
            for path in (README, JAPANESE_README, INSTALLATION)
            for block in _shell_blocks(path)
            for command in block
        ]
        for command in commands:
            lowered = command.casefold()
            self.assertNotIn("sudo ", lowered)
            self.assertNotIn("curl ", lowered)
            self.assertNotIn("wget ", lowered)
            self.assertNotRegex(lowered, r"(?:token|password|secret)=")


if __name__ == "__main__":
    unittest.main()
