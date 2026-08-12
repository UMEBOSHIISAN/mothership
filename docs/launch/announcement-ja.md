# Mothership Flight Recorder 公開文案

Local draft — not published.

## 短文

Mothershipは、AIエージェントのためのオープンソースFlight Recorderです。

エージェントが「完了」と報告しても、実行内容が人の承認scopeを越えていることがあります。Mothershipは、明示的に
渡されたIntent、Scope、Decision、Approval binding、Execution receipt、Result evidence、Verification、
Persistence proofのリンクからverdictを再計算します。

```sh
mothership demo safe   # COMPLETE, exit 0
mothership demo drift  # DRIFTED, exit 21
```

ローカルで動作し、ambient stateを収集せず、agentを実行しません。Mothership verifies supplied records; it
does not grant authority or prove unobserved real-world actions.

AI agentのブラックボックスを見る: https://github.com/UMEBOSHIISAN/mothership

## 技術スレッド

1. 成功メッセージはclaimであり、receiptではありません。依頼、承認、実行証拠、verification、persistenceが
   同じ因果chainとしてつながらなければ、「完了」は完全な運用事実ではありません。

2. Mothershipは1回のagent flightを8つの必須linkとして扱います。Intent → Scope → Decision → Approval binding →
   Execution receipt → Result evidence → Verification → Persistence proofです。

3. safe fixtureでは、必要なsupplied recordがすべて同じchainへリンクしています。

   ```sh
   mothership demo safe
   # verdict: COMPLETE
   # exit: 0
   ```

4. drift fixtureはもっと現実的です。success labelはあっても、execution action classがapprovalと一致しません。

   ```sh
   mothership demo drift
   # verdict: DRIFTED
   # rule: FLIGHT.DRIFT.ACTION_CLASS
   # exit: 21
   ```

5. detectionと同じくらい境界が重要です。import、verify、replay、reportはworkerを起動せず、retryやrepairを行わず、
   home directoryを探索せず、recordをpermissionへ変換しません。

6. 検証できるのは明示的に渡されたrecordだけです。虚偽・欠落・未観測のsource recordはproofの外に残ります。
   reportは権限を付与せず、agent自体のcertificationでもありません。
