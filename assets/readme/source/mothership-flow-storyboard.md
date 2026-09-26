# Mothership Core説明GIFの絵コンテ

この資料と `generate_mothership_flow.py` は、READMEに置く説明用GIFと
静止画ポスターの生成元です。commit済みの出力bytesは `SHA256SUMS` で固定します。
生成環境は asset-build.toml と同梱fontで固定します。実行結果の証拠や
外部操作の記録ではありません。

## 伝える順番

1. 人間とAIが仕事を分ける。proposal・evidenceは未結合の判断材料として示し、
   正確な実行項目は呼び出し側が別に用意する
2. Mothershipが対応済みの具体的な操作を固定する
3. 人間が表示された操作を承認または拒否する
4. 判断をローカル台帳へ記録し、同じ信頼された履歴内で一度だけ取り出す
5. 任意GitHub companionが明示transportで試行を記録し、純粋adapterがterminal attempt pairをCore Receiptへ投影する
6. 独立した確認系を別経路で構成し、Receipt成功を独立確認へ昇格させない

現在の最初の参照profileは github.merge_pr です。これは製品全体ではなく、
5つの実行パラメータ、判断との照合、台帳記録、一回限りのconsume境界を
具体化した例です。Coreの外側にある実行系・確認系はCore packageに
同梱されません。GitHub companionは別packageの任意導入で、汎用の実行系も
含まず、自動runtime bridgeもありません。
任意GitHub companionはCore発行のactionと明示transportだけで最大1回を試みます。
finish欠落はadapterがrejectし、retryやreconsumeは行いません。adapterはauthorityを
与えず、terminal attempt pairをCore Receiptへ投影するだけです。
独立したverifier producerは別途構成し、Receipt成功は外部真実ではありません。
確認不能や曖昧な観測はUNKNOWNのまま扱います。
base commit SHA、最終的な外部結果、人間本人の認証、台帳コピーをまたぐ
再利用防止を、この図が示すこともありません。
