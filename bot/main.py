"""
Telegram bot entry point.
Uses aiogram 3 in polling mode (no webhook needed for MVP).
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers.admin_handlers import router as admin_router
from bot.handlers.main_handlers import router as main_router
from bot.middlewares.language import LanguageMiddleware

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


async def main():
    bot = Bot(
        token=settings.TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    lang_mw = LanguageMiddleware()
    dp.message.middleware(lang_mw)
    dp.callback_query.middleware(lang_mw)

    dp.include_router(main_router)
    dp.include_router(admin_router)

    logger.info("Bot starting (polling mode)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
