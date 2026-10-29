"""Offline checks for explicitly selected gh-backed credentials."""
import os
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from mothership_adapters.gh_auth import GhAuthError, load_secrets


class GhAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gh = Path(self.tmp.name) / "gh"

    def tool(self, body):
        self.gh.write_text("#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then printf 'gh version 2.103.3\\n'; exit 0; fi\n" + body + "\n")
        self.gh.chmod(0o700)
        return patch("mothership_adapters.gh_auth._find_gh", return_value=str(self.gh))

    def test_selected_account_succeeds_once_without_inherited_token(self):
        body = '''[ "$1 $2 $3 $4 $5 $6 $7" = "auth token --hostname github.com --user Operator --no-refresh" ] || exit 9
[ -z "${GH_TOKEN+x}" ] && [ -z "${GITHUB_TOKEN+x}" ] || exit 9
[ "$GH_NO_UPDATE_NOTIFIER" = 1 ] && [ "$GH_PROMPT_DISABLED" = 1 ] || exit 9
printf 'synthetic-token\\n' '''
        with self.tool(body), patch.dict(os.environ, {"GH_TOKEN": "wrong-secret"}):
            self.assertEqual(("synthetic-token", "2.103.3"), load_secrets("github", "Operator"))

    def test_empty_multiline_large_and_failed_output_are_rejected(self):
        for body in ("exit 0", "printf 'one\\ntwo\\n'", "yes x | head -c 5000", "printf private-error >&2; exit 1"):
            with self.subTest(body=body), self.tool(body):
                with self.assertRaises(GhAuthError) as raised:
                    load_secrets("github", "Operator")
                self.assertNotIn("private-error", str(raised.exception))

    def test_timeout_stops_without_fallback(self):
        with self.tool("exec /bin/sleep 3"), patch("mothership_adapters.gh_auth._GH_TIMEOUT_SECONDS", 0.1):
            with self.assertRaises(GhAuthError):
                load_secrets("github", "Operator")

    def test_invalid_category_and_account_stop_before_invocation(self):
        with self.tool("printf 'synthetic-token\\n' "):
            for category, login in (("other", "Operator"), ("github", "bad user"), ("github", "")):
                with self.subTest(category=category, login=login), self.assertRaises(GhAuthError):
                    load_secrets(category, login)

    def test_untrusted_executable_path_stops_before_invocation(self):
        from mothership_adapters.gh_auth import _find_gh
        with self.tool("exit 0"):
            pass
        with patch("mothership_adapters.gh_auth.shutil.which", return_value=str(self.gh)):
            with self.assertRaises(GhAuthError):
                _find_gh()

    def test_nonstandard_gh_store_stops_before_invocation(self):
        for key in ("GH_CONFIG_DIR", "XDG_CONFIG_HOME"):
            with self.subTest(key=key), patch.dict(os.environ, {key: "/synthetic/store"}):
                with patch("mothership_adapters.gh_auth._find_gh") as find:
                    with self.assertRaises(GhAuthError):
                        load_secrets("github", "Operator")
                    self.assertEqual(0, find.call_count)

    def test_failed_child_reaping_has_deadline_and_keeps_failure(self):
        from unittest.mock import MagicMock
        from mothership_adapters.gh_auth import _run_gh
        child = MagicMock()
        child.poll.return_value = None
        child.wait.side_effect = subprocess.TimeoutExpired("synthetic", 1)
        with patch("mothership_adapters.gh_auth.subprocess.Popen", return_value=child), \
             patch("mothership_adapters.gh_auth.selectors.DefaultSelector", side_effect=OSError("synthetic")):
            with self.assertRaises(GhAuthError):
                _run_gh("/usr/bin/synthetic", ["--version"])
        child.wait.assert_called_once_with(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
