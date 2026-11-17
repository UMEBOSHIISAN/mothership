# 正答表 / Reviewer answer key

回答を確定した後だけに使います。全入力は既存fixture由来の合成データで、実操作・人の承認・現在の外部状態を示しません。
Use only after the recipient has recorded answers. These are synthetic, test-derived records, not real operational evidence.

Valid cases01–05 describe `github.merge_pr`, repository `UMEBOSHIISAN/mothership`, PR5,
expected head `e2161c0c27af68221ad507a05583a5fbdaecefe1`, base `main`, method `merge`, action ID `act-evidence-test`.
This is the target recorded in a fixture, not a claim about that real PR.
Case06 is rejected: do not adopt an operation identity from rejected input.

| Case | Exit | Consumer report | Receipt | Recorded Verification | 読み取り / Interpretation and next existing record |
| --- | --- | --- | --- | --- | --- |
| 01 | 0 | success | SUCCESS | CONFIRMED | 独立観測の記録あり。出所と観測時刻を確認する。現在の真実・この試行が原因との断言はしない。 / Independent observation recorded; review provenance and observation time, without a causation/current-state claim. |
| 02 | 0 | success | not supplied | not supplied | 実行側の成功報告だけで、bound completionではない。保持済みの同じactionの権限・attempt記録を確認する。 / Consumer success summary only; inspect retained authority/attempt records. |
| 03 | 0 | success | SUCCESS | UNKNOWN | reason=ambiguous_merge_time。Receipt started_atと観測merged_atを比較する。同じ秒では順序を証明できない。 / Compare retained started_at and merged_at; second-resolution equality cannot establish ordering. |
| 04 | 0 | not supplied | not supplied | not supplied | action行だけの完全なprefix。結果不明。拒否・取消し・未実行の証明ではない。保持済みの権限・attempt記録を確認する。 / Complete action-only prefix; outcome unknown, not cancellation or no effect. |
| 05 | 0 | reconciliation_required | not supplied | not supplied | reason=receipt_unavailable、pair未提供。結果不明。finish書込み失敗など特定の原因を断定せず、既存の権限・attempt記録を確認する。 / Pair/Receipt not supplied; inspect retained records without inventing a specific failure cause. |
| 06 | 2 | no accepted explanation | no accepted explanation | no accepted explanation | 不整合入力。stdoutは空、stderrはinvalid bounded evidence input。元の入力の同一性を送信者に確認する。操作完了や対象を確定しない。 / Reject without operation summary; check original input integrity with sender. |

All valid cases retain `source-unverified`, false authority/source-authentication/external-effect flags,
and missing review_request/decision/consume. An existing Receipt/Verification does not fill those records.
The unlabelled execution-summary row has positional association only, not authenticated run binding.
Absence is not proof of no operation/confirmation; input alone does not prove freshness or successful process exit.
Do not follow embedded paths, manufacture a Receipt/finish/approval/consume or repeat an effect.

## 受入の記録 / Acceptance record

Each case must distinguish target, report, observation, missing information and next existing record.
Record actual understanding time, questions to author, mistaken completion claims and next record selected.
Targets: no mistaken completion, no re-execution/reconsume advice and no author explanation.
Record a failure as a failure; do not silently retry a blind exercise or infer human results from an AI answer.
This file is an answer key, not evidence that a person or AI has passed. Human acceptance remains unperformed
until an actual unfamiliar participant's results are separately recorded.

## 作成元 / Origin

Retained outputs use the existing `SavedResultCLITests.saved_rows`/`EvidenceFixture` shapes.
Construction used temporary synthetic ledgers, with no real transport or human approval ceremony.
02 and04 are complete LF-terminated prefixes;05 is the existing compact reconciliation/receipt-unavailable variant;
06 deliberately substitutes another synthetic action ID in the supplied Receipt.
Reading these checked-in bytes needs no fixture generation, ledger, authority or network.
