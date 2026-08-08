# Mothership 日本語ガイド

[English README](../../README.md) · [設計](../architecture.md) · [導入と更新](../installation.md) · [安全モデル](../security.md)

Mothership は、AI 支援の開発ハーネスを安全に確認・配布するためのローカル基盤です。契約の検証、助言的なルーティング、ローカル診断、設定テンプレートを提供しますが、実行権限を与えたり、外部操作を自動で行ったりはしません。

![暗い星空を進むクジラ型の母船](../../assets/mothership-banner.png)

## はじめ方

Python 3.12 以上が必要です。

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git
cd mothership
python3 --version
./bootstrap/doctor.sh
python3 -m unittest discover -s tests -v
```

`doctor.sh` は、固定されたローカルアダプターの利用可否を確認するだけです。ソフトウェアの導入、認証、モデル呼び出し、設定変更、フックの追加は行いません。アダプターが未導入なら診断は非ゼロ終了になりますが、それは診断結果です。

## 安全な使い方

- [`config/executors.example.json`](../../config/executors.example.json) は空のテンプレートです。コマンドやパスは自分で確認してからローカルに設定してください。
- トークン、認証情報、個人情報、端末固有のパスを Git に入れないでください。
- 外部操作・実行・承認は Mothership の外で、必ず人が判断してください。

詳しい構成は [Architecture](../architecture.md)、導入・更新・削除は [Installation and lifecycle](../installation.md)、秘密情報と権限境界は [Security model](../security.md) を参照してください。
