"""Run the GitHub read-back verifier against explicit synthetic JSON."""

from __future__ import annotations

import datetime
import io
import json

from mothership.action_authority import freeze_action
from mothership_github.verification import verify_merge_pr


_HEAD = "a" * 40
_BASE = "b" * 40
_MERGE = "c" * 40


class SyntheticResponse(io.BytesIO):
    status = 200

    def __init__(self, payload: object):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.headers = {}

    def getcode(self) -> int:
        return self.status


class SyntheticOpener:
    """A test-only opener; it is not an independent GitHub actor."""

    def __init__(self, merged_at: str):
        self.merged_at = merged_at

    def __call__(self, request, *, timeout: float):
        if "/pulls/7" in request.full_url:
            return SyntheticResponse(
                {
                    "url": "https://api.github.com/repos/owner/repo/pulls/7",
                    "number": 7,
                    "title": "synthetic title is not retained",
                    "state": "closed",
                    "merged": True,
                    "merged_at": self.merged_at,
                    "updated_at": self.merged_at,
                    "draft": False,
                    "head": {"sha": _HEAD, "ref": "feature"},
                    "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
                    "merge_commit_sha": _MERGE,
                    "body": "synthetic body is not retained",
                }
            )
        return SyntheticResponse(
            {
                "sha": _MERGE,
                "url": "https://api.github.com/repos/owner/repo/git/commits/" + _MERGE,
                "parents": [{"sha": _BASE}, {"sha": _HEAD}],
                "commit": {"message": "synthetic message is not retained"},
            }
        )


def _format_utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def main() -> int:
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    started = _format_utc(now - datetime.timedelta(seconds=3))
    finished = _format_utc(now - datetime.timedelta(seconds=2))
    merged_at = _format_utc(now - datetime.timedelta(seconds=1))
    action = freeze_action(
        "act-offline-readback",
        "github.merge_pr",
        {
            "repository": "owner/repo",
            "pull_request": 7,
            "expected_head_sha": _HEAD,
            "expected_base": "main",
            "merge_method": "merge",
        },
    )
    receipt = {
        "schema_version": "external-action-receipt.v0",
        "action_id": action.action["action_id"],
        "action_sha256": action.action_sha256,
        "executor_ref": {"ref_id": "executor:synthetic", "sha256": "d" * 64},
        "started_at": started,
        "finished_at": finished,
        "status": "UNKNOWN",
        "executor_observation_ref": {
            "ref_id": "observation:synthetic",
            "sha256": "e" * 64,
        },
    }
    result = verify_merge_pr(action, receipt, opener=SyntheticOpener(merged_at))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
