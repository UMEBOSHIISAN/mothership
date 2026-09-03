# 0.2互換protocolの履歴

Mothershipは、旧0.2互換protocolの固定snapshotを、相互運用性と履歴のために保持しています。
これは現在のMothershipの導入経路でも、複数repoを自動的に接続する実装でもありません。

| Protocol | 歴史上の意味上の所有者 |
| --- | --- |
| `frontdoor-task` | Agent Frontdoor |
| `governance-handoff` | Workflow Governance Model |
| `router-manifest` | Mothership Router |
| `observation-snapshot` | Secretary TUI |

上の名前はsnapshotの出所を示すためだけに残しています。旧repositoryへのリンクは提供しません。
現在の互換性の正本は、このrepositoryに同梱されたschema snapshot、fixture、digestです。

詳細なversion、commit、schema SHA-256、適合試験の記録は
[Compatibility](../compatibility.md) と [Protocol reference](../protocols.md) を参照してください。
