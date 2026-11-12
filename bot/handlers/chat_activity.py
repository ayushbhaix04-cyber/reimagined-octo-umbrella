import hashlib
from aiogram import Router,F
from bot.db import pool
router=Router()

@router.message(F.chat.type.in_({"group","supergroup"}))
async def count_activity(message):
    if not message.from_user or message.from_user.is_bot or message.sender_chat:
        return
    text=(message.text or "").strip()
    if len(text)<5 or text.startswith("/"):
        return
    if any(e.type in {"url","text_link"} for e in (message.entities or [])):
        return
    digest=hashlib.sha256(text.casefold().encode()).hexdigest()
    async with pool.acquire() as c:
        async with c.transaction():
            rows=await c.fetch("""SELECT p.giveaway FROM participants p JOIN giveaways g ON g.id=p.giveaway
                WHERE g.chat_id=$1 AND g.status='active' AND g.ends>now()
                AND p.user_id=$2 AND p.captcha""",message.chat.id,message.from_user.id)
            for row in rows:
                gid=row["giveaway"]
                await c.execute("SELECT 1 FROM participants WHERE giveaway=$1 AND user_id=$2 FOR UPDATE",gid,message.from_user.id)
                inserted=await c.fetchval("INSERT INTO counted_messages VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING message_id",gid,message.chat.id,message.message_id,message.from_user.id)
                if inserted is None:
                    continue
                await c.execute("""UPDATE participants SET messages=messages+1,last_count=now()
                    WHERE giveaway=$1 AND user_id=$2 AND (last_count IS NULL OR last_count<=now()-interval '30 seconds')""",gid,message.from_user.id)
