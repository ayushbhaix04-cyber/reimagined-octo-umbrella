from bot.config import LOG_CHANNEL_ID,DISCOVERY_CHANNEL_ID
from aiogram import Bot
async def audit(bot:Bot,action,actor,giveaway,details=""):
    from bot.db import pool
    async with pool.acquire() as c:
        await c.execute("INSERT INTO audit(action,actor,giveaway,details) VALUES($1,$2,$3,$4)",action,actor,giveaway,details)
    if LOG_CHANNEL_ID:
        try: await bot.send_message(LOG_CHANNEL_ID,f"🛡 {action} | actor {actor} | giveaway {giveaway}\n{details[:1500]}")
        except Exception: pass
async def discover(bot:Bot,text,button=None):
    if DISCOVERY_CHANNEL_ID:
        try: return await bot.send_message(DISCOVERY_CHANNEL_ID,text,reply_markup=button)
        except Exception: return None
