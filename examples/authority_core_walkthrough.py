#!/usr/bin/env python3
"""Show the current Authority Core boundary without external side effects.

This walkthrough is intentionally local: it freezes one supported action,
shows the display derived by the core, records an approval in a temporary
ledger, consumes it once, and demonstrates that replay is rejected.  It does
not contact GitHub, load credentials, or execute the action.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from mothership import action_authority


PARAMETERS = {
    "repository": "UMEBOSHIISAN/mothership",
    "pull_request": 5,
    "expected_head_sha": "e2161c0c27af68221ad507a05583a5fbdaecefe1",
    "expected_base": "main",
    "merge_method": "merge",
}


def main() -> int:
    print("Mothership Authority Core — オフライン walkthrough")
    print("外部通信: なし / 外部操作: なし / 一時台帳のみ")

    with tempfile.TemporaryDirectory(prefix="mothership-authority-core-") as directory:
        authority_dir = Path(directory) / "authority-action"
        authority_dir.mkdir(mode=0o700)
        os.chmod(authority_dir, 0o700)
        ledger_path = authority_dir / "events.jsonl"

        frozen = action_authority.freeze_action(
            "act-walkthrough-001",
            "github.merge_pr",
            PARAMETERS,
        )
        display = frozen.action["display"]
        print("\n1. 操作を固定")
        print(f"   対象: {display['target']}")
        print(f"   表示: {display['scope']}")
        print(f"   action digest: {frozen.action_sha256}")

        approval = action_authority.record_action_decision(
            ledger_path,
            frozen,
            "approve",
            frozen.action["action_id"],
            frozen.action_sha256,
        )
        print("\n2. 人間の判断を記録")
        print(f"   decision: {approval['decision']}")
        print(f"   event: {approval['event_id']}")

        consume_event, consumed_action = action_authority.consume_action(
            ledger_path,
            approval["event_id"],
            consumed_action_id := consumed_action_id_from(approval),
            approval["action_sha256"],
        )
        print("\n3. consume: 成功")
        print(f"   event: {consume_event['event_id']}")
        print(f"   action: {consumed_action['action_id']}")

        try:
            action_authority.consume_action(
                ledger_path,
                approval["event_id"],
                consumed_action_id,
                approval["action_sha256"],
            )
        except action_authority.ActionLedgerError as exc:
            print(f"\n4. replay: 拒否 ({type(exc).__name__})")
        else:  # pragma: no cover - the ledger contract must reject this path
            raise RuntimeError("authority replay was unexpectedly accepted")

    print("\nこの例はfreeze / decision / consumeの境界だけを示します。")
    print("executor、GitHub変更、結果確認は含みません。")
    return 0


def consumed_action_id_from(approval: dict[str, object]) -> str:
    action = approval["action"]
    if not isinstance(action, dict) or not isinstance(action.get("action_id"), str):
        raise RuntimeError("approval did not contain an action id")
    return action["action_id"]


if __name__ == "__main__":
    raise SystemExit(main())
