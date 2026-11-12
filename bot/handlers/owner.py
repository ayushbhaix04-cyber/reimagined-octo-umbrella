from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import db
from bot.config import OWNER_ID
from bot.services.logs import audit

router = Router()


def owner_only(function):
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id != OWNER_ID:
            return await message.answer("❌ Owner only command.")

        return await function(message, *args, **kwargs)

    return wrapper


@router.message(Command("globalchannel"))
@owner_only
async def add_global_channel(
    message: Message,
    command: CommandObject,
    bot: Bot,
):
    args = (command.args or "").split(maxsplit=1)

    if len(args) < 2:
        return await message.answer(
            "Usage: /globalchannel CHANNEL_ID INVITE_LINK"
        )

    channel_id = int(args[0])
    invite_link = args[1]

    async with db.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO global_channels
            (chat_id, title, link)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id)
            DO UPDATE SET link = $3, title = $2
            """,
            channel_id,
            args[0],
            invite_link,
        )

    await audit(
        bot,
        "GLOBAL_CHANNEL_ADDED",
        message.from_user.id,
        0,
        args[0],
    )

    await message.answer("✅ Global channel added.")


@router.message(Command("removeglobalchannel"))
@owner_only
async def remove_global_channel(
    message: Message,
    command: CommandObject,
    bot: Bot,
):
    channel_id = int(command.args or 0)

    async with db.pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM global_channels WHERE chat_id = $1",
            channel_id,
        )

    await audit(
        bot,
        "GLOBAL_CHANNEL_REMOVED",
        message.from_user.id,
        0,
        str(channel_id),
    )

    await message.answer("✅ Global channel removed.")


@router.message(Command("platformstats"))
@owner_only
async def platform_stats(message: Message):
    async with db.pool.acquire() as connection:
        giveaway_count = await connection.fetchval(
            "SELECT COUNT(*) FROM giveaways"
        )

        participant_count = await connection.fetchval(
            "SELECT COUNT(*) FROM participants"
        )

    await message.answer(
        f"📊 <b>Platform Stats</b>\n\n"
        f"🎁 Giveaways: {giveaway_count}\n"
        f"👥 Participants: {participant_count}"
    )


@router.message(Command("winner"))
@owner_only
async def fixed_winner(
    message: Message,
    command: CommandObject,
    bot: Bot,
):
    args = (command.args or "").split()

    if len(args) < 2:
        return await message.answer(
            "Usage: /winner GIVEAWAY_ID USER_ID [reason]"
        )

    giveaway_id = int(args[0])
    user_id = int(args[1])
    reason = " ".join(args[2:])

    async with db.pool.acquire() as connection:
        async with connection.transaction():
            giveaway = await connection.fetchrow(
                """
                SELECT * FROM giveaways
                WHERE id = $1
                FOR UPDATE
                """,
                giveaway_id,
            )

            if not giveaway:
                return await message.answer(
                    "❌ Giveaway not found."
                )

            participant = await connection.fetchrow(
                """
                SELECT 1
                FROM participants
                WHERE giveaway = $1
                AND user_id = $2
                """,
                giveaway_id,
                user_id,
            )

            if not participant:
                return await message.answer(
                    "⚠️ User is not a participant."
                )

            round_number = await connection.fetchval(
                """
                SELECT COALESCE(MAX(round), 0) + 1
                FROM winners
                WHERE giveaway = $1
                """,
                giveaway_id,
            )

            await connection.execute(
                """
                INSERT INTO winners
                (giveaway, user_id, round, selection, reason)
                VALUES ($1, $2, $3, 'fixed', $4)
                """,
                giveaway_id,
                user_id,
                round_number,
                reason,
            )

            await connection.execute(
                "UPDATE giveaways SET status = 'ended' WHERE id = $1",
                giveaway_id,
            )

    await audit(
        bot,
        "FIXED_WINNER",
        message.from_user.id,
        giveaway_id,
        f"user={user_id} reason={reason}",
    )

    await message.answer(
        f"✅ Fixed winner set: <code>{user_id}</code>\n"
        f"Giveaway: <code>{giveaway_id}</code>"
    )
