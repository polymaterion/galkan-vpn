"""
Tiny i18n loader. Usage:

    from bot.locales import t
    text = t("welcome", lang)
    text = t("btn_buy_new", lang, price=100)

Falls back to Russian if the language is unsupported, the key is missing,
or formatting fails (e.g. a translated string has a typo'd placeholder) —
the bot should never crash or show a raw key because of a translation gap.
"""
from __future__ import annotations

import logging

from bot.locales.ru import STRINGS as RU
from bot.locales.tk import STRINGS as TK

logger = logging.getLogger(__name__)

LOCALES: dict[str, dict[str, str]] = {"ru": RU, "tk": TK}
DEFAULT_LANG = "ru"
SUPPORTED_LANGUAGES = tuple(LOCALES.keys())


def t(key: str, lang: str | None = None, **kwargs) -> str:
    lang = lang if lang in LOCALES else DEFAULT_LANG
    template = LOCALES.get(lang, {}).get(key)
    if template is None:
        template = RU.get(key)
    if template is None:
        logger.warning("Missing locale key: %s", key)
        return key
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        logger.warning("Failed to format locale key %s for lang=%s, falling back to ru", key, lang)
        fallback = RU.get(key, key)
        try:
            return fallback.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return fallback
