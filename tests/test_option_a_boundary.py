from pathlib import Path
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

class OptionABoundaryTests(unittest.TestCase):
    def core(self, script):
        env = {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
        return subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)

    def test_core_cli_import_has_no_transport_or_companion(self):
        result = self.core("import sys; import mothership.cli; assert 'urllib.request' not in sys.modules; assert 'http.client' not in sys.modules; assert not any(n.startswith('mothership_github') for n in sys.modules)")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_companion_is_typed_offline_error(self):
        result = self.core("from orchestration.lib.github_observation import fetch_github_observation, MissingGitHubIntegrationError\ntry: fetch_github_observation('invalid')\nexcept MissingGitHubIntegrationError: pass\nelse: raise AssertionError('must require companion')")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_companion_cli_explains_dependency(self):
        result = self.core("from mothership.cli import main; raise SystemExit(main(['github-candidate-window', '--repo', 'owner/repo']))")
        self.assertEqual(1, result.returncode)
        self.assertIn('mothership-github', result.stderr)
        self.assertEqual('', result.stdout)
