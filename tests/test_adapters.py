from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from orchestration.lib.paths import PreparedScope, ScopeFile, prepare_scope


FIXTURE_ROOT = Path(tempfile.gettempdir()).resolve() / "mothership-adapters-tests"
ALIASES = ("claude-code-agent", "codex-cli", "ollama-local")


class AdapterPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
        os.chmod(FIXTURE_ROOT, 0o700)
        self.temp = tempfile.TemporaryDirectory(dir=FIXTURE_ROOT)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir(mode=0o700)
        self.task = self.root / "task"
        self.task.mkdir(mode=0o700)
        (self.task / "prompt").write_bytes(b"prompt\x00bytes")
        (self.task / "z.txt").write_bytes(b"z")
        (self.task / "a\u6885.txt").write_bytes("a\u6885".encode("utf-8"))

    def tearDown(self) -> None:
        self.temp.cleanup()
        FIXTURE_ROOT.rmdir()

    def _scope(self, staged: bool = True) -> PreparedScope:
        return prepare_scope(
            {"prompt_path": "prompt", "context_paths": ["z.txt", "a\u6885.txt"]},
            self.task,
            self.run,
            staged,
        )

    def test_plans_have_frozen_exact_projection_and_sanitized_environment(self) -> None:
        # Reordering flags, using a caller executable, or leaking a parent key must fail this.
        from orchestration.lib.adapters import AdapterPlan, build_adapter_plan

        scope = self._scope()
        parent = {
            "PATH": "/bin", "HOME": "/home/test", "TMPDIR": "/tmp/test",
            "LANG": "C", "LC_CUSTOM": "yes", "CODEX_HOME": "/codex",
            "SECRET": "no", "HTTP_PROXY": "no", "FRIEND_MOTHERSHIP_CALL_DEPTH": "99",
        }
        expected_env = {
            "PATH": "/bin", "HOME": "/home/test", "TMPDIR": "/tmp/test",
            "LANG": "C", "LC_CUSTOM": "yes", "CODEX_HOME": "/codex",
            "FRIEND_MOTHERSHIP_CALL_DEPTH": "1",
        }
        expected = {
            "codex-cli": (
                "codex", "-a", "never", "exec", "--ignore-user-config", "--ignore-rules",
                "--strict-config", "-c", 'web_search="disabled"', "-c", "features.apps=false",
                "-c", "features.hooks=false", "-c", "features.memories=false", "--ephemeral",
                "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(scope.staged_root),
                "--color", "never", "-",
            ),
            "claude-code-agent": (
                "claude", "--print", "--safe-mode", "--tools", "", "--permission-mode", "plan",
                "--no-session-persistence", "--no-chrome", "--disable-slash-commands",
                "--strict-mcp-config", "--mcp-config", "{}", "--output-format", "json",
            ),
            "ollama-local": ("ollama", "run", "friend-core-advisory"),
        }
        self.assertEqual(("alias", "argv", "stdin_bytes", "cwd", "env"), tuple(AdapterPlan.__dataclass_fields__))
        self.assertTrue(AdapterPlan.__dataclass_params__.frozen)
        for alias in ALIASES:
            with self.subTest(alias=alias):
                plan = build_adapter_plan(alias, b"prompt\x00bytes", scope, parent)
                self.assertEqual(alias, plan.alias)
                self.assertEqual(expected[alias], plan.argv)
                self.assertNotIn("prompt", "\0".join(plan.argv))
                self.assertEqual(scope.staged_root, plan.cwd)
                self.assertEqual(expected_env, plan.env)
                self.assertIsNot(plan.env, parent)
                self.assertEqual(parent["SECRET"], "no")
                if alias == "codex-cli":
                    self.assertEqual(b"prompt\x00bytes", plan.stdin_bytes)
                else:
                    self.assertEqual(
                        self._envelope(b"prompt\x00bytes", scope.files, scope.staged_root), plan.stdin_bytes
                    )

    def _envelope(self, prompt: bytes, files: tuple[ScopeFile, ...], staged: Path | None) -> bytes:
        assert staged is not None
        chunks = [
            b"FRIEND-MOTHERSHIP-ENVELOPE/1\n",
            f"prompt-bytes:{len(prompt)}\n".encode(),
            f"prompt-sha256:{hashlib.sha256(prompt).hexdigest()}\n\n".encode(),
            prompt,
            f"\ncontext-files:{len(files)}\n".encode(),
        ]
        for item in files:
            path = item.relative_path.encode("utf-8")
            raw = (staged / item.relative_path).read_bytes()
            chunks.extend((
                f"file-path-bytes:{len(path)}\n".encode(), b"file-path:" + path + b"\n",
                f"file-bytes:{len(raw)}\n".encode(),
                f"file-sha256:{hashlib.sha256(raw).hexdigest()}\n\n".encode(), raw, b"\n",
            ))
        chunks.append(b"END\n")
        return b"".join(chunks)

    def test_live_plan_rejects_bad_stage_and_context_integrity(self) -> None:
        # Reading an unchecked leaf or accepting an unstaged scope must fail this.
        from orchestration.lib.adapters import build_adapter_plan

        unstaged = self._scope(False)
        with self.assertRaises(ValueError):
            build_adapter_plan("codex-cli", b"x", unstaged, {})
        scope = self._scope()
        assert scope.staged_root is not None
        os.chmod(scope.staged_root, 0o700)
        os.chmod(scope.staged_root / "z.txt", 0o600)
        (scope.staged_root / "z.txt").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            build_adapter_plan("ollama-local", b"x", scope, {})
        for alias in ("unknown", "Codex-cli", ""):
            with self.subTest(alias=alias):
                with self.assertRaises(ValueError):
                    build_adapter_plan(alias, b"x", scope, {})

    def test_preview_is_nonlaunchable_and_matches_later_live_projection(self) -> None:
        # Creating a leaf, reading task bytes, or diverging from the live argv/env must fail this.
        from orchestration.lib.adapters import AdapterPlanPreview, build_adapter_plan, build_adapter_plan_preview

        prospective = self.run / "staged-context"
        parent = {"PATH": "/bin", "LC_Z": "1", "SECRET": "hidden"}
        before = dict(parent)
        self.assertEqual(("alias", "argv", "cwd", "env"), tuple(AdapterPlanPreview.__dataclass_fields__))
        self.assertTrue(AdapterPlanPreview.__dataclass_params__.frozen)
        self.assertNotIn("stdin_bytes", AdapterPlanPreview.__dataclass_fields__)
        previews = {}
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("preview read bytes")):
            for alias in ALIASES:
                with self.subTest(alias=alias):
                    preview = build_adapter_plan_preview(alias, prospective, parent)
                    previews[alias] = preview
                    self.assertEqual(alias, preview.alias)
                    self.assertEqual(prospective, preview.cwd)
                    self.assertEqual({"PATH": "/bin", "LC_Z": "1", "FRIEND_MOTHERSHIP_CALL_DEPTH": "1"}, preview.env)
        self.assertEqual(before, parent)
        self.assertFalse(prospective.exists())
        scope = self._scope()
        for alias in ALIASES:
            preview = previews[alias]
            live = build_adapter_plan(alias, b"not used for equality", scope, parent)
            self.assertEqual((preview.alias, preview.argv, preview.cwd, preview.env), (live.alias, live.argv, live.cwd, live.env))

    def test_preview_rejects_unsafe_prospective_paths_without_creating_a_leaf(self) -> None:
        # Resolving an input, allowing a wrong parent mode, or accepting a leaf must fail this.
        from orchestration.lib.adapters import build_adapter_plan_preview

        good = self.run / "staged-context"
        bad_parent = self.root / "bad-parent"
        bad_parent.write_bytes(b"not directory")
        link = self.root / "link"
        link.symlink_to(self.run, target_is_directory=True)
        cases = (
            Path("staged-context"),
            Path(str(good) + "/../staged-context"),
            self.run / "other",
            self.root / "missing" / "staged-context",
            link / "staged-context",
            bad_parent / "staged-context",
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_adapter_plan_preview("codex-cli", value, {})
        os.chmod(self.run, 0o755)
        with self.assertRaises(ValueError):
            build_adapter_plan_preview("codex-cli", good, {})
        os.chmod(self.run, 0o700)
        good.mkdir(mode=0o555)
        with self.assertRaises(ValueError):
            build_adapter_plan_preview("codex-cli", good, {})


if __name__ == "__main__":
    unittest.main()
