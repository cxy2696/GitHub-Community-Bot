"""Small, dependency-free internationalisation layer.

Catalogs are flat JSON files with named placeholders. Missing keys fall back to
English (and then to the key itself) so a partially translated catalog can
never crash the bot. Locale detection is intentionally lightweight: an explicit
user setting wins, then the platform hint, then a quick script check.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .config import LOCALE_LABELS, SUPPORTED_LOCALES

logger = logging.getLogger(__name__)

_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class _SafeDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:  # pragma: no cover - tiny helper
        return "{" + key + "}"


class I18n:
    def __init__(self, locale_dir: Path | None = None) -> None:
        self.locale_dir = locale_dir or Path(__file__).parent / "locales"
        self._catalogs: dict[str, dict[str, str]] = {}
        self.reload()

    def reload(self) -> None:
        catalogs: dict[str, dict[str, str]] = {}
        for locale in SUPPORTED_LOCALES:
            path = self.locale_dir / f"{locale}.json"
            if not path.exists():
                raise FileNotFoundError(f"Missing locale file: {path}")
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in data.items()
            ):
                raise ValueError(f"Locale file must be a flat string map: {path}")
            catalogs[locale] = data
        if "en" not in catalogs:
            raise ValueError("An English locale catalog is required")
        self._catalogs = catalogs

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(self._catalogs)

    def missing_keys(self, locale: str) -> set[str]:
        """Return keys present in English but missing from ``locale``."""
        reference = set(self._catalogs["en"])
        return reference - set(self._catalogs.get(locale, {}))

    def t(self, key: str, locale: str = "en", **values: Any) -> str:
        normalized = normalize_locale(locale) or "en"
        template = (
            self._catalogs.get(normalized, {}).get(key) or self._catalogs["en"].get(key) or key
        )
        try:
            return template.format_map(_SafeDict(values))
        except (KeyError, ValueError):
            logger.warning("Bad locale template for %s/%s", normalized, key)
            return template

    def language_name(self, locale: str) -> str:
        return LOCALE_LABELS.get(normalize_locale(locale) or "en", "English")


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    primary = value.strip().lower().replace("_", "-").split("-")[0]
    return primary if primary in SUPPORTED_LOCALES else None


def detect_locale(text: str) -> str | None:
    """Detect Japanese/Chinese from script, otherwise return ``None``."""
    if not text:
        return None
    if _KANA.search(text):
        return "ja"
    if len(_HAN.findall(text)) >= 2:
        return "zh"
    return None


def resolve_locale(
    preference: str | None,
    hint: str | None,
    text: str,
    default: str = "en",
) -> str:
    """Pick the best locale for a reply.

    Priority: saved user preference → platform hint → message script → default.
    """

    return (
        normalize_locale(preference)
        or normalize_locale(hint)
        or detect_locale(text)
        or normalize_locale(default)
        or "en"
    )
