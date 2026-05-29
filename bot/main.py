import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import settings
from core.database import init_db
from bot.handlers import start, files, replies, grading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("Database initialized")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(files.router)
    dp.include_router(replies.router)
    dp.include_router(grading.router)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
