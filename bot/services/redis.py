import secrets, random
from redis.asyncio import from_url
from bot.config import REDIS_URL
r=from_url(REDIS_URL,decode_responses=True)
async def lock(key,ttl=10): return bool(await r.set(key,"1",nx=True,ex=ttl))
async def unlock(key): await r.delete(key)
async def new_captcha(gid,uid):
    a,b=random.randint(2,20),random.randint(2,20)
    await r.setex(f"cap:{gid}:{uid}",180,str(a+b))
    return a,b
async def check_captcha(gid,uid,ans):
    correct=await r.get(f"cap:{gid}:{uid}")
    if correct and ans.strip()==correct:
        await r.delete(f"cap:{gid}:{uid}"); return True
    return False
async def captcha_cooldown(gid,uid): return bool(await r.exists(f"capcool:{gid}:{uid}"))
async def set_cooldown(gid,uid): await r.setex(f"capcool:{gid}:{uid}",600,"1")
