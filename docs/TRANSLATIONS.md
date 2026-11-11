# Translations

The bot ships with English (`en`), Simplified Chinese (`zh`) and Japanese (`ja`).
Translations are flat JSON maps under `src/github_community_bot/locales/`.

## Adding or changing a string

1. Add the key to `en.json` first.
2. Add the same key to `zh.json` and `ja.json`.
3. Use named placeholders, never positional ones:

```json
"link.success": "Linked **{github}**! I found **{commits} commits**."
```

4. Keep formatting placeholders identical across languages. Reordering is fine:
   `"{points} 分，来自 {commits} 次提交"`.
5. Do not translate command *names* in backticks (`!link`, `!ask`). Command aliases
   live in `commands.py`.
6. Run the tests:

```bash
pytest tests/test_i18n.py -q
ruff check .
```

The key-parity test fails if a locale is missing a key. Missing keys at runtime fall
back to English, but CI should not rely on that.

## Placeholder safety

`I18n.t()` formats with a safe mapping. An unknown placeholder is left visible as
`{name}` instead of raising, and a malformed template falls back to the raw string with
a warning. This means a bad translation degrades one message, not the bot.

## Style guide

### English

- Warm, direct, plain language. Avoid corporate or overly enthusiastic tone.
- Short sentences. Prefer “Try this” over “It is recommended that you”.
- No shaming, no “should have”, no jargon without context.
- Use emoji sparingly: one at most, and not in error messages that may worry someone.

### 中文

- 使用自然、温和的简体中文，避免翻译腔和过度营销语。
- 技术名词保留通用写法：PR、issue、commit、token、Ollama。
- 命令名放在反引号里，不翻译。
- 用“你”而不是“您”，保持亲近但不过度熟络。
- 错误信息先说明发生了什么，再给出下一步。

### 日本語

- です・ます調で、やわらかく簡潔に。
- 技術用語は一般的なカタカナ表記（コミット、issue、PR、トークン）を基本とする。
- コマンド名はバッククォートのまま翻訳しない。
- 失敗を責める表現を避け、「〜してみましょう」「〜できます」を使う。
- 絵文字は 1 メッセージに 1 個まで。

## UI vs documentation

- **UI strings** live in JSON and must be available in all three languages.
- **Documentation** has English as the source of truth in `README.md` and `docs/`.
  `docs/i18n/README.zh.md` and `docs/i18n/README.ja.md` are complete quick-start
  guides, not word-for-word mirrors. When a core workflow changes, update all three.
- **Code comments and logs** are English. Logs are for operators, not end users.

## Adding a new locale

1. Create `src/github_community_bot/locales/<code>.json` by copying `en.json`.
2. Add the code to `SUPPORTED_LOCALES` and `LOCALE_LABELS` in `config.py`.
3. Add command aliases in `commands.py` if natural commands exist in that language.
4. Add a `language` command alias and update the help text where it lists the three
   languages (search for `English, 中文 and 日本語` / `English、中文和日本語`).
5. Extend the parity test to the new locale, or let it iterate `SUPPORTED_LOCALES`.
6. Add a short translated quick-start under `docs/i18n/`.
7. Smoke-test with `python -m github_community_bot --cli` and `!language <code>`.

## Review checklist

- [ ] All keys present; no English left in a translated value unless intentional.
- [ ] Placeholders unchanged and grammatically correct.
- [ ] Commands, IDs and URLs untouched.
- [ ] Tone is kind, specific and non-judgmental.
- [ ] Emoji count is modest.
- [ ] `pytest` and `ruff` pass.
- [ ] A native or fluent speaker has reviewed the Chinese/Japanese text.

Machine translation is a useful first draft; it is not a substitute for review.
