import asyncpg
from bot.config import DATABASE_URL
pool=None
async def init():
    global pool
    pool=await asyncpg.create_pool(DATABASE_URL,min_size=1,max_size=10)
    schema=open("app_schema.sql").read()
    async with pool.acquire() as c:
        await c.execute(schema)
async def close():
    if pool: await pool.close()
