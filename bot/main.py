import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot import db
from bot.config import BOT_TOKEN, REDIS_URL
from bot.handlers import user, host, owner, chat_activity
from bot.jobs.scheduler import run as scheduler


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logging.info("Initializing database...")

    try:
        await db.init()
        logging.info("Database initialized successfully.")
    except Exception:
        logging.exception("Database initialization failed")
        raise

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(
        storage=RedisStorage.from_url(REDIS_URL)
    )

    dp.include_router(chat_activity.router)
    dp.include_router(user.router)
    dp.include_router(host.router)
    dp.include_router(owner.router)

    scheduler_task = asyncio.create_task(scheduler(bot))

    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
