"""Generate existing consumer JSONL with synthetic callbacks, entirely offline.

Fixture approval is not a human approval ceremony. Only temporary synthetic
ledgers are written. The genuine reference consumer saves its current format;
the example never builds a portable request or fills missing records.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile

from examples import github_merge_reference as reference


class _Terminal(io.StringIO):
    def isatty(self):
        return True


class _FixtureApproval(_Terminal):
    def __init__(self, output):
        super().__init__()
        self.output = output

    def readline(self):
        frozen = next(json.loads(line) for line in self.output.getvalue().splitlines()
                      if json.loads(line).get("event") == "frozen_action")
        return f"approve {frozen['action']['action_id']} {frozen['action_sha256']}\n"


class _SyntheticTransport:
    def get_pull_request(self, repository, pull_request):
        return {"http_status": 200, "state": "open", "merged": False,
                "head_sha": "a" * 40, "base_ref": "main"}

    def merge_pull_request(self, **parameters):
        return {"http_status": 200, "merged": True, "merge_commit_sha": "c" * 40}


class _Response(io.BytesIO):
    status = 200
    headers = {}

    def getcode(self):
        return 200


def _synthetic_readback(request, *, timeout):
    # Deliberately reports unmerged after the synthetic executor's success.
    # The recorded independent observation must therefore remain UNKNOWN.
    payload = {
        "url": "https://api.github.com/repos/example/repo/pulls/7", "number": 7,
        "title": "synthetic offline handoff", "updated_at": "2026-10-20T00:00:00Z", "draft": False,
        "state": "open", "closed": False, "merged": False, "merged_at": None,
        "head": {"sha": "a" * 40, "ref": "synthetic"},
        "base": {"ref": "main", "repo": {"full_name": "example/repo"}},
        "merge_commit_sha": None,
    }
    return _Response(json.dumps(payload).encode())


def synthetic_saved_result() -> bytes:
    """Run the real saver/validators once with local fixture callbacks only."""
    with tempfile.TemporaryDirectory(prefix="mothership-result-example-") as directory:
        root = Path(directory).resolve()
        os.chmod(root, 0o700)
        output = _Terminal()
        code = reference.main(
            ["--repo", "example/repo", "--pr", "7", "--ledger-dir", str(root),
             "--verify-result", "--save-result"],
            transport=_SyntheticTransport(), input_stream=_FixtureApproval(output),
            output_stream=output, readback_opener=_synthetic_readback,
        )
        if code != 3:
            raise RuntimeError("synthetic readback did not retain expected uncertainty")
        return (root / "result.jsonl").read_bytes()


if __name__ == "__main__":
    sys.stderr.write("SYNTHETIC fixture only; no network, credentials or human approval; temporary ledgers.\n")
    raw = synthetic_saved_result()
    if sys.stdout.buffer.write(raw) != len(raw):
        raise OSError("incomplete example output")
    sys.stdout.buffer.flush()
