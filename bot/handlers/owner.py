from aiogram import Router,F,Bot
from aiogram.filters import Command,CommandObject
from aiogram.types import Message
from bot.db import pool
from bot.config import OWNER_ID
from bot.services.logs import audit
router=Router()

def owner_only(fn):
    async def w(m:Message,*a,**k):
        if m.from_user.id!=OWNER_ID: return await m.answer("❌ Owner only.")
        return await fn(m,*a,**k)
    return w

@router.message(Command("globalchannel"))
@owner_only
async def add_global(m:Message,command:CommandObject,bot:Bot):
    args=(command.args or '').split(maxsplit=1)
    if len(args)<2: return await m.answer("Usage: /globalchannel CHAT_ID INVITE_LINK")
    async with pool.acquire() as c:
        await c.execute("INSERT INTO global_channels(chat_id,title,link) VALUES($1,$2,$3) ON CONFLICT(chat_id) DO UPDATE SET link=$3,title=$2",int(args[0]),args[0],args[1])
    await audit(bot,"GLOBAL_ADDED",m.from_user.id,0,args[0])
    await m.answer("✅ Global channel added.")
@router.message(Command("removeglobalchannel"))
@owner_only
async def rm_global(m:Message,command:CommandObject,bot:Bot):
    async with pool.acquire() as c: await c.execute("DELETE FROM global_channels WHERE chat_id=$1",int(command.args or 0))
    await audit(bot,"GLOBAL_REMOVED",m.from_user.id,0,str(command.args))
    await m.answer("✅ Removed.")
@router.message(Command("platformstats"))
@owner_only
async def stats(m:Message):
    async with pool.acquire() as c:
        g=await c.fetchval("SELECT COUNT(*) FROM giveaways"); p=await c.fetchval("SELECT COUNT(*) FROM participants")
    await m.answer(f"📊 Giveaways: {g}\n👥 Participants: {p}")
@router.message(Command("winner"))
@owner_only
async def winner(m:Message,command:CommandObject,bot:Bot):
    args=(command.args or '').split()
    if len(args)<2: return await m.answer("Usage: /winner GID UID [reason]")
    gid,uid=int(args[0]),int(args[1]); reason=" ".join(args[2:])
    async with pool.acquire() as c:
        async with c.transaction():
            g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1 FOR UPDATE",gid)
            if not g: return await m.answer("❌ Not found.")
            p=await c.fetchrow("SELECT 1 FROM participants WHERE giveaway=$1 AND user_id=$2",gid,uid)
            if not p: return await m.answer("⚠️ Not a participant. Add via /channel or manually first.")
            rnd=await c.fetchval("SELECT COALESCE(MAX(round),0)+1 FROM winners WHERE giveaway=$1",gid)
            await c.execute("INSERT INTO winners(giveaway,user_id,round,selection,reason) VALUES($1,$2,$3,'fixed',$4)",gid,uid,rnd,reason)
            await c.execute("UPDATE giveaways SET status='ended' WHERE id=$1",gid)
    await audit(bot,"FIXED_WINNER",m.from_user.id,gid,f"user={uid} reason={reason}")
    await m.answer(f"✅ Fixed winner {uid} for #{gid}.")
