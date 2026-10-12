# Mothership Core portable review storyboard

この資料と `generate_mothership_flow.py` は、READMEに置く説明用GIFと
静止画ポスターの生成元です。commit済みの出力bytesは `SHA256SUMS` で固定します。
生成環境は `asset-build.toml` と同梱fontで固定します。実行結果の証拠や
外部操作の記録ではありません。

## 伝える順番

1. Agents、LangGraph、OpenClaw、Lobster、MCP、Dots、UME-HARNESS、Evidenceの
   8つのbounded routeが、同じCore発行actionとhost-owned contextをreviewへ渡す
2. Mothershipがlive `FrozenAction`から対応済みの具体的な操作と期限を供給し、
   review helperがrequest digestを作る
3. hostのresponseを保持したrequest、action、期限、host_id・session・actor・
   runtime generation・scopeへ照合する。変更または期限切れは止める
4. review helperはledgerを書かず、既存のdecision validatorへ渡す。consumeは
   同じ信頼された履歴内で一度だけ行う
5. 選択経路のlocal evidenceだけを測定する。pinned SDK、same-process
   checkpointer、real local lease fixture、subprocess owner、synthetic transportを
   live hostや外部効果と混同しない
6. 任意GitHub companionが試行を記録し、純粋adapterがterminal attempt pairを
   Core Receiptへ投影する。host callback、retry、reconsumeは追加しない
7. companionのopt-in read-back producerが別のVerificationを作る。Receipt成功を
   人間・GitHub・外部真実の証明へ昇格させず、UNKNOWNを保持する
8. 不明な結果は停止し、storageやdeviceなどのfuture exact profileをgeneric
   `execute`へ拡張しない

現在の最初の参照profileは `github.merge_pr` です。これは製品全体ではなく、
5つの実行パラメータ、判断との照合、台帳記録、一回限りのconsume境界を
具体化した例です。Coreのreview helperは純粋で、ledger、network、credential、
executor callback、host runtimeのlease/revocation強制を行いません。
8つのrouteは実装とlocal checksを持ちますが、全hostのgateway、credential、
runtime権限、外部効果を実装したことを示しません。Coreの外側に汎用の実行系は
追加していません。実行系・確認系はhost側の責務です。
GitHub companionは別packageの任意導入で、Core発行のactionと明示transportだけで
最大1回を試みます。finish欠落はadapterがrejectし、retryやreconsumeは行いません。
read-back producerはcompanionのopt-in機能ですが、VerificationはReceiptとは別記録です。
確認不能や曖昧な観測はUNKNOWNのまま扱います。
base commit SHA、hostのeffect境界、人間本人の認証、台帳コピーをまたぐ
再利用防止、永続resumeを、この図が示すことはありません。
