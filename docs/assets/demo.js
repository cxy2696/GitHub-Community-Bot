(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const ALIASES = {
    help: "help", "帮助": "help", "ヘルプ": "help",
    start: "start", welcome: "start", "开始": "start", "はじめ": "start",
    link: "link", link_github: "link", bind: "link", "绑定": "link", "連携": "link",
    challenge: "challenge", my_challenge: "challenge", "挑战": "challenge", "チャレンジ": "challenge",
    leaderboard: "leaderboard", lb: "leaderboard", "排行": "leaderboard", "排行榜": "leaderboard", "ランキング": "leaderboard",
    sentiment: "sentiment", tone: "sentiment", "语气": "sentiment", "感情": "sentiment", "トーン": "sentiment",
    ask: "ask", chat: "ask", "问": "ask", "質問": "ask",
    language: "language", lang: "language", "语言": "language", "言語": "language",
    privacy: "privacy", data: "privacy", "隐私": "privacy", "プライバシー": "privacy",
    about: "about", "关于": "about", "概要": "about",
    set_repo: "set_repo", repo: "set_repo", "仓库": "set_repo", "リポジトリ": "set_repo",
    refresh: "refresh", "更新": "refresh",
    shutdown: "shutdown", "关机": "shutdown", "停止": "shutdown"
  };

  const LANGUAGE_NAMES = { en: "English", zh: "中文", ja: "日本語" };

  const STRINGS = {
    en: {
      welcome: "👋 Welcome! I turn GitHub contributions into friendly momentum.\n\nTry `!link alice`, then `!challenge` and `!leaderboard`. Type `!help` for the full card.",
      help: "**GitHub Community Bot** · help\n\n**Get started**\n`!start` — quick tour\n`!link <github>` — connect GitHub\n`!challenge` — one small next step\n\n**Community**\n`!leaderboard` — top contributors\n`!sentiment <text>` — reflect on tone\n`!ask <question>` — ask the local AI\n\n**Settings**\n`!language en|zh|ja` · `!privacy` · `!about`",
      start: "**Start here**\n1. `!link <github-username>` — connect your work\n2. `!challenge` — get one concrete next step\n3. `!leaderboard` — celebrate what the community built\n\nNo tokens are needed in this browser demo.",
      linked: "Linked **{github}**! In the real bot I would find **3 commits / 2 issues / 1 PR**, worth **100 points**, and award a Bronze badge. 🎉",
      linkUsage: "Usage: `!link <github-username>`",
      challenge: "🎯 **Your next challenge**\n\nLeave one kind, specific comment on a small pull request this week. Name what works, then ask one gentle question.\n\n*Simulated reply — the real bot asks your local Ollama model.*",
      leaderboard: "🏆 **Community leaderboard**\n\n1. **Mina** (@mina-dev) — **1,240 pts** · Gold\n2. **Ken** (@kenji) — **760 pts** · Silver\n3. **Ada** (@ada) — **310 pts** · Bronze\n\nPoints: commit ×10 · issue ×20 · PR ×30.",
      sentiment: "🫶 **Tone check**\n\nThe message sounds frustrated, and the phrase “terrible idea” may put people on the defensive. That does not make the author a bad collaborator.\n\nTry separating the problem from the person, and ask one clarifying question before replying.\n\n*This is a reflection, not a judgment or a mental-health assessment.*",
      sentimentUsage: "Usage: `!sentiment <text to reflect on>`",
      ask: "Start small: read `CONTRIBUTING.md`, pick a docs or test fix, and comment on the issue to say you are taking it. Ask one clarifying question before coding — small PRs get reviewed faster.\n\n*Simulated reply. Run the bot with Ollama for a real answer.*",
      askUsage: "Ask me anything, e.g. `!ask how do I review my first PR?`",
      privacy: "🔒 **Your data, your call**\n\nThis demo stores nothing. The real bot keeps only your platform ID, display name, language, GitHub link, points and badges. No chat message bodies are stored.\n\n`!privacy optout` · `!privacy delete confirm` (DM only)",
      about: "**GitHub Community Bot** v2.1 — free, open-source community momentum for GitHub.\n\n• Local AI through Ollama\n• Discord, Slack, Telegram, Matrix + signed HTTP bridge\n• English, 中文, 日本語\n• MIT licensed",
      unknown: "I do not know `{command}` yet. Try `!help`, or ask a question with `!ask ...`.",
      freeChat: "I am a simulated preview, so I cannot call a model here. In the real bot, your local Ollama model would answer this question. Try `!help`, `!challenge` or `!leaderboard` to explore the community features.",
      language: "Done — I will reply in **English** from now on. 🌍",
      languageInvalid: "I can speak English, 中文 and 日本語. Choose one: `!language en`, `zh` or `ja`.",
      admin: "Admin commands are disabled in this browser demo. The real bot checks the per-platform admin allowlist.",
      reset: "Demo reset. Try `!help` or `!challenge`.",
      placeholder: "Type !help or say hello…"
    },
    zh: {
      welcome: "👋 欢迎！我把 GitHub 上的贡献变成社区里看得见的鼓励。\n\n试试 `!link alice`，然后 `!challenge` 和 `!leaderboard`。输入 `!help` 查看完整帮助。",
      help: "**GitHub Community Bot** · 帮助\n\n**开始使用**\n`!start` — 快速上手\n`!link <GitHub用户名>` — 绑定 GitHub\n`!challenge` — 一个具体的小目标\n\n**社区**\n`!leaderboard` — 贡献排行榜\n`!sentiment <文字>` — 一起看看语气\n`!ask <问题>` — 问问本地 AI\n\n**设置**\n`!language en|zh|ja` · `!privacy` · `!about`",
      start: "**从这里开始**\n1. `!link <GitHub用户名>` — 绑定你的贡献\n2. `!challenge` — 领取一个具体的小目标\n3. `!leaderboard` — 看看社区一起完成了什么\n\n这个网页演示不需要任何 Token。",
      linked: "已绑定 **{github}**！在真实机器人里，我会找到 **3 次提交 / 2 个 issue / 1 个 PR**，共 **100 分**，并颁发青铜徽章。🎉",
      linkUsage: "用法：`!link <GitHub用户名>`",
      challenge: "🎯 **你的下一个挑战**\n\n这周给一个小 PR 留一条具体又友善的评论：先说说哪里做得好，再温和地问一个问题。\n\n*这是模拟回复——真实机器人会询问你本地的 Ollama 模型。*",
      leaderboard: "🏆 **社区排行榜**\n\n1. **Mina**（@mina-dev）— **1,240 分** · 黄金\n2. **Ken**（@kenji）— **760 分** · 白银\n3. **Ada**（@ada）— **310 分** · 青铜\n\n积分：提交 ×10 · issue ×20 · PR ×30。",
      sentiment: "🫶 **语气小检查**\n\n这段话听起来有些沮丧，“terrible idea”这样的表达可能会让人进入防御状态。但这不代表作者是糟糕的协作者。\n\n试着把问题和人分开，回复前先问一个澄清问题。\n\n*这是语气参考，不是对人的评价，也不是心理健康诊断。*",
      sentimentUsage: "用法：`!sentiment <想一起看看的文字>`",
      ask: "从小处开始：读一读 `CONTRIBUTING.md`，挑一个文档或测试的小修复，在 issue 里留言说你想做，并在动手前问一个澄清问题。小 PR 通常更容易被 review。\n\n*这是模拟回复。用 Ollama 启动真实机器人后可以获得真实回答。*",
      askUsage: "可以这样问我：`!ask 第一次 review PR 应该看什么？`",
      privacy: "🔒 **你的数据，你做主**\n\n这个演示不保存任何数据。真实机器人只保存平台 ID、显示名、语言、GitHub 绑定、积分和徽章，不保存聊天正文。\n\n`!privacy optout` · `!privacy delete confirm`（仅私聊）",
      about: "**GitHub Community Bot** v2.1 — 为 GitHub 社区带来免费、开源的成长动力。\n\n• 通过 Ollama 使用本地 AI\n• Discord、Slack、Telegram、Matrix + 签名 HTTP 桥接\n• English、中文、日本語\n• MIT 许可证",
      unknown: "我还不会 `{command}`。试试 `!help`，或者用 `!ask ...` 提问。",
      freeChat: "这里是模拟预览，无法真的调用模型。真实机器人会让你的本地 Ollama 回答这个问题。可以先试试 `!help`、`!challenge` 或 `!leaderboard`。",
      language: "好的，接下来我会用 **中文** 回复。🌍",
      languageInvalid: "我会说 English、中文和日本語。请选一个：`!language en`、`zh` 或 `ja`。",
      admin: "网页演示中管理命令已关闭。真实机器人会检查各平台的管理员白名单。",
      reset: "演示已重置。试试 `!help` 或 `!challenge`。",
      placeholder: "输入 !help，或直接说你好…"
    },
    ja: {
      welcome: "👋 ようこそ！GitHub への貢献を、コミュニティの小さな前進として応援します。\n\n`!link alice`、`!challenge`、`!leaderboard` を試してみてください。`!help` でヘルプを表示します。",
      help: "**GitHub Community Bot** · ヘルプ\n\n**はじめに**\n`!start` — かんたんガイド\n`!link <GitHubユーザー名>` — GitHub と連携\n`!challenge` — 次の一歩\n\n**コミュニティ**\n`!leaderboard` — 貢献ランキング\n`!sentiment <文章>` — 雰囲気を一緒に確認\n`!ask <質問>` — ローカル AI に質問\n\n**設定**\n`!language en|zh|ja` · `!privacy` · `!about`",
      start: "**ここから始める**\n1. `!link <GitHubユーザー名>` — 貢献を連携\n2. `!challenge` — 具体的な次の一歩\n3. `!leaderboard` — みんなの成果を見る\n\nこのブラウザデモには Token は不要です。",
      linked: "**{github}** を連携しました！実際の Bot では **3 コミット / 2 issue / 1 PR**、**100 ポイント**を確認し、ブロンズバッジを付与します。🎉",
      linkUsage: "使い方：`!link <GitHubユーザー名>`",
      challenge: "🎯 **次のチャレンジ**\n\n今週、小さな PR に具体的で優しいコメントを一つ残してみましょう。良い点を伝えてから、やわらかく質問を一つ。\n\n*これはシミュレーションです。実際の Bot はローカルの Ollama に質問します。*",
      leaderboard: "🏆 **コミュニティランキング**\n\n1. **Mina**（@mina-dev）— **1,240 ポイント** · ゴールド\n2. **Ken**（@kenji）— **760 ポイント** · シルバー\n3. **Ada**（@ada）— **310 ポイント** · ブロンズ\n\nポイント：コミット ×10 · issue ×20 · PR ×30。",
      sentiment: "🫶 **トーンチェック**\n\n少し苛立っているように聞こえます。「terrible idea」という表現は、相手を防御的にさせるかもしれません。ただし、それは書き手が悪い協力者だという意味ではありません。\n\n問題と人を分けて考え、返信する前に確認の質問を一つしてみましょう。\n\n*これは雰囲気の参考であり、人を評価するものでも、心の健康を診断するものでもありません。*",
      sentimentUsage: "使い方：`!sentiment <一緒に確認したい文章>`",
      ask: "小さく始めましょう。`CONTRIBUTING.md` を読み、ドキュメントかテストの小さな修正を選び、issue に「やります」とコメントします。コードを書く前に確認の質問を一つ。小さな PR はレビューされやすいです。\n\n*これはシミュレーションです。Ollama で実際の Bot を起動すると本物の回答が得られます。*",
      askUsage: "こんなふうに聞けます：`!ask 初めての PR レビューでは何を見ればいい？`",
      privacy: "🔒 **あなたのデータは、あなたのもの**\n\nこのデモは何も保存しません。実際の Bot はプラットフォーム ID、表示名、言語、GitHub 連携、ポイント、バッジだけを保存し、チャット本文は保存しません。\n\n`!privacy optout` · `!privacy delete confirm`（DM のみ）",
      about: "**GitHub Community Bot** v2.1 — GitHub コミュニティに無料でオープンな弾みを。\n\n• Ollama によるローカル AI\n• Discord、Slack、Telegram、Matrix + 署名付き HTTP ブリッジ\n• English、中文、日本語\n• MIT ライセンス",
      unknown: "`{command}` はまだ分かりません。`!help` を見るか、`!ask ...` で質問してください。",
      freeChat: "ここはシミュレーションなので、実際のモデルは呼び出せません。本物の Bot ではローカルの Ollama が答えます。まずは `!help`、`!challenge`、`!leaderboard` を試してみてください。",
      language: "了解しました。これからは **日本語** で返信します。🌍",
      languageInvalid: "English・中文・日本語に対応しています。`!language en`、`zh`、`ja` から選んでください。",
      admin: "ブラウザデモでは管理コマンドは無効です。実際の Bot はプラットフォームごとの管理者許可リストを確認します。",
      reset: "デモをリセットしました。`!help` または `!challenge` を試してください。",
      placeholder: "!help と入力するか、こんにちはと話しかけてください…"
    }
  };

  const chatLog = $("#chat-log");
  const form = $("#chat-form");
  const input = $("#chat-input");
  const resetButton = $("#reset-demo");
  const shell = $("#demo-shell");

  const state = {
    lang: savedLanguage(),
    platform: "discord",
    busy: false
  };

  function readSavedLanguage() {
    try {
      return localStorage.getItem("gcb-demo-lang");
    } catch {
      return null;
    }
  }

  function saveLanguage(language) {
    try {
      saveLanguage(language);
    } catch {
      // Private browsing / storage disabled: the demo still works for this visit.
    }
  }

  function savedLanguage() {
    const saved = readSavedLanguage();
    if (saved && STRINGS[saved]) return saved;
    const browser = (navigator.language || "en").toLowerCase();
    if (browser.startsWith("zh")) return "zh";
    if (browser.startsWith("ja")) return "ja";
    return "en";
  }

  function t(key) {
    return STRINGS[state.lang][key] || STRINGS.en[key] || key;
  }

  function escapeHtml(value) {
    return value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function format(text) {
    const escaped = escapeHtml(text);
    const withCode = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
    const withBold = withCode.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    const withItalic = withBold.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    return withItalic
      .split("\n")
      .map((line) => `<span class="msg-line">${line || "&nbsp;"}</span>`)
      .join("");
  }

  function scrollToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function addMessage(role, text, { html = false } = {}) {
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role}`;
    const meta = document.createElement("span");
    meta.className = "msg-meta";
    meta.textContent = role === "user" ? "You" : "GitHub Community Bot";
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    if (html) {
      bubble.innerHTML = text;
    } else {
      bubble.textContent = text;
    }
    wrapper.append(meta, bubble);
    chatLog.append(wrapper);
    scrollToBottom();
    return wrapper;
  }

  function addTyping() {
    const wrapper = document.createElement("div");
    wrapper.className = "msg bot";
    wrapper.setAttribute("aria-hidden", "true");
    wrapper.innerHTML =
      '<div class="typing-row"><i></i><i></i><i></i></div>';
    chatLog.append(wrapper);
    scrollToBottom();
    return wrapper;
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function parseCommand(raw) {
    const text = raw.trim();
    if (!text) return null;
    let match = text.match(/^[!/]\s*(\S+)(?:\s+([\s\S]*))?$/);
    if (!match) {
      const first = text.split(/\s+/, 1)[0].toLowerCase();
      if (ALIASES[first]) {
        match = [text, first, text.slice(first.length).trim()];
      } else {
        return { name: null, args: text };
      }
    }
    const token = match[1].toLowerCase().replace(/-/g, "_").split("@")[0];
    return {
      name: ALIASES[token] || token,
      args: (match[2] || "").trim(),
      original: match[1]
    };
  }

  function replyFor(text) {
    const parsed = parseCommand(text);
    if (!parsed || !parsed.name) {
      return t("freeChat");
    }
    switch (parsed.name) {
      case "help":
        return t("help");
      case "start":
        return t("start");
      case "link":
        if (!parsed.args) return t("linkUsage");
        return t("linked").replace("{github}", escapeHtml(parsed.args.split(/\s+/)[0]));
      case "challenge":
        return t("challenge");
      case "leaderboard":
        return t("leaderboard");
      case "sentiment":
        return parsed.args ? t("sentiment") : t("sentimentUsage");
      case "ask":
        return parsed.args ? t("ask") : t("askUsage");
      case "language": {
        const requested = parsed.args.trim().toLowerCase();
        const next =
          requested === "en" || requested === "english" ? "en" :
          requested === "zh" || requested === "中文" || requested === "chinese" ? "zh" :
          requested === "ja" || requested === "日本語" || requested === "japanese" ? "ja" : null;
        if (!next) return t("languageInvalid");
        setDemoLanguage(next, { announce: false });
        return t("language");
      }
      case "about":
        return t("about");
      case "privacy":
        return t("privacy");
      case "set_repo":
      case "refresh":
      case "shutdown":
        return t("admin");
      default:
        return t("unknown").replace("{command}", escapeHtml(parsed.original || parsed.name));
    }
  }

  async function respond(text) {
    addMessage("user", text);
    const typing = addTyping();
    await sleep(380 + Math.random() * 320);
    const reply = replyFor(text);
    typing.remove();
    addMessage("bot", format(reply), { html: true });
  }

  function setBusy(value) {
    state.busy = value;
    input.disabled = value;
    form.querySelector("button").disabled = value;
  }

  function setDemoLanguage(language, { announce = true } = {}) {
    if (!STRINGS[language]) return;
    state.lang = language;
    saveLanguage(language);
    $$("[data-demo-lang]").forEach((button) => {
      const active = button.dataset.demoLang === language;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    input.placeholder = t("placeholder");
    if (announce) {
      const label = LANGUAGE_NAMES[language] || language;
      const note = document.createElement("div");
      note.className = "msg system";
      note.innerHTML = `<span class="msg-meta">${escapeHtml(label)}</span>`;
      chatLog.append(note);
      scrollToBottom();
    }
  }

  function welcome() {
    chatLog.replaceChildren();
    addMessage("bot", format(t("welcome")), { html: true });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    setBusy(true);
    try {
      await respond(text);
    } finally {
      setBusy(false);
      input.focus();
    }
  });

  $$("[data-demo-lang]").forEach((button) => {
    button.addEventListener("click", () => {
      setDemoLanguage(button.dataset.demoLang);
      input.placeholder = t("placeholder");
    });
  });

  $$(".platform-chip").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".platform-chip").forEach((chip) => {
        const active = chip === button;
        chip.classList.toggle("is-active", active);
        chip.setAttribute("aria-pressed", String(active));
      });
      state.platform = button.dataset.platform;
      shell.dataset.platform = state.platform;
      const label = button.textContent.trim();
      $("#demo-platform-label").textContent = label;
    });
  });

  $$("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.busy) return;
      input.value = button.dataset.prompt;
      form.requestSubmit();
    });
  });

  resetButton.addEventListener("click", () => {
    if (state.busy) return;
    welcome();
  });

  const copyButton = $(".copy-button");
  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      const target = document.getElementById(copyButton.dataset.copyTarget);
      if (!target) return;
      const text = target.innerText;
      try {
        await navigator.clipboard.writeText(text);
        copyButton.textContent = "Copied";
      } catch {
        const area = document.createElement("textarea");
        area.value = text;
        document.body.append(area);
        area.select();
        document.execCommand("copy");
        area.remove();
        copyButton.textContent = "Copied";
      }
      setTimeout(() => {
        copyButton.textContent = "Copy";
      }, 1800);
    });
  }

  setDemoLanguage(state.lang, { announce: false });
  welcome();
})();
