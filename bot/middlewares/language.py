"""
Fetches the user's saved language (via billing API) once per incoming
update and injects it into handler kwargs as `lang`. Handlers that need it
just declare `lang: str` in their signature — aiogram 3 fills it from data.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.billing_client import billing_client
from bot.locales import DEFAULT_LANG

logger = logging.getLogger(__name__)


class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        lang = DEFAULT_LANG
        user = data.get("event_from_user")
        if user:
            try:
                lang = await billing_client.get_user_language(user.id)
            except Exception as e:
                logger.warning("Failed to fetch language for %s: %s", user.id, e)
        data["lang"] = lang
        return await handler(event, data)
