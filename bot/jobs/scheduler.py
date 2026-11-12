import asyncio
import logging

from bot import db
from bot.services.draw import draw


async def run(bot):
    while True:
        try:
            if db.pool is None:
                logging.warning("Database pool is not ready. Retrying...")
                await asyncio.sleep(5)
                continue

            async with db.pool.acquire() as connection:
                rows = await connection.fetch(
                    """
                    SELECT id
                    FROM giveaways
                    WHERE status = 'active'
                    AND ends <= now()
                    """
                )

            for row in rows:
                giveaway_id = row["id"]

                try:
                    await draw(bot, giveaway_id)
                except Exception:
                    logging.exception(
                        "Draw failed for giveaway %s",
                        giveaway_id,
                    )

        except Exception:
            logging.exception("Scheduler error")

        await asyncio.sleep(30)
