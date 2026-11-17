# Mothership Core portable review storyboard

この資料と `generate_mothership_flow.py` は、READMEに置く説明用GIFと
静止画ポスターの生成元です。commit済みの出力bytesは `SHA256SUMS` で固定します。
生成環境は `asset-build.toml` と同梱fontで固定します。実行結果の証拠や
外部操作の記録ではありません。

## 伝える順番

1. Agents、LangGraph、OpenClaw、Lobster、UME-HARNESSの実行系は、
   Core発行actionとhost-owned contextをreviewへ渡す。
   MCP・Dots・Evidenceは保存済み記録のread-only経路として分ける
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
8. 保存した結果を別の人・AIへ渡し、bundleは `inspect --human`、
   参照consumerのJSONLは `inspect-result --human` で読む。
   実行報告・独立観測・欠落・次の確認を分け、閲覧は承認・consumeを補わず、
   権限を移送しない。UNKNOWNを成功へ変えず、操作を再実行しない

GIFの6場面は、入口、操作の固定、context照合、reviewとconsume、
ReceiptとVerification、保存結果の引継ぎです。local checksの範囲は入口と
説明文で示します。合成の受取人向け6ケースは実操作の証拠ではなく、
人間の受入も別途記録します。storageやdeviceなどのfuture exact profileを
generic `execute`へ拡張する図ではありません。

現在の最初の参照profileは `github.merge_pr` です。これは製品全体ではなく、
5つの実行パラメータ、判断との照合、台帳記録、一回限りのconsume境界を
具体化した例です。Coreのreview helperは純粋で、ledger、network、credential、
executor callback、host runtimeのlease/revocation強制を行いません。
8つのbounded routeは、実行系と読取専用系で確認範囲が異なり、全hostのgateway、credential、
runtime権限、外部効果を実装したことを示しません。Coreの外側に汎用の実行系は
追加していません。実行系・確認系はhost側の責務です。
GitHub companionは別packageの任意導入で、Core発行のactionと明示transportだけで
最大1回を試みます。finish欠落はadapterがrejectし、retryやreconsumeは行いません。
read-back producerはcompanionのopt-in機能ですが、VerificationはReceiptとは別記録です。
確認不能や曖昧な観測はUNKNOWNのまま扱います。
base commit SHA、hostのeffect境界、人間本人の認証、台帳コピーをまたぐ
再利用防止、永続resumeを、この図が示すことはありません。

## Saved-result reading story

`--story saved-result` は、既存の合成6ケースから、受け取った人が完了を
早合点しないための3つの読み方を説明します。GIFとポスターは同じ内容を
別の画面向けに配置した説明用の合成図で、スクリーンショットや実行結果では
ありません。source-unverified、authority: false、no rerunを各出力のフッターに
表示します。

- **case 02 / UNKNOWN** — consumerのsuccess報告だけで、ReceiptとVerificationは未提供です。
  結果を完了とせず、保持済みの同じactionのauthority・attempt記録を読みます。
- **case 03 / UNKNOWN** — ReceiptはSUCCESSでも、VerificationはUNKNOWN（reason: `ambiguous_merge_time`）です。
  保持した`started_at`と報告された`merged_at`を比較し、再実行しません。
- **case 06 / REJECTED** — 不整合入力はexit 2で受理された説明を返しません。
  元の入力を保持してsenderへ同一性を確認し、対象や完了を表示しません。

status、Receipt、Verification、拒否を別の色で描き、未確認の成功を緑で表しません。

## 再生成

`requirements-assets.txt`のPillowと、契約に固定した同梱fontを使います。
リポジトリのルートから、言語ごとに既存Core図と追加の保存結果図を生成します。
`python3`はその生成環境のPython 3.12以上を選びます。

```sh
python3 assets/readme/source/generate_mothership_flow.py --locale ja --font assets/readme/source/fonts/NotoSansJP-Regular.ttf --output-dir assets/readme/ja
python3 assets/readme/source/generate_mothership_flow.py --locale en --font assets/readme/source/fonts/NotoSansJP-Regular.ttf --output-dir assets/readme/en
python3 assets/readme/source/generate_mothership_flow.py --story saved-result --locale ja --font assets/readme/source/fonts/NotoSansJP-Regular.ttf --output-dir assets/readme/ja
python3 assets/readme/source/generate_mothership_flow.py --story saved-result --locale en --font assets/readme/source/fonts/NotoSansJP-Regular.ttf --output-dir assets/readme/en
```

出力一覧は`asset-build.toml`の`outputs`と`reader_outputs`に分けています。
再生成後は出力bytesを確認し、既存`SHA256SUMS`へ反映します。
Pillow 13.0.0への依存更新では、既存のGIF・PNGは再生成していません。新pinの生成候補は
既存画像とbytes・画素が異なるため、現在の画像を再生成するときは更新前のsource revision
`57e967a`とPillow 12.3.0、同等のbuild環境を使用し、checksumで一致を確認します。
新生成物を採用するときに限り、
画像と対応するchecksumを同時に更新します。
