# GitHub Community Bot（中文）

[English](../../README.md) · **中文** · [日本語](README.ja.md)

**在线演示与官网：** <https://cxy2696.github.io/GitHub-Community-Bot/>

一个免费、开源、可自托管的社区机器人：把 GitHub 上的贡献变成社区里看得见的鼓励。
AI 通过 [Ollama](https://ollama.com) 在本地运行，不需要付费 API，也不把聊天内容交给第三方。
支持 **Discord、Slack、Telegram、Matrix**，以及任何能发送签名 HTTP 请求的聊天软件。

> 仓库已从 `GitHub-Discord-Bot` 更名为 `GitHub-Community-Bot`，旧链接会自动跳转；产品已经不再局限于 Discord。

---

## 2.0 带来了什么

| 方面 | 以前 | 现在 |
| --- | --- | --- |
| AI | Gemini API Key，有付费额度 | Ollama 本地免费模型，模型离线也能降级工作 |
| 平台 | 仅 Discord | Discord、Slack、Telegram、Matrix、HTTP 桥接、命令行 |
| 语言 | 英文 | English / 中文 / 日本語 |
| 数据 | 单表、按 Discord ID 记分 | 版本化数据库、按 GitHub 身份共享积分、幂等活动账本 |
| 运维 | 直接运行 `bot.py` | Docker、健康检查、Prometheus 指标、Webhook、备份、CI |
| 安全 | 所有人都能关机 | 管理员白名单、仅私聊删除、默认禁用远程关机 |

## 5 分钟本地演示（不需要 Discord / GitHub Token）

### 1. 安装 Ollama 和模型

```bash
ollama serve
ollama pull qwen2.5:3b
```

`qwen2.5:3b` 对中英日三语比较均衡，适合笔记本。内存充足可以换
`qwen3:8b`，并设置 `OLLAMA_MODEL=qwen3:8b`。

### 2. 安装机器人

```bash
git clone https://github.com/cxy2696/GitHub-Community-Bot.git
cd GitHub-Community-Bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
```

演示时先关闭 HTTP 服务，避免占用 8080 端口：

```bash
export HTTP_ENABLED=false
python -m github_community_bot --cli
```

可以试试：

```text
!start
!about
!language zh
!ask 第一次给开源项目提 PR，应该先做什么？
!sentiment 这个改动太糟糕了，我不明白为什么还没人处理
!privacy
```

命令行也是正式适配器，和 Discord 等平台共用同一套引擎、数据库、翻译和 Ollama 客户端。

### 3. 连接 GitHub（可选）

创建一个只读 Token，权限包含 **Metadata、Contents、Issues、Pull requests**；经典
Token 可用 `public_repo`（私有仓库用 `repo`）。

```bash
GITHUB_TOKEN=ghp_...
GITHUB_REPO=cxy2696/GitHub-Community-Bot
```

然后在命令行里运行 `!link 你的GitHub用户名` 和 `!leaderboard`。

## 连接社区

| 平台 | 接入方式 | 指南 |
| --- | --- | --- |
| **Discord** | Bot Token，斜杠命令 + 消息 | [PLATFORMS.md](../PLATFORMS.md#discord) |
| **Slack** | Socket Mode，无需公网地址 | [PLATFORMS.md](../PLATFORMS.md#slack) |
| **Telegram** | 长轮询，无需 Webhook | [PLATFORMS.md](../PLATFORMS.md#telegram) |
| **Matrix** | Client-Server `/sync` | [PLATFORMS.md](../PLATFORMS.md#matrix) |
| **其他所有软件** | 带 HMAC 签名的 JSON 桥接 | [PLATFORMS.md](../PLATFORMS.md#bridge) |
| **终端** | `--cli` | 本文 |

任何能发 HTTP 请求的软件都可以通过桥接接入：飞书、企业微信、LINE、Teams、网页小组件、
n8n 工作流，或者你自己写的服务。它发送一条标准化 JSON，机器人在响应里返回回复。

### Discord 快速步骤

1. 打开 <https://discord.com/developers/applications>，新建应用并添加 Bot。
2. 复制 Token，在 Bot 设置里开启 **Message Content Intent**。
3. 用 `bot` + `applications.commands` 权限邀请机器人。
4. 把 Token 写入 `.env` 的 `DISCORD_BOT_TOKEN`。
5. 把你的 Discord 用户 ID 写入 `DISCORD_ADMIN_IDS`，然后运行：

```bash
python -m github_community_bot
```

斜杠命令会自动同步：`/help`、`/ask`、`/challenge`、`/leaderboard`、`/link`、
`/language`、`/privacy`、`/status`。也支持 `!help` 这类前缀命令、私聊和 @机器人。

## 命令一览

| 命令 | 作用 | 中文别名 |
| --- | --- | --- |
| `help` | 显示帮助 | `帮助` |
| `start` | 快速上手 | `开始` |
| `link <GitHub用户名>` | 绑定 GitHub，补上历史积分 | `绑定` |
| `challenge` | 获得一个专属小目标 | `挑战` |
| `leaderboard` | 社区排行榜 | `排行榜` |
| `sentiment <文字>` | 一起看看语气 | `语气` |
| `ask <问题>` | 询问本地 AI | `问` |
| `language en\|zh\|ja` | 切换语言 | `语言` |
| `privacy` | 查看 / 退出 / 删除数据 | `隐私` |
| `status` | 机器人、数据库、AI、平台状态 | `状态` |
| `about` | 版本与许可证 | `关于` |
| `set_repo 所有者/仓库` | 管理员：设置仓库 | `仓库` |
| `refresh` | 管理员：立即刷新统计 | `更新` |
| `unlink platform:user` | 管理员：解除绑定 | `解除` |
| `shutdown confirm` | 管理员：停止机器人（默认禁用） | `关机` |

私聊或 @机器人 时，可以不加前缀直接说话，例如：
`@机器人 第一次 review PR 应该看什么？`

### 积分与徽章

| 贡献 | 积分 |
| --- | --- |
| Commit | 10 |
| 新建 Issue | 20 |
| 新建 PR | 30 |

徽章：100 分青铜、500 分白银、1000 分黄金。积分属于 GitHub 身份，不属于聊天账号；
同一个人从 Discord 和 Telegram 绑定同一个 GitHub 账号，不会重复计算历史积分。

## AI 如何工作

- `ask` / 私聊：本地模型用社区教练语气回答，控制在 140 字以内。
- `challenge`：根据近期活动给一个具体、本周可完成的小目标。
- `sentiment`：只做语气反思，不做人格判断，也不做心理健康诊断。

系统提示会要求模型不羞辱贡献者、不编造仓库事实、不提供医疗/法律建议，并把用户引用的
社区文字当作数据而不是指令。机器人只发送当前问题或待分析文字，不会上传数据库、Token
或聊天记录。

Ollama 掉线时，机器人不会整体崩溃：挑战和语气分析会使用本地模板，其他功能照常工作。

```bash
curl -s http://127.0.0.1:11434/api/tags
curl -s http://127.0.0.1:8080/readyz
```

## 主要配置

完整注释见 [`.env.example`](../../.env.example)。

| 分组 | 关键变量 |
| --- | --- |
| 核心 | `BOT_NAME`、`DEFAULT_LOCALE`、`DATABASE_PATH`、`LOG_FORMAT` |
| Ollama | `OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`OLLAMA_TIMEOUT_SECONDS` |
| GitHub | `GITHUB_TOKEN`、`GITHUB_REPO`、`GITHUB_WEBHOOK_SECRET` |
| HTTP | `HTTP_HOST`、`HTTP_PORT`、`BRIDGE_SHARED_SECRET` |
| Discord | `DISCORD_BOT_TOKEN`、`DISCORD_ADMIN_IDS`、`DISCORD_CHANNEL_IDS` |
| Slack | `SLACK_BOT_TOKEN`、`SLACK_APP_TOKEN`、`SLACK_ADMIN_IDS` |
| Telegram | `TELEGRAM_BOT_TOKEN`、`TELEGRAM_ADMIN_IDS`、`TELEGRAM_CHAT_IDS` |
| Matrix | `MATRIX_HOMESERVER`、`MATRIX_USER_ID`、`MATRIX_ACCESS_TOKEN` |
| 安全 | `RATE_LIMIT_PER_MINUTE`、`MAX_AI_INPUT_CHARS`、`RETENTION_DAYS` |

只检查配置、不启动：

```bash
python -m github_community_bot --check
```

管理命令由各平台的 `*_ADMIN_IDS` 白名单控制。远程关机默认关闭，推荐用 Ctrl+C、Docker
或进程管理器停止服务。

## Docker 一键运行

```bash
cp .env.example .env      # 至少填一个平台 Token；设置 BRIDGE_SHARED_SECRET
docker compose up -d
docker compose logs -f bot
```

Compose 会启动 Ollama、拉取 `qwen2.5:3b`，并用 `/data` 持久化数据库。详见
[DEPLOYMENT.md](../DEPLOYMENT.md)。

## 运维与健康检查

```bash
curl http://127.0.0.1:8080/healthz   # 存活
curl http://127.0.0.1:8080/readyz    # 数据库 + 适配器就绪
curl http://127.0.0.1:8080/metrics   # Prometheus 文本指标
```

- 日志支持 JSON（`LOG_FORMAT=json`），并自动脱敏常见 Token。
- 备份：`scripts/backup.sh` 使用 SQLite 在线备份 API，运行中也能安全备份。
- 升级：`git pull` → `pip install -e .` → 重启；启动时自动执行增量迁移。
- 运行手册：[OPERATIONS.md](../OPERATIONS.md)。

`/readyz` 不会调用 GitHub 或 Ollama，所以模型故障不会让整个服务被负载均衡摘除；`/status`
会明确告诉你 AI 处于降级状态。

## 隐私与安全

- 不保存聊天正文，只保存平台 ID、显示名、语言、GitHub 绑定、积分和徽章。
- `privacy delete confirm` 只能在私聊执行，删除资料、绑定和孤立的积分/活动记录。
- `privacy optout` 会停止跟踪和回应社区命令，直到 `privacy optin`。
- 桥接接口必须配置 HMAC-SHA256 签名；可选时间戳提供 5 分钟重放窗口。
- GitHub Webhook 校验 `X-Hub-Signature-256`。
- 日志脱敏；`.env` 被 Git 和 Docker 忽略。
- 建议把 `/metrics` 和桥接接口放在内网或 TLS 反向代理后面。

详见 [PRIVACY.md](../PRIVACY.md) 与 [SECURITY.md](../../SECURITY.md)。

## 从 v1 迁移

1. 保留 `DISCORD_BOT_TOKEN` 和 `GITHUB_TOKEN`。
2. 删除 `GEMINI_API_KEY`，安装 Ollama 并拉取模型。
3. 推荐使用全新的 `data/community.db`，运行 `!set_repo 所有者/仓库`，让成员重新 `!link`。
4. 如果想保留旧排行榜，先停机器人，再运行：

```bash
python scripts/import_v1.py --legacy user_data.db --database data/community.db --dry-run
# 确认后去掉 --dry-run
```

导入脚本会把旧积分作为基线，不会降低 v2 中已有的分数。详见
[MIGRATION.md](../MIGRATION.md)。

## 项目结构与贡献

```text
src/github_community_bot/
  bot.py            平台无关的引擎与命令
  storage.py        SQLite + 版本化迁移
  services/ai.py    Ollama 客户端、提示词与内存对话
  services/github.py GitHub 读取与轮询
  platforms/        Discord / Slack / Telegram / Matrix / HTTP / CLI
  locales/          en.json / zh.json / ja.json
tests/              70+ 离线测试
```

欢迎贡献：先读 [CONTRIBUTING.md](../../CONTRIBUTING.md)，翻译规范见
[TRANSLATIONS.md](../TRANSLATIONS.md)，路线图见 [ROADMAP.md](../ROADMAP.md)。

## 许可证

MIT，见 [LICENSE](../../LICENSE)。最初由 [cxy2696](https://github.com/cxy2696) 创建。
Ollama 和你选择的模型有各自的许可证，商用前请查看模型卡。
