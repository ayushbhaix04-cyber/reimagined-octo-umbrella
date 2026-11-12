from aiogram import Bot

from bot import db
from bot.config import LOG_CHANNEL_ID, DISCOVERY_CHANNEL_ID


async def audit(
    bot: Bot,
    action: str,
    actor_id: int | None,
    giveaway_id: int | None,
    details: str = "",
):
    async with db.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO audit
            (action, actor, giveaway, details)
            VALUES ($1, $2, $3, $4)
            """,
            action,
            actor_id,
            giveaway_id,
            details,
        )

    if LOG_CHANNEL_ID:
        try:
            await bot.send_message(
                LOG_CHANNEL_ID,
                f"🛡 <b>{action}</b>\n\n"
                f"🆔 Giveaway: <code>{giveaway_id}</code>\n"
                f"👤 Actor: <code>{actor_id}</code>\n"
                f"📝 {details}",
            )
        except Exception:
            pass


async def discover(
    bot: Bot,
    text: str,
    button=None,
):
    if not DISCOVERY_CHANNEL_ID:
        return None

    try:
        return await bot.send_message(
            DISCOVERY_CHANNEL_ID,
            text,
            reply_markup=button,
        )
    except Exception:
        return None
