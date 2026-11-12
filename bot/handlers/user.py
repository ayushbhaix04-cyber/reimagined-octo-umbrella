from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from bot import db
from bot.config import SUPPORT_USERNAME
from bot.services.redis import (
    new_captcha,
    check_captcha,
    captcha_cooldown,
    set_cooldown,
    lock,
    unlock,
)
from bot.services.channels import is_member
from bot.services.logs import audit, discover

router = Router()

MENU = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎁 Browse Giveaways",
                callback_data="browse",
            )
        ],
        [
            InlineKeyboardButton(
                text="🚀 Create Giveaway",
                callback_data="host_create",
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 My Entries",
                callback_data="my_entries",
            )
        ],
        [
            InlineKeyboardButton(
                text="🆘 Support",
                url=f"https://t.me/{SUPPORT_USERNAME}",
            )
        ],
    ]
)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject):
    async with db.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO users (tg_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (tg_id)
            DO UPDATE SET username = $2
            """,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )

        if command.args and command.args.startswith("ref_"):
            try:
                _, giveaway_id, referrer_id = command.args.split("_")
                giveaway_id = int(giveaway_id)
                referrer_id = int(referrer_id)

                if referrer_id != message.from_user.id:
                    await connection.execute(
                        """
                        INSERT INTO referrals
                        (giveaway, referrer, invited)
                        VALUES ($1, $2, $3)
                        ON CONFLICT DO NOTHING
                        """,
                        giveaway_id,
                        referrer_id,
                        message.from_user.id,
                    )
            except Exception:
                pass

    await message.answer(
        "🎉 <b>Welcome to GiveawayX</b>\n\n"
        "Participate in giveaways, invite friends, or create your own giveaway.\n\n"
        f"👤 User: @{message.from_user.username or message.from_user.first_name}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>",
        reply_markup=MENU,
    )


@router.callback_query(F.data == "browse")
async def browse(callback: CallbackQuery):
    async with db.pool.acquire() as connection:
        giveaways = await connection.fetch(
            """
            SELECT id, title, prize
            FROM giveaways
            WHERE status = 'active'
            AND ends > now()
            ORDER BY id DESC
            LIMIT 10
            """
        )

    if not giveaways:
        return await callback.message.edit_text(
            "No active giveaways right now."
        )

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🎁 {giveaway['title']}",
                callback_data=f"view:{giveaway['id']}",
            )
        ]
        for giveaway in giveaways
    ]

    buttons.append(
        [
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data="main",
            )
        ]
    )

    await callback.message.edit_text(
        "🔥 <b>Active Giveaways</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data == "main")
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎉 <b>Main Menu</b>",
        reply_markup=MENU,
    )


@router.callback_query(F.data.startswith("view:"))
async def view_giveaway(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[1])

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT * FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        channels = await connection.fetch(
            """
            SELECT * FROM giveaway_channels
            WHERE giveaway = $1
            """,
            giveaway_id,
        )

    if not giveaway:
        return await callback.answer(
            "Giveaway not found.",
            show_alert=True,
        )

    text = (
        f"🎁 <b>{giveaway['title']}</b>\n\n"
        f"🏆 Prize: {giveaway['prize']}\n"
        f"👥 Winners: {giveaway['winners']}\n"
        f"🆔 Giveaway ID: <code>{giveaway['id']}</code>\n\n"
        f"{giveaway['description'] or ''}"
    )

    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Participate",
                callback_data=f"join:{giveaway_id}",
            )
        ]
    ]

    for channel in channels:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {channel['title'] or 'Join Channel'}",
                    url=channel["link"],
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data="browse",
            )
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("join:"))
async def join_giveaway(callback: CallbackQuery, bot: Bot):
    giveaway_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    lock_key = f"join:{giveaway_id}:{user_id}"

    if not await lock(lock_key):
        return await callback.answer(
            "Please wait...",
            show_alert=True,
        )

    try:
        async with db.pool.acquire() as connection:
            giveaway = await connection.fetchrow(
                """
                SELECT * FROM giveaways
                WHERE id = $1
                AND status = 'active'
                AND ends > now()
                """,
                giveaway_id,
            )

            channels = await connection.fetch(
                """
                SELECT * FROM giveaway_channels
                WHERE giveaway = $1
                AND required = TRUE
                """,
                giveaway_id,
            )

            global_channels = await connection.fetch(
                """
                SELECT * FROM global_channels
                WHERE active = TRUE
                """
            )

        if not giveaway:
            return await callback.answer(
                "Giveaway is not active.",
                show_alert=True,
            )

        for channel in list(global_channels) + list(channels):
            if not await is_member(
                bot,
                channel["chat_id"],
                user_id,
            ):
                return await callback.answer(
                    f"Join {channel['title'] or channel['chat_id']} first.",
                    show_alert=True,
                )

        if await captcha_cooldown(giveaway_id, user_id):
            return await callback.answer(
                "Captcha cooldown active. Try again later.",
                show_alert=True,
            )

        first_number, second_number = await new_captcha(
            giveaway_id,
            user_id,
        )

        await callback.message.edit_text(
            "🤖 <b>Human Verification</b>\n\n"
            f"Solve: <b>{first_number} + {second_number} = ?</b>\n\n"
            f"Reply:\n<code>/captcha {giveaway_id} ANSWER</code>\n\n"
            "⏳ Expires in 3 minutes."
        )

    finally:
        await unlock(lock_key)


@router.message(Command("captcha"))
async def captcha(message: Message, command: CommandObject):
    try:
        giveaway_id, answer = command.args.split()
        giveaway_id = int(giveaway_id)
    except Exception:
        return await message.answer(
            "Usage: /captcha GIVEAWAY_ID ANSWER"
        )

    if await captcha_cooldown(giveaway_id, message.from_user.id):
        return await message.answer(
            "⏳ Captcha cooldown active. Try again later."
        )

    if await check_captcha(
        giveaway_id,
        message.from_user.id,
        answer,
    ):
        async with db.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO participants
                (giveaway, user_id, captcha)
                VALUES ($1, $2, TRUE)
                ON CONFLICT (giveaway, user_id)
                DO UPDATE SET captcha = TRUE
                """,
                giveaway_id,
                message.from_user.id,
            )

            referral = await connection.fetchrow(
                """
                SELECT referrer
                FROM referrals
                WHERE giveaway = $1
                AND invited = $2
                AND valid = FALSE
                """,
                giveaway_id,
                message.from_user.id,
            )

            if referral:
                await connection.execute(
                    """
                    UPDATE referrals
                    SET valid = TRUE
                    WHERE giveaway = $1
                    AND invited = $2
                    """,
                    giveaway_id,
                    message.from_user.id,
                )

                referral_count = await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM referrals
                    WHERE giveaway = $1
                    AND referrer = $2
                    AND valid = TRUE
                    """,
                    giveaway_id,
                    referral["referrer"],
                )

                giveaway = await connection.fetchrow(
                    "SELECT * FROM giveaways WHERE id = $1",
                    giveaway_id,
                )

                if referral_count <= giveaway["referral_cap"]:
                    await connection.execute(
                        """
                        UPDATE participants
                        SET referral_entries = referral_entries + $2,
                        total_entries = total_entries + $2
                        WHERE giveaway = $1
                        AND user_id = $3
                        """,
                        giveaway_id,
                        giveaway["referral_bonus"],
                        referral["referrer"],
                    )

        await message.answer(
            "✅ <b>Captcha verified!</b>\n\n"
            "You are now participating.\n\n"
            f"Use /requirements {giveaway_id} to view bonus entries."
        )

    else:
        await message.answer(
            "❌ Wrong or expired captcha.\n\n"
            "Use /join again."
        )


@router.message(Command("requirements", "recheck"))
async def requirements(message: Message, command: CommandObject):
    giveaway_id = int(command.args or 0)

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT * FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        participant = await connection.fetchrow(
            """
            SELECT * FROM participants
            WHERE giveaway = $1
            AND user_id = $2
            """,
            giveaway_id,
            message.from_user.id,
        )

    if not giveaway or not participant:
        return await message.answer(
            "You are not participating in this giveaway."
        )

    bot_username = (await message.bot.me()).username

    referral_link = (
        f"https://t.me/{bot_username}"
        f"?start=ref_{giveaway_id}_{message.from_user.id}"
    )

    text = (
        f"📋 <b>{giveaway['title']}</b>\n\n"
        f"🎯 Your entries: <b>{participant['total_entries']}</b>\n\n"
        f"💬 Chat activity: "
        f"{participant['messages']}/{giveaway['chat_target'] or 0}\n"
        f"🤖 Captcha: "
        f"{'✅ Verified' if participant['captcha'] else '❌ Not verified'}\n\n"
    )

    if giveaway["bio_bonus"]:
        text += (
            f"📝 Bio bonus: add <code>{giveaway['bio_bonus']}</code>\n"
            f"Reward: +1 entry\n\n"
        )

    if giveaway["name_bonus"]:
        text += (
            f"🏷 Name bonus: add <code>{giveaway['name_bonus']}</code>\n"
            f"Reward: +1 entry\n\n"
        )

    if giveaway["referral_bonus"]:
        text += (
            f"👥 Referrals: +{giveaway['referral_bonus']} per valid friend\n"
            f"Referral cap: {giveaway['referral_cap']}\n\n"
            f"🔗 Your referral link:\n{referral_link}"
        )

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Recheck Bonus Entries",
                        callback_data=f"recheck:{giveaway_id}",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("recheck:"))
async def recheck(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[1])

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT * FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        participant = await connection.fetchrow(
            """
            SELECT * FROM participants
            WHERE giveaway = $1
            AND user_id = $2
            """,
            giveaway_id,
            callback.from_user.id,
        )

    if not giveaway or not participant:
        return await callback.answer(
            "You are not participating.",
            show_alert=True,
        )

    profile = await callback.bot.get_chat(callback.from_user.id)

    full_name = " ".join(
        filter(
            None,
            [
                profile.first_name,
                profile.last_name,
            ],
        )
    )

    bio = profile.bio or ""

    bonus = 0

    if (
        giveaway["bio_bonus"]
        and giveaway["bio_bonus"].casefold()
        in bio.casefold()
    ):
        bonus += 1

    if (
        giveaway["name_bonus"]
        and giveaway["name_bonus"].casefold()
        in full_name.casefold()
    ):
        bonus += 1

    async with db.pool.acquire() as connection:
        await connection.execute(
            """
            UPDATE participants
            SET bonus = $3,
            total_entries = 1 + $3 + referral_entries
            WHERE giveaway = $1
            AND user_id = $2
            """,
            giveaway_id,
            callback.from_user.id,
            bonus,
        )

    await callback.message.edit_text(
        f"✅ <b>Bonus entries updated!</b>\n\n"
        f"🎯 Total entries: <b>{1 + bonus + participant['referral_entries']}</b>"
    )


@router.callback_query(F.data == "my_entries")
async def my_entries(callback: CallbackQuery):
    async with db.pool.acquire() as connection:
        participants = await connection.fetch(
            """
            SELECT giveaway, total_entries
            FROM participants
            WHERE user_id = $1
            """,
            callback.from_user.id,
        )

    if not participants:
        return await callback.message.edit_text(
            "You have not joined any giveaway yet."
        )

    text = "📊 <b>My Entries</b>\n\n"

    text += "\n".join(
        f"🆔 <code>{participant['giveaway']}</code> — "
        f"{participant['total_entries']} entries"
        for participant in participants
    )

    await callback.message.edit_text(text)
