# GitHub Community Bot（日本語）

[English](../../README.md) · [中文](README.zh.md) · **日本語**

**ライブデモ / ウェブサイト：** <https://cxy2696.github.io/GitHub-Community-Bot/>

GitHub への貢献を、コミュニティの小さな前進として応援する無料・オープンソースの
セルフホスト Bot です。AI は [Ollama](https://ollama.com) でローカルに動くため、
有料 API も、チャット内容を第三者へ送ることもありません。
**Discord、Slack、Telegram、Matrix**、そして署名付き HTTP リクエストを送れる
あらゆるチャットツールに対応します。

> リポジトリは `GitHub-Discord-Bot` から `GitHub-Community-Bot` に改名されました。
> 旧リンクはリダイレクトされます。製品は Discord 専用ではありません。

---

## 2.0 で変わったこと

| 領域 | 以前 | 現在 |
| --- | --- | --- |
| AI | Gemini API キー、有料枠 | Ollama のローカル無料モデル。落ちても代替動作 |
| プラットフォーム | Discord のみ | Discord、Slack、Telegram、Matrix、HTTP ブリッジ、CLI |
| 言語 | 英語 | English / 中文 / 日本語 |
| データ | 単一テーブル、Discord ID 単位の得点 | バージョン管理された DB、GitHub 単位の共有スコア、冪等な活動台帳 |
| 運用 | `bot.py` を直接実行 | Docker、ヘルスチェック、Prometheus 指標、Webhook、バックアップ、CI |
| 安全 | 全員が停止コマンドを実行可能 | 管理者許可リスト、DM 限定の削除、リモート停止は初期状態で無効 |

## 5 分で試す（Discord / GitHub のトークン不要）

### 1. Ollama とモデルを用意

```bash
ollama serve
ollama pull qwen2.5:3b
```

`qwen2.5:3b` は英中日の三言語でバランスが良く、ノート PC でも動きます。
余裕があれば `qwen3:8b` に上げ、`OLLAMA_MODEL=qwen3:8b` を設定してください。

### 2. Bot をインストール

```bash
git clone https://github.com/cxy2696/GitHub-Community-Bot.git
cd GitHub-Community-Bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
```

デモでは HTTP サーバーを止めて、ポート 8080 を占有しないようにします。

```bash
export HTTP_ENABLED=false
python -m github_community_bot --cli
```

試してみましょう。

```text
!start
!about
!language ja
!ask 初めての PR レビューでは何を見ればいい？
!sentiment この変更はひどい。なぜ誰も対応しないのか分からない
!privacy
```

CLI も正式なアダプターです。Discord などと同じエンジン、SQLite、翻訳、Ollama
クライアントを使います。

### 3. GitHub と接続（任意）

**Metadata、Contents、Issues、Pull requests** の読み取り権限を持つ Token を作成します。
クラシック Token なら公開リポジトリは `public_repo`、非公開なら `repo` です。

```bash
GITHUB_TOKEN=ghp_...
GITHUB_REPO=cxy2696/GitHub-Community-Bot
```

CLI で `!link GitHubユーザー名`、`!leaderboard` を実行します。

## コミュニティと接続

| プラットフォーム | 接続方法 | ガイド |
| --- | --- | --- |
| **Discord** | Bot Token、スラッシュコマンド + メッセージ | [PLATFORMS.md](../PLATFORMS.md#discord) |
| **Slack** | Socket Mode、公開 URL 不要 | [PLATFORMS.md](../PLATFORMS.md#slack) |
| **Telegram** | ロングポーリング、Webhook 不要 | [PLATFORMS.md](../PLATFORMS.md#telegram) |
| **Matrix** | Client-Server `/sync` | [PLATFORMS.md](../PLATFORMS.md#matrix) |
| **その他のツール** | HMAC 署名付き JSON ブリッジ | [PLATFORMS.md](../PLATFORMS.md#bridge) |
| **ターミナル** | `--cli` | このページ |

HTTP リクエストを送れるツールなら何でも接続できます。Feishu、WeCom、LINE、Teams、
Web ウィジェット、n8n ワークフロー、自作サービスなど。正規化した JSON を送ると、
応答に Bot の返信が入ります。

### Discord の最短手順

1. <https://discord.com/developers/applications> でアプリを作成し、Bot を追加。
2. Token をコピーし、Bot 設定で **Message Content Intent** を有効化。
3. `bot` と `applications.commands` スコープで招待。
4. `.env` の `DISCORD_BOT_TOKEN` に Token を設定。
5. 自分の Discord ユーザー ID を `DISCORD_ADMIN_IDS` に設定し、起動。

```bash
python -m github_community_bot
```

スラッシュコマンド `/help`、`/ask`、`/challenge`、`/leaderboard`、`/link`、
`/language`、`/privacy`、`/status` は自動同期されます。`!help` などのプレフィックス
コマンド、DM、メンションにも対応します。

## コマンド

| コマンド | 内容 | 日本語エイリアス |
| --- | --- | --- |
| `help` | ヘルプを表示 | `ヘルプ` |
| `start` | かんたんガイド | `はじめ` |
| `link <GitHubユーザー名>` | GitHub を連携し、過去のポイントを付与 | `連携` |
| `challenge` | あなた向けの次の一歩 | `チャレンジ` |
| `leaderboard` | コミュニティランキング | `ランキング` |
| `sentiment <文章>` | メッセージの雰囲気を一緒に確認 | `トーン` |
| `ask <質問>` | ローカル AI に質問 | `質問` |
| `language en\|zh\|ja` | 言語を変更 | `言語` |
| `privacy` | データの確認・拒否・削除 | `プライバシー` |
| `status` | Bot、DB、AI、プラットフォームの状態 | `ステータス` |
| `about` | バージョンとライセンス | `概要` |
| `set_repo オーナー/リポジトリ` | 管理者：対象リポジトリを設定 | `リポジトリ` |
| `refresh` | 管理者：統計を今すぐ更新 | — |
| `unlink platform:user` | 管理者：連携を解除 | `解除` |
| `shutdown confirm` | 管理者：Bot を停止（既定では無効） | `停止` |

DM またはメンションでは、プレフィックスなしで自然に話しかけられます。
例：`@bot 初めての PR レビューでは何を見ればいい？`

### ポイントとバッジ

| 貢献 | ポイント |
| --- | --- |
| コミット | 10 |
| Issue 作成 | 20 |
| PR 作成 | 30 |

バッジ：100 でブロンズ、500 でシルバー、1,000 でゴールド。ポイントは GitHub の
身元に紐づくため、Discord と Telegram から同じ GitHub アカウントを連携しても履歴は
二重計上されません。

## AI の使い方

- `ask` / DM：コミュニティコーチとして 140 語以内で簡潔に回答。
- `challenge`：最近の活動から、今週実行できる小さな一歩を提案。
- `sentiment`：雰囲気の振り返りと建設的な次の一歩。人格の評価や心の健康の診断はしません。

システムプロンプトは、貢献者を責めないこと、リポジトリの事実を捏造しないこと、
医療・法律・危機介入の助言をしないことを指示します。引用されたコミュニティの文章は
「データ」として扱い、指示として解釈しないようにしています。

Ollama が落ちても Bot 全体は止まりません。チャレンジとトーン分析はローカルの
テンプレートで代替し、その他の機能は動き続けます。

```bash
curl -s http://127.0.0.1:11434/api/tags
curl -s http://127.0.0.1:8080/readyz
```

## 主な設定

すべての項目とコメントは [`.env.example`](../../.env.example) にあります。

| グループ | 主な変数 |
| --- | --- |
| 基本 | `BOT_NAME`、`DEFAULT_LOCALE`、`DATABASE_PATH`、`LOG_FORMAT` |
| Ollama | `OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`OLLAMA_TIMEOUT_SECONDS` |
| GitHub | `GITHUB_TOKEN`、`GITHUB_REPO`、`GITHUB_WEBHOOK_SECRET` |
| HTTP | `HTTP_HOST`、`HTTP_PORT`、`BRIDGE_SHARED_SECRET` |
| Discord | `DISCORD_BOT_TOKEN`、`DISCORD_ADMIN_IDS`、`DISCORD_CHANNEL_IDS` |
| Slack | `SLACK_BOT_TOKEN`、`SLACK_APP_TOKEN`、`SLACK_ADMIN_IDS` |
| Telegram | `TELEGRAM_BOT_TOKEN`、`TELEGRAM_ADMIN_IDS`、`TELEGRAM_CHAT_IDS` |
| Matrix | `MATRIX_HOMESERVER`、`MATRIX_USER_ID`、`MATRIX_ACCESS_TOKEN` |
| 安全 | `RATE_LIMIT_PER_MINUTE`、`MAX_AI_INPUT_CHARS`、`RETENTION_DAYS` |

設定だけを検証する場合：

```bash
python -m github_community_bot --check
```

管理コマンドは各プラットフォームの `*_ADMIN_IDS` 許可リストで制御されます。
リモート停止は既定で無効です。Ctrl+C、Docker、プロセスマネージャーで停止してください。

## Docker でまとめて起動

```bash
cp .env.example .env      # 最低 1 つのプラットフォーム Token、BRIDGE_SHARED_SECRET を設定
docker compose up -d
docker compose logs -f bot
```

Compose は Ollama を起動し、`qwen2.5:3b` を取得し、`/data` にデータを永続化します。
詳しくは [DEPLOYMENT.md](../DEPLOYMENT.md) へ。

## 運用とヘルスチェック

```bash
curl http://127.0.0.1:8080/healthz   # 稼働確認
curl http://127.0.0.1:8080/readyz    # DB + アダプターの準備状態
curl http://127.0.0.1:8080/metrics   # Prometheus 形式
```

- ログは JSON にも対応（`LOG_FORMAT=json`）。一般的な Token は自動で伏せられます。
- バックアップは `scripts/backup.sh`。SQLite のオンラインバックアップ API を使います。
- 更新は `git pull` → `pip install -e .` → 再起動。マイグレーションは起動時に自動実行。
- 運用ランブック：[OPERATIONS.md](../OPERATIONS.md)。

`/readyz` は GitHub や Ollama を呼ばないため、モデル障害でサービス全体が
ロードバランサーから外れることはありません。`/status` が AI の劣化状態を表示します。

## プライバシーと安全

- チャット本文は保存しません。保存するのはプラットフォーム ID、表示名、言語、
  GitHub 連携、ポイント、バッジです。
- `privacy delete confirm` は DM でのみ実行でき、プロフィール、連携、孤立した
  スコアと活動台帳を削除します。
- `privacy optout` は追跡とコミュニティコマンドへの応答を停止します。
- ブリッジは HMAC-SHA256 署名が必須。任意のタイムスタンプで 5 分の再生ウィンドウを
  追加できます。
- GitHub Webhook は `X-Hub-Signature-256` を検証します。
- ログは秘匿情報を伏せ、`.env` は Git と Docker の対象外です。
- `/metrics` とブリッジは内部ネットワークまたは TLS リバースプロキシの背後に置いて
  ください。

詳細：[PRIVACY.md](../PRIVACY.md)、[SECURITY.md](../../SECURITY.md)。

## v1 からの移行

1. `DISCORD_BOT_TOKEN` と `GITHUB_TOKEN` はそのまま使えます。
2. `GEMINI_API_KEY` を削除し、Ollama とモデルを用意します。
3. 新しい `data/community.db` を推奨。`!set_repo オーナー/リポジトリ` を実行し、
   メンバーに `!link` をしてもらいます。
4. 旧ランキングを残したい場合は、Bot を停止してから：

```bash
python scripts/import_v1.py --legacy user_data.db --database data/community.db --dry-run
# 確認後、--dry-run を外して実行
```

インポートは旧ポイントをベースラインとして使い、v2 で既に高いスコアを下げません。
詳細：[MIGRATION.md](../MIGRATION.md)。

## 構成とコントリビューション

```text
src/github_community_bot/
  bot.py            プラットフォーム非依存のエンジンとコマンド
  storage.py        SQLite + バージョン付きマイグレーション
  services/ai.py    Ollama クライアント、プロンプト、会話メモリ
  services/github.py GitHub 読み取りとポーリング
  platforms/        Discord / Slack / Telegram / Matrix / HTTP / CLI
  locales/          en.json / zh.json / ja.json
tests/              60 以上のオフラインテスト
```

コントリビューションは歓迎です。まず [CONTRIBUTING.md](../../CONTRIBUTING.md)、
翻訳は [TRANSLATIONS.md](../TRANSLATIONS.md)、予定は
[ROADMAP.md](../ROADMAP.md) をご覧ください。

## ライセンス

MIT。[LICENSE](../../LICENSE) を参照。オリジナルは
[cxy2696](https://github.com/cxy2696) によるものです。Ollama と選択したモデルには
それぞれのライセンスがあり、商用利用の前にモデルカードを確認してください。
