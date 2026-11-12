import secrets

from bot import db
from bot.services.channels import is_member
from bot.services.logs import audit, discover


async def is_eligible(bot, giveaway, participant):
    if not participant["captcha"]:
        return False

    if (
        giveaway["chat_target"]
        and participant["messages"] < giveaway["chat_target"]
    ):
        return False

    async with db.pool.acquire() as connection:
        channels = await connection.fetch(
            """
            SELECT chat_id
            FROM giveaway_channels
            WHERE giveaway = $1
            AND required = TRUE
            """,
            giveaway["id"],
        )

    for channel in channels:
        if not await is_member(
            bot,
            channel["chat_id"],
            participant["user_id"],
        ):
            return False

    if giveaway["chat_id"]:
        if not await is_member(
            bot,
            giveaway["chat_id"],
            participant["user_id"],
        ):
            return False

    return True


async def draw(bot, giveaway_id, actor=None, reroll=False):
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
                raise ValueError("Giveaway not found.")

            if (
                actor is not None
                and actor != giveaway["host"]
                and actor != 0
            ):
                raise ValueError("Not your giveaway.")

            if not reroll and giveaway["status"] != "active":
                return []

            if reroll and giveaway["status"] != "ended":
                raise ValueError(
                    "Reroll requires an ended giveaway."
                )

            previous_winners = await connection.fetch(
                """
                SELECT user_id
                FROM winners
                WHERE giveaway = $1
                """,
                giveaway_id,
            )

            excluded_users = {
                winner["user_id"]
                for winner in previous_winners
            }

            participants = await connection.fetch(
                """
                SELECT * FROM participants
                WHERE giveaway = $1
                AND valid = TRUE
                """,
                giveaway_id,
            )

            entry_pool = []

            for participant in participants:
                if participant["user_id"] in excluded_users:
                    continue

                if not await is_eligible(
                    bot,
                    giveaway,
                    participant,
                ):
                    continue

                profile = await bot.get_chat(
                    participant["user_id"]
                )

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

                total_entries = (
                    1
                    + participant["bonus"]
                    + bonus
                    + participant["referral_entries"]
                )

                entry_pool.extend(
                    [participant["user_id"]] * total_entries
                )

            winners = []

            while (
                len(winners)
                < min(
                    giveaway["winners"],
                    len(set(entry_pool)),
                )
            ):
                if not entry_pool:
                    break

                selected_user = secrets.choice(entry_pool)

                if selected_user in winners:
                    continue

                winners.append(selected_user)

            round_number = await connection.fetchval(
                """
                SELECT COALESCE(MAX(round), 0) + 1
                FROM winners
                WHERE giveaway = $1
                """,
                giveaway_id,
            )

            for user_id in winners:
                await connection.execute(
                    """
                    INSERT INTO winners
                    (giveaway, user_id, round, selection)
                    VALUES ($1, $2, $3, $4)
                    """,
                    giveaway_id,
                    user_id,
                    round_number,
                    "reroll" if reroll else "random",
                )

            if not reroll:
                await connection.execute(
                    """
                    UPDATE giveaways
                    SET status = 'ended'
                    WHERE id = $1
                    """,
                    giveaway_id,
                )

    result_text = (
        f"🏆 <b>Giveaway #{giveaway_id}</b>\n\n"
        f"Round: {round_number}\n"
        f"Winners:\n"
        + "\n".join(f"• <code>{user_id}</code>" for user_id in winners)
    )

    await audit(
        bot,
        "WINNERS_SELECTED" if not reroll else "WINNERS_REROLLED",
        actor,
        giveaway_id,
        ", ".join(map(str, winners)),
    )

    await discover(bot, result_text)

    try:
        await bot.send_message(
            giveaway["host"],
            result_text,
        )
    except Exception:
        pass

    return winners
