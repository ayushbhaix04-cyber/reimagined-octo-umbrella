import asyncpg

from bot.config import DATABASE_URL

pool = None


async def init():
    global pool

    if pool is not None:
        return

    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    with open("app_schema.sql", "r", encoding="utf-8") as file:
        schema = file.read()

    async with pool.acquire() as connection:
        await connection.execute(schema)


async def close():
    global pool

    if pool:
        await pool.close()
        pool = None
