# Mothership 日本語ガイド

[English README](../../README.md) · [設計](../architecture.md) · [導入と更新](../installation.md) · [安全モデル](../security.md) · [構成ガイド](../composition.md)

Mothership は、Codex CLI・Claude Code・Ollama Local などをまたぐ AI 開発環境のための、**安全第一の共通コントロール基盤**です。閉じた契約、失敗時に止まる検証、助言的ルーティング、承認ログの部品、ローカル診断、設定テンプレートを提供します。Codex 専用ではありません。

自分の Mac、別の Mac、チームメンバー、専用 mini 機へ環境の土台を再現するときに、「共有すべき構造」と「各マシンに残すべき秘密情報・実行権限」を分けられます。Mothership 自体は実行権限を与えず、モデル呼び出しや外部操作も自動では行いません。

![暗い星空を進むクジラ型の母船](../../assets/mothership-banner.png)

## はじめ方

Python 3.12 以上が必要です。

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git
cd mothership
python3 --version
./bootstrap/doctor.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

`doctor.sh` は、固定されたローカルアダプターの利用可否を確認するだけです。ソフトウェアの導入、認証、モデル呼び出し、設定変更、フックの追加は行いません。アダプターが未導入なら診断は非ゼロ終了になりますが、それは診断結果です。

## 安全な使い方

- [`config/executors.example.json`](../../config/executors.example.json) は空のテンプレートです。コマンドやパスは自分で確認してからローカルに設定してください。
- トークン、認証情報、個人情報、端末固有のパスを Git に入れないでください。
- 外部操作・実行・承認は Mothership の外で、必ず人が判断してください。

詳しい構成は [Architecture](../architecture.md)、導入・更新・削除は [Installation and lifecycle](../installation.md)、秘密情報と権限境界は [Security model](../security.md) を参照してください。他の公開リポジトリと人が確認しながら組み合わせる場合は、[構成ガイド](../composition.md) を参照してください。

英語 README には、機能一覧、移植できるもの／ローカルに残すもの、他 OSS との組み合わせ方、FAQ をまとめています：[README](../../README.md#capabilities)。
