from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot import db
from bot.services.logs import audit, discover

router = Router()


class CreateGiveaway(StatesGroup):
    title = State()
    prize = State()
    duration = State()
    winners = State()
    channel = State()
    chat = State()
    bio = State()
    name = State()


def parse_duration(value: str):
    units = {
        "m": 60,
        "h": 3600,
        "d": 86400,
    }

    try:
        seconds = int(value[:-1]) * units[value[-1].lower()]
    except Exception:
        return None

    if 60 <= seconds <= 7776000:
        return seconds

    return None


def clean_value(value, max_length=200):
    if not value:
        return ""

    value = str(value).strip()

    if value.lower() in {"skip", "-", "none", "no"}:
        return ""

    return value[:max_length]


async def resolve_channel(bot: Bot, value: str):
    """
    Accepts:
    - @username
    - -1001234567890
    - https://t.me/username

    Returns:
    (chat_id, invite_link)
    """

    value = value.strip()

    if value.startswith("@"):
        chat = await bot.get_chat(value)
        return chat.id, f"https://t.me/{chat.username}"

    if value.startswith("https://t.me/"):
        username = value.replace("https://t.me/", "").split("/")[0]
        chat = await bot.get_chat(f"@{username}")
        return chat.id, f"https://t.me/{chat.username}"

    if value.lstrip("-").isdigit():
        chat = await bot.get_chat(int(value))
        invite_link = (
            f"https://t.me/{chat.username}"
            if chat.username
            else ""
        )
        return chat.id, invite_link

    raise ValueError(
        "Send a public channel username, numeric channel ID, or t.me link."
    )


@router.callback_query(F.data == "host_create")
async def host_create(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await state.set_state(CreateGiveaway.title)

    await callback.message.edit_text(
        "🚀 <b>Create Giveaway</b>\n\n"
        "✅ No approval required.\n"
        "You can create and manage your own giveaways.\n\n"
        "1️⃣ Send the giveaway title:"
    )


@router.message(Command("cancel"))
async def cancel_creation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Giveaway creation cancelled.\n\nUse /create to start again."
    )


@router.message(CreateGiveaway.title)
async def set_title(message: Message, state: FSMContext):
    title = clean_value(message.text, 100)

    if not title:
        return await message.answer(
            "❌ Please send a valid giveaway title."
        )

    await state.update_data(title=title)
    await state.set_state(CreateGiveaway.prize)

    await message.answer("2️⃣ Send the prize:")


@router.message(CreateGiveaway.prize)
async def set_prize(message: Message, state: FSMContext):
    prize = clean_value(message.text, 300)

    if not prize:
        return await message.answer(
            "❌ Please send a valid prize."
        )

    await state.update_data(prize=prize)
    await state.set_state(CreateGiveaway.duration)

    await message.answer(
        "3️⃣ Send duration:\n\n"
        "Examples:\n"
        "<code>1m</code>\n"
        "<code>1h</code>\n"
        "<code>7d</code>\n"
        "<code>90d</code>"
    )


@router.message(CreateGiveaway.duration)
async def set_duration(message: Message, state: FSMContext):
    seconds = parse_duration(message.text.strip())

    if not seconds:
        return await message.answer(
            "❌ Duration must be between 1m and 90d."
        )

    await state.update_data(duration=seconds)
    await state.set_state(CreateGiveaway.winners)

    await message.answer("4️⃣ How many winners?")


@router.message(CreateGiveaway.winners)
async def set_winners(message: Message, state: FSMContext):
    if not message.text.isdigit() or not 1 <= int(message.text) <= 100:
        return await message.answer(
            "❌ Send a number between 1 and 100."
        )

    await state.update_data(winners=int(message.text))
    await state.set_state(CreateGiveaway.channel)

    await message.answer(
        "5️⃣ Send a required public channel:\n\n"
        "<code>@yourchannel</code>\n\n"
        "Or send a numeric channel ID:\n"
        "<code>-1001234567890</code>\n\n"
        "Send <code>skip</code> to continue without a channel."
    )


@router.message(CreateGiveaway.channel)
async def set_channel(message: Message, state: FSMContext, bot: Bot):
    channel = clean_value(message.text, 200)

    if channel:
        try:
            channel_id, invite_link = await resolve_channel(
                bot,
                channel,
            )
        except Exception:
            return await message.answer(
                "❌ Invalid channel.\n\n"
                "Send a public channel username, numeric channel ID, "
                "or t.me link.\n\n"
                "Example:\n<code>@yourchannel</code>"
            )

        await state.update_data(
            channel_id=channel_id,
            channel_link=invite_link,
        )

    else:
        await state.update_data(
            channel_id=None,
            channel_link="",
        )

    await state.set_state(CreateGiveaway.chat)

    await message.answer(
        "6️⃣ Send optional chat activity requirement.\n\n"
        "Format:\n<code>GROUP_ID:MESSAGE_TARGET</code>\n\n"
        "Example:\n<code>-1001234567890:20</code>\n\n"
        "This means: participants must send 20 messages in that group.\n\n"
        "Send <code>skip</code> to disable."
    )


@router.message(CreateGiveaway.chat)
async def set_chat(message: Message, state: FSMContext):
    chat = clean_value(message.text, 100)

    if chat and ":" not in chat:
        return await message.answer(
            "❌ Use format:\n<code>GROUP_ID:TARGET</code>\n\n"
            "Example:\n<code>-1001234567890:20</code>"
        )

    if chat:
        try:
            group_id, target = chat.split(":")
            group_id = int(group_id)
            target = int(target)

            if not 0 <= target <= 10000:
                raise ValueError
        except Exception:
            return await message.answer(
                "❌ Invalid chat format.\n\n"
                "Use:\n<code>GROUP_ID:TARGET</code>"
            )

    await state.update_data(chat=chat)
    await state.set_state(CreateGiveaway.bio)

    await message.answer(
        "7️⃣ Send optional bio bonus keyword.\n\n"
        "Example:\n<code>@uniquegiveaways123</code>\n\n"
        "This gives +1 bonus entry.\n\n"
        "Send <code>skip</code> to disable."
    )


@router.message(CreateGiveaway.bio)
async def set_bio(message: Message, state: FSMContext):
    bio = clean_value(message.text, 100)

    await state.update_data(bio=bio)
    await state.set_state(CreateGiveaway.name)

    await message.answer(
        "8️⃣ Send optional name bonus keyword.\n\n"
        "Example:\n<code>@uniquegiveaways123</code>\n\n"
        "This gives +1 bonus entry.\n\n"
        "Send <code>skip</code> to disable."
    )


@router.message(CreateGiveaway.name)
async def finish_creation(
    message: Message,
    state: FSMContext,
    bot: Bot,
):
    data = await state.get_data()

    title = clean_value(data.get("title"), 100)
    prize = clean_value(data.get("prize"), 300)
    duration = data.get("duration")
    winners = data.get("winners")
    channel_id = data.get("channel_id")
    channel_link = data.get("channel_link") or ""
    chat = clean_value(data.get("chat"), 100)
    bio_bonus = clean_value(data.get("bio"), 100)
    name_bonus = clean_value(data.get("name"), 100)

    if not title or not prize or not duration or not winners:
        await state.clear()

        return await message.answer(
            "❌ Giveaway creation data expired or incomplete.\n\n"
            "Please use /create again."
        )

    chat_id = None
    chat_target = 0

    if chat and ":" in chat:
        try:
            chat_id, chat_target = chat.split(":")
            chat_id = int(chat_id)
            chat_target = int(chat_target)
        except Exception:
            chat_id = None
            chat_target = 0

    async with db.pool.acquire() as connection:
        giveaway_id = await connection.fetchval(
            """
            INSERT INTO giveaways
            (
                host,
                title,
                prize,
                ends,
                winners,
                chat_id,
                chat_target,
                bio_bonus,
                name_bonus
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            message.from_user.id,
            title,
            prize,
            datetime.now(timezone.utc)
            + timedelta(seconds=duration),
            winners,
            chat_id,
            chat_target,
            bio_bonus,
            name_bonus,
        )

        if channel_id:
            await connection.execute(
                """
                INSERT INTO giveaway_channels
                (giveaway, chat_id, title, link)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (giveaway, chat_id)
                DO UPDATE SET link = $4
                """,
                giveaway_id,
                channel_id,
                str(channel_id),
                channel_link,
            )

        await connection.execute(
            """
            UPDATE users
            SET is_host = TRUE
            WHERE tg_id = $1
            """,
            message.from_user.id,
        )

    await state.clear()

    bot_username = (await bot.me()).username

    participation_link = (
        f"https://t.me/{bot_username}"
        f"?start=giveaway_{giveaway_id}"
    )

    discovery_text = (
        "🎉 <b>NEW GIVEAWAY</b>\n\n"
        f"🎁 {prize}\n"
        f"👥 Winners: {winners}\n"
        f"👤 Host: @{message.from_user.username or message.from_user.id}\n"
        f"🆔 Giveaway ID: <code>{giveaway_id}</code>\n\n"
        "Tap below to participate."
    )

    discovery_message = await discover(
        bot,
        discovery_text,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎁 Participate Now",
                        url=participation_link,
                    )
                ]
            ]
        ),
    )

    if discovery_message:
        async with db.pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE giveaways
                SET discovery_msg = $2
                WHERE id = $1
                """,
                giveaway_id,
                discovery_message.message_id,
            )

    await audit(
        bot,
        "GIVEAWAY_CREATED",
        message.from_user.id,
        giveaway_id,
        f"{title} | {prize}",
    )

    await message.answer(
        "✅ <b>Giveaway created!</b>\n\n"
        f"🆔 ID: <code>{giveaway_id}</code>\n"
        f"🎁 Prize: {prize}\n"
        f"👥 Winners: {winners}\n"
        f"💬 Chat target: {chat_target or 'Disabled'}\n"
        f"📝 Bio bonus: {bio_bonus or 'Disabled'}\n"
        f"🏷 Name bonus: {name_bonus or 'Disabled'}\n\n"
        f"Participation link:\n{participation_link}"
    )


@router.message(Command("mygiveaways"))
async def my_giveaways(message: Message):
    async with db.pool.acquire() as connection:
        giveaways = await connection.fetch(
            """
            SELECT *
            FROM giveaways
            WHERE host = $1
            ORDER BY id DESC
            LIMIT 20
            """,
            message.from_user.id,
        )

    if not giveaways:
        return await message.answer(
            "You have not created any giveaways yet.\n\nUse /create"
        )

    text = "📋 <b>My Giveaways</b>\n\n"

    text += "\n".join(
        f"🆔 <code>{giveaway['id']}</code> — "
        f"{giveaway['title']} [{giveaway['status']}]"
        for giveaway in giveaways
    )

    await message.answer(text)


@router.message(Command("participants"))
async def participants(message: Message, command: CommandObject):
    giveaway_id = int(command.args or 0)

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can view only your own giveaways."
            )

        participants = await connection.fetch(
            """
            SELECT user_id, messages, bonus, referral_entries, total_entries
            FROM participants
            WHERE giveaway = $1
            LIMIT 100
            """,
            giveaway_id,
        )

    if not participants:
        return await message.answer("No participants yet.")

    text = f"👥 <b>Participants — {giveaway_id}</b>\n\n"

    text += "\n".join(
        f"• <code>{participant['user_id']}</code> — "
        f"{participant['total_entries']} entries\n"
        f"💬 Chat: {participant['messages']}\n"
        f"🎁 Bonus: {participant['bonus']}\n"
        f"👥 Referrals: {participant['referral_entries']}"
        for participant in participants
    )

    await message.answer(text)


@router.message(Command("edit"))
async def edit_giveaway(message: Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=2)

    if len(args) < 3:
        return await message.answer(
            "Usage:\n"
            "/edit ID title VALUE\n"
            "/edit ID prize VALUE\n"
            "/edit ID duration 7d\n"
            "/edit ID winners 3"
        )

    giveaway_id = int(args[0])
    field = args[1]
    value = args[2]

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can edit only your own giveaways."
            )

        if field in {"title", "prize"}:
            await connection.execute(
                f"UPDATE giveaways SET {field} = $2 WHERE id = $1",
                giveaway_id,
                value[:500],
            )

        elif field == "duration":
            seconds = parse_duration(value)

            if not seconds:
                return await message.answer(
                    "❌ Invalid duration."
                )

            await connection.execute(
                """
                UPDATE giveaways
                SET ends = $2
                WHERE id = $1
                """,
                giveaway_id,
                datetime.now(timezone.utc)
                + timedelta(seconds=seconds),
            )

        elif field == "winners":
            if not value.isdigit() or not 1 <= int(value) <= 100:
                return await message.answer(
                    "❌ Winners must be 1–100."
                )

            await connection.execute(
                "UPDATE giveaways SET winners = $2 WHERE id = $1",
                giveaway_id,
                int(value),
            )

        else:
            return await message.answer(
                "❌ Invalid field."
            )

    await audit(
        message.bot,
        "GIVEAWAY_EDITED",
        message.from_user.id,
        giveaway_id,
        f"{field}={value}",
    )

    await message.answer("✅ Giveaway updated.")


@router.message(Command("pause", "resume", "cancel"))
async def change_status(message: Message, command: CommandObject):
    giveaway_id = int(command.args or 0)

    status = {
        "pause": "paused",
        "resume": "active",
        "cancel": "cancelled",
    }[command.command]

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can manage only your own giveaways."
            )

        await connection.execute(
            "UPDATE giveaways SET status = $2 WHERE id = $1",
            giveaway_id,
            status,
        )

    await audit(
        message.bot,
        command.command.upper(),
        message.from_user.id,
        giveaway_id,
    )

    await message.answer("✅ Updated.")


@router.message(Command("channel"))
async def add_channel(message: Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=2)

    if len(args) < 3:
        return await message.answer(
            "Usage: /channel GIVEAWAY_ID CHANNEL_ID INVITE_LINK"
        )

    giveaway_id = int(args[0])

    try:
        channel_id = int(args[1])
    except Exception:
        return await message.answer(
            "❌ CHANNEL_ID must be a numeric Telegram ID.\n"
            "Example: -1001234567890"
        )

    invite_link = args[2]

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can manage only your own giveaways."
            )

        bot_id = (await message.bot.me()).id

        try:
            bot_member = await message.bot.get_chat_member(
                channel_id,
                bot_id,
            )
        except Exception:
            return await message.answer(
                "❌ Add the bot as administrator in that channel first."
            )

        if bot_member.status not in {"administrator", "creator"}:
            return await message.answer(
                "❌ Bot must be administrator in the required channel."
            )

        await connection.execute(
            """
            INSERT INTO giveaway_channels
            (giveaway, chat_id, title, link)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (giveaway, chat_id)
            DO UPDATE SET link = $4
            """,
            giveaway_id,
            channel_id,
            str(channel_id),
            invite_link,
        )

    await audit(
        message.bot,
        "CHANNEL_ADDED",
        message.from_user.id,
        giveaway_id,
        invite_link,
    )

    await message.answer("✅ Required channel added.")


@router.message(Command("removechannel"))
async def remove_channel(message: Message, command: CommandObject):
    args = (command.args or "").split()

    if len(args) < 2:
        return await message.answer(
            "Usage: /removechannel GIVEAWAY_ID CHANNEL_ID"
        )

    giveaway_id = int(args[0])
    channel_id = int(args[1])

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can manage only your own giveaways."
            )

        await connection.execute(
            """
            DELETE FROM giveaway_channels
            WHERE giveaway = $1
            AND chat_id = $2
            """,
            giveaway_id,
            channel_id,
        )

    await audit(
        message.bot,
        "CHANNEL_REMOVED",
        message.from_user.id,
        giveaway_id,
        str(channel_id),
    )

    await message.answer("✅ Channel removed.")


@router.message(Command("chat"))
async def set_chat_requirement(message: Message, command: CommandObject):
    args = (command.args or "").split()

    if len(args) < 3:
        return await message.answer(
            "Usage: /chat GIVEAWAY_ID GROUP_ID TARGET\n\n"
            "Example:\n/chat 1 -1001234567890 20\n\n"
            "Use target 0 to disable chat activity."
        )

    giveaway_id = int(args[0])
    group_id = int(args[1])
    target = int(args[2])

    if not 0 <= target <= 10000:
        return await message.answer(
            "❌ Target must be between 0 and 10000."
        )

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can manage only your own giveaways."
            )

        if target > 0:
            try:
                chat = await message.bot.get_chat(group_id)
            except Exception:
                return await message.answer(
                    "❌ Invalid group ID."
                )

            if chat.type not in {"group", "supergroup"}:
                return await message.answer(
                    "❌ Chat activity must be a group."
                )

            bot_id = (await message.bot.me()).id

            try:
                bot_member = await message.bot.get_chat_member(
                    group_id,
                    bot_id,
                )
            except Exception:
                return await message.answer(
                    "❌ Add the bot as administrator in the group first."
                )

            if bot_member.status not in {"administrator", "creator"}:
                return await message.answer(
                    "❌ Bot must be group administrator to count messages."
                )

        await connection.execute(
            """
            UPDATE giveaways
            SET chat_id = $2,
            chat_target = $3
            WHERE id = $1
            """,
            giveaway_id,
            group_id if target else None,
            target,
        )

        await connection.execute(
            """
            UPDATE participants
            SET messages = 0,
            last_count = NULL
            WHERE giveaway = $1
            """,
            giveaway_id,
        )

    await audit(
        message.bot,
        "CHAT_REQUIREMENT_SET",
        message.from_user.id,
        giveaway_id,
        f"target={target}",
    )

    await message.answer(
        f"✅ Chat target set to {target}."
    )


@router.message(Command("bonus"))
async def set_bonus(message: Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=2)

    if len(args) < 3:
        return await message.answer(
            "Usage:\n"
            "/bonus ID bio KEYWORD\n"
            "/bonus ID name KEYWORD\n"
            "/bonus ID bio -\n"
            "/bonus ID name -"
        )

    giveaway_id = int(args[0])
    bonus_type = args[1]
    keyword = args[2]

    if bonus_type not in {"bio", "name"}:
        return await message.answer(
            "❌ Bonus type must be bio or name."
        )

    keyword = "" if keyword == "-" else keyword[:100]

    async with db.pool.acquire() as connection:
        giveaway = await connection.fetchrow(
            "SELECT host FROM giveaways WHERE id = $1",
            giveaway_id,
        )

        if not giveaway or giveaway["host"] != message.from_user.id:
            return await message.answer(
                "❌ You can manage only your own giveaways."
            )

        await connection.execute(
            f"UPDATE giveaways SET {bonus_type}_bonus = $2 WHERE id = $1",
            giveaway_id,
            keyword,
        )

        await connection.execute(
            "UPDATE participants SET bonus = 0 WHERE giveaway = $1",
            giveaway_id,
        )

    await audit(
        message.bot,
        "BONUS_SET",
        message.from_user.id,
        giveaway_id,
        f"{bonus_type}={keyword}",
    )

    await message.answer("✅ Bonus updated.")


@router.message(Command("draw", "reroll"))
async def draw_command(message: Message, command: CommandObject, bot: Bot):
    from bot.services.draw import draw

    giveaway_id = int(command.args or 0)

    try:
        winners = await draw(
            bot,
            giveaway_id,
            message.from_user.id,
            command.command == "reroll",
        )
    except ValueError as error:
        return await message.answer(f"❌ {error}")

    if not winners:
        return await message.answer(
            "No eligible participants."
        )

    await message.answer(
        "🏆 <b>Winners selected!</b>\n\n"
        + "\n".join(
            f"{index}. <code>{user_id}</code>"
            for index, user_id in enumerate(winners, 1)
        )
    )
