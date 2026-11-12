from aiogram import Router,F,Bot
from aiogram.filters import Command,CommandStart,CommandObject
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton
from bot.db import pool
from bot.config import OWNER_ID,SUPPORT_USERNAME
from bot.services.redis import new_captcha,check_captcha,captcha_cooldown,set_cooldown,lock,unlock
from bot.services.channels import is_member
from bot.services.logs import audit,discover
router=Router()

MENU=InlineKeyboardMarkup(inline_keyboard=[
 [InlineKeyboardButton(text="🎁 Browse Giveaways",callback_data="browse")],
 [InlineKeyboardButton(text="🚀 Create Giveaway",callback_data="host_create")],
 [InlineKeyboardButton(text="📊 My Entries",callback_data="my_entries")],
 [InlineKeyboardButton(text="🆘 Support",url=f"https://t.me/{SUPPORT_USERNAME}")]])

@router.message(CommandStart())
async def start(m:Message,command:CommandObject):
    async with pool.acquire() as c:
        await c.execute("INSERT INTO users(tg_id,username,first_name) VALUES($1,$2,$3) ON CONFLICT(tg_id) DO UPDATE SET username=$2",m.from_user.id,m.from_user.username,m.from_user.first_name)
        if command.args and command.args.startswith("ref_"):
            try:
                _,gid,ref=command.args.split("_"); gid,ref=int(gid),int(ref)
                if ref!=m.from_user.id:
                    await c.execute("INSERT INTO referrals(giveaway,referrer,invited) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",gid,ref,m.from_user.id)
            except Exception: pass
    await m.answer("🎉 <b>Welcome to GiveawayX</b>\nParticipate, refer friends, or host your own giveaway — no approval needed.",reply_markup=MENU)

@router.callback_query(F.data=="browse")
async def browse(cb:CallbackQuery):
    async with pool.acquire() as c:
        rows=await c.fetch("SELECT id,title,prize FROM giveaways WHERE status='active' AND ends>now() ORDER BY id DESC LIMIT 10")
    if not rows: return await cb.message.edit_text("No active giveaways.")
    kb=[[InlineKeyboardButton(text=f"🎁 {r['title']}",callback_data=f"view:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="🔙 Back",callback_data="main")])
    await cb.message.edit_text("🔥 <b>Active Giveaways</b>",reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data=="main")
async def main_menu(cb:CallbackQuery): await cb.message.edit_text("🎉 <b>Main Menu</b>",reply_markup=MENU)

@router.callback_query(F.data.startswith("view:"))
async def view_cb(cb:CallbackQuery):
    gid=int(cb.data.split(":")[1])
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1",gid)
        chans=await c.fetch("SELECT * FROM giveaway_channels WHERE giveaway=$1",gid)
    if not g: return await cb.answer("Not found",show_alert=True)
    text=f"🎁 <b>{g['title']}</b>\n🏆 {g['prize']}\n👥 Winners: {g['winners']}\n🆔 #{gid}\n\n{g['description'] or ''}"
    kb=[[InlineKeyboardButton(text="✅ Participate",callback_data=f"join:{gid}")]]
    for ch in chans: kb.append([InlineKeyboardButton(text=f"📢 {ch['title'] or 'Join'}",url=ch["link"])])
    kb.append([InlineKeyboardButton(text="🔙 Back",callback_data="browse")])
    await cb.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("join:"))
async def join_cb(cb:CallbackQuery,bot:Bot):
    gid=int(cb.data.split(":")[1]); uid=cb.from_user.id
    if not await lock(f"join:{gid}:{uid}"): return await cb.answer("Wait...",show_alert=True)
    try:
        async with pool.acquire() as c:
            g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1 AND status='active' AND ends>now()",gid)
            chans=await c.fetch("SELECT * FROM giveaway_channels WHERE giveaway=$1 AND required",gid)
            glob=await c.fetch("SELECT * FROM global_channels WHERE active")
        if not g: return await cb.answer("Giveaway ended.",show_alert=True)
        for ch in list(glob)+list(chans):
            if not await is_member(bot,ch["chat_id"],uid):
                return await cb.answer(f"Join {ch['title'] or ch['chat_id']} first.",show_alert=True)
        if await captcha_cooldown(gid,uid): return await cb.answer("Captcha cooldown 10 min.",show_alert=True)
        a,b=await new_captcha(gid,uid)
        await cb.message.edit_text(f"🤖 Human check\n{a} + {b} = ?\nReply: /captcha {gid} ANSWER")
    finally: await unlock(f"join:{gid}:{uid}")

@router.message(Command("captcha"))
async def captcha(m:Message,command:CommandObject):
    try: gid,ans=command.args.split(); gid=int(gid)
    except Exception: return await m.answer("Usage: /captcha GID ANSWER")
    if await captcha_cooldown(gid,m.from_user.id): return await m.answer("Cooldown active.")
    if await check_captcha(gid,m.from_user.id,ans):
        async with pool.acquire() as c:
            await c.execute("INSERT INTO participants(giveaway,user_id,captcha) VALUES($1,$2,TRUE) ON CONFLICT(giveaway,user_id) DO UPDATE SET captcha=TRUE",gid,m.from_user.id)
            # credit referrer if referral exists and now valid
            ref=await c.fetchrow("SELECT referrer FROM referrals WHERE giveaway=$1 AND invited=$2 AND NOT valid",gid,m.from_user.id)
            if ref:
                await c.execute("UPDATE referrals SET valid=TRUE WHERE giveaway=$1 AND invited=$2",gid,m.from_user.id)
                cnt=await c.fetchval("SELECT COUNT(*) FROM referrals WHERE giveaway=$1 AND referrer=$2 AND valid",gid,ref["referrer"])
                cap=await c.fetchval("SELECT referral_cap FROM giveaways WHERE id=$1",gid)
                if cnt<=cap:
                    bonus=await c.fetchval("SELECT referral_bonus FROM giveaways WHERE id=$1",gid)
                    await c.execute("UPDATE participants SET referral_entries=referral_entries+$2,total_entries=total_entries+$2 WHERE giveaway=$1 AND user_id=$3",gid,bonus,ref["referrer"])
        await m.answer(f"✅ Verified! Use /requirements {gid} for bonus tasks.")
    else: await m.answer("❌ Wrong/expired captcha. /join again.")

@router.message(Command("requirements","recheck"))
async def requirements(m:Message,command:CommandObject):
    gid=int(command.args or 0)
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1",gid)
        p=await c.fetchrow("SELECT * FROM participants WHERE giveaway=$1 AND user_id=$2",gid,m.from_user.id)
        bonuses=await c.fetch("SELECT * FROM bonus_tasks WHERE giveaway=$1 AND active",gid) if False else []
    if not g or not p: return await m.answer("Join first: /join "+str(gid))
    lines=[f"📋 <b>{g['title']}</b>",f"🎯 Entries: {p['total_entries']}",
           f"💬 Chat: {p['messages']}/{g['chat_target'] or 0}"+(" (mandatory)" if g['chat_target'] else " (none)"),
           f"🤖 Captcha: {'✅' if p['captcha'] else '❌'}"]
    if g['bio_bonus']: lines.append(f"📝 Bio bonus: add {g['bio_bonus']} (+1)")
    if g['name_bonus']: lines.append(f"🏷 Name bonus: add {g['name_bonus']} (+1)")
    if g['referral_bonus']: lines.append(f"👥 Referrals: +{g['referral_bonus']} per valid friend (cap {g['referral_cap']})")
    me=await m.bot.me()
    lines.append(f"\n🔗 Referral link:\nhttps://t.me/{me.username}?start=ref_{gid}_{m.from_user.id}")
    await m.answer("\n".join(lines),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Recheck",callback_data=f"recheck:{gid}")]]))

@router.callback_query(F.data.startswith("recheck:"))
async def recheck(cb:CallbackQuery):
    gid=int(cb.data.split(":")[1])
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1",gid)
        p=await c.fetchrow("SELECT * FROM participants WHERE giveaway=$1 AND user_id=$2",gid,cb.from_user.id)
    if not g or not p: return await cb.answer("Not participating.",show_alert=True)
    profile=await cb.bot.get_chat(cb.from_user.id)
    full=" ".join(filter(None,[profile.first_name,profile.last_name]))
    bonus=int(bool(g["bio_bonus"]) and g["bio_bonus"].casefold() in (profile.bio or "").casefold())+int(bool(g["name_bonus"]) and g["name_bonus"].casefold() in full.casefold())
    async with pool.acquire() as c:
        await c.execute("UPDATE participants SET bonus=$3,total_entries=1+$3+referral_entries WHERE giveaway=$1 AND user_id=$2",gid,cb.from_user.id,bonus)
    await cb.message.edit_text(f"✅ Bonus updated. Total entries: {1+bonus+p['referral_entries']}")

@router.callback_query(F.data=="my_entries")
async def my_entries(cb:CallbackQuery):
    async with pool.acquire() as c:
        rows=await c.fetch("SELECT giveaway,total_entries FROM participants WHERE user_id=$1",cb.from_user.id)
    await cb.message.edit_text("📊 <b>My Entries</b>\n"+("\n".join(f"#{r['giveaway']}: {r['total_entries']}" for r in rows) or "None yet."))
