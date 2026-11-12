import asyncio,logging
from bot.db import pool
from bot.services.draw import draw
from bot.services.logs import audit
async def run(bot):
    while True:
        try:
            async with pool.acquire() as c:
                rows=await c.fetch("SELECT id FROM giveaways WHERE status='active' AND ends<=now()")
            for r in rows:
                try: await draw(bot,r["id"])
                except Exception: logging.exception("draw failed")
        except Exception: logging.exception("scheduler error")
        await asyncio.sleep(30)
