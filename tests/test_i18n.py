from __future__ import annotations

from github_community_bot.i18n import I18n, detect_locale, normalize_locale, resolve_locale


def test_catalogs_are_complete(i18n: I18n) -> None:
    assert set(i18n.available) == {"en", "zh", "ja"}
    for locale in ("zh", "ja"):
        assert i18n.missing_keys(locale) == set()


def test_translation_fallback_and_formatting(i18n: I18n) -> None:
    assert i18n.t("link.usage", "zh", prefix="!").startswith("用法")
    assert i18n.t("missing.key", "ja") == "missing.key"
    assert i18n.t("help.title", "fr", bot_name="Bot") == "**Bot** · help"


def test_locale_detection() -> None:
    assert detect_locale("こんにちは、調子はどう？") == "ja"
    assert detect_locale("你好，今天怎么样？") == "zh"
    assert detect_locale("Hello there") is None
    assert normalize_locale("zh-CN") == "zh"
    assert normalize_locale("ja_JP") == "ja"
    assert normalize_locale("de") is None


def test_locale_resolution_priority() -> None:
    assert resolve_locale("ja", "en-US", "你好", "en") == "ja"
    assert resolve_locale(None, "zh-CN", "Hello", "en") == "zh"
    assert resolve_locale(None, None, "こんにちは", "en") == "ja"
    assert resolve_locale(None, None, "Hello", "en") == "en"
