from aiogram import Router,F,Bot
from aiogram.filters import Command,CommandObject
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State,StatesGroup
from datetime import datetime,timedelta,timezone
from bot.db import pool
from bot.services.logs import audit,discover
router=Router()

class CW(StatesGroup):
    title=State(); prize=State(); duration=State(); winners=State(); channel=State(); chat=State(); bio=State(); name=State()

@router.callback_query(F.data=="host_create")
async def host_create(cb:CallbackQuery,state:FSMContext):
    await state.set_state(CW.title)
    await cb.message.edit_text("🚀 <b>Create Giveaway</b>\n✅ No approval needed.\n\n1️⃣ Send title:")

@router.message(CW.title)
async def s_title(m:Message,state:FSMContext):
    await state.update_data(title=m.text[:100]); await state.set_state(CW.prize)
    await m.answer("2️⃣ Send prize:")
@router.message(CW.prize)
async def s_prize(m:Message,state:FSMContext):
    await state.update_data(prize=m.text[:300]); await state.set_state(CW.duration)
    await m.answer("3️⃣ Duration (1m–90d):")
@router.message(CW.duration)
async def s_dur(m:Message,state:FSMContext):
    def parse(v):
        try: s=int(v[:-1])*{'m':60,'h':3600,'d':86400}[v[-1]]
        except Exception: return None
        return s if 60<=s<=7776000 else None
    sec=parse(m.text.strip())
    if not sec: return await m.answer("❌ Use 1m–90d.")
    await state.update_data(dur=sec); await state.set_state(CW.winners)
    await m.answer("4️⃣ Winners (1–100):")
@router.message(CW.winners)
async def s_win(m:Message,state:FSMContext):
    if not m.text.isdigit() or not 1<=int(m.text)<=100: return await m.answer("❌ 1–100.")
    await state.update_data(winners=int(m.text)); await state.set_state(CW.channel)
    await m.answer("5️⃣ Required channel (username or invite link). Send 'skip' to skip:")
@router.message(CW.channel)
async def s_chan(m:Message,state:FSMContext):
    await state.update_data(channel=m.text.strip()); await state.set_state(CW.chat)
    await m.answer("6️⃣ Chat activity: GROUP_ID:TARGET (e.g. -100123:20). 'skip' to disable:")
@router.message(CW.chat)
async def s_chat(m:Message,state:FSMContext):
    await state.update_data(chat=m.text.strip()); await state.set_state(CW.bio)
    await m.answer("7️⃣ Bio bonus keyword (+1). 'skip' to disable:")
@router.message(CW.bio)
async def s_bio(m:Message,state:FSMContext):
    await state.update_data(bio=m.text.strip()); await state.set_state(CW.name)
    await m.answer("8️⃣ Name bonus keyword (+1). 'skip' to disable:")
@router.message(CW.name)
async def finish(m:Message,state:FSMContext,bot:Bot):
    d=await state.get_data()
    async with pool.acquire() as c:
        gid=await c.fetchval("""INSERT INTO giveaways(host,title,prize,ends,winners,chat_id,chat_target,bio_bonus,name_bonus)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
          m.from_user.id,d['title'],d['prize'],datetime.now(timezone.utc)+timedelta(seconds=d['dur']),d['winners'],
          *( (int(d['chat'].split(':')[0]),int(d['chat'].split(':')[1])) if ':' in d['chat'] and d['chat']!='skip' else (None,0) ),
          '' if d['bio']=='skip' else d['bio'], '' if d['name']=='skip' else d['name'])
        if d['channel']!='skip':
            await c.execute("INSERT INTO giveaway_channels(giveaway,chat_id,link) VALUES($1,$2,$3)",gid,d['channel'],d['channel'])
        await c.execute("UPDATE users SET is_host=TRUE WHERE tg_id=$1",m.from_user.id)
    await state.clear()
    url=f"https://t.me/{(await bot.me()).username}?start=giveaway_{gid}"
    post=await discover(bot,f"🎉 <b>NEW GIVEAWAY</b>\n🎁 {d['prize']}\n👥 {d['winners']} winners\n🆔 #{gid}",InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Participate",url=url)]]))
    if post:
        async with pool.acquire() as c: await c.execute("UPDATE giveaways SET discovery_msg=$2 WHERE id=$1",gid,post.message_id)
    await audit(bot,"CREATED",m.from_user.id,gid,f"{d['title']} | {d['prize']}")
    await m.answer(f"✅ Created #{gid}. Add channels/chat/bonuses via /help commands.\n{url}")

@router.message(Command("mygiveaways"))
async def my(m:Message):
    async with pool.acquire() as c: rows=await c.fetch("SELECT * FROM giveaways WHERE host=$1 ORDER BY id DESC LIMIT 20",m.from_user.id)
    await m.answer("📋 <b>My Giveaways</b>\n"+("\n".join(f"#{r['id']} {r['title']} [{r['status']}]" for r in rows) or "None. Use /create"))

@router.message(Command("participants"))
async def parts(m:Message,command:CommandObject):
    gid=int(command.args or 0)
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT host FROM giveaways WHERE id=$1",gid)
        if not g or (g['host']!=m.from_user.id and m.from_user.id!=0): return await m.answer("❌ Not your giveaway.")
        rows=await c.fetch("SELECT user_id,messages,bonus,referral_entries,total_entries FROM participants WHERE giveaway=$1 LIMIT 100",gid)
    await m.answer("👥 Participants\n"+("\n".join(f"{r['user_id']}: {r['total_entries']} entries (chat {r['messages']}, bonus {r['bonus']}, ref {r['referral_entries']})" for r in rows) or "None"))

@router.message(Command("edit"))
async def edit(m:Message,command:CommandObject):
    args=(command.args or '').split(maxsplit=2)
    if len(args)<3: return await m.answer("Usage: /edit ID field value\nFields: title,prize,duration,winners")
    gid,field,value=int(args[0]),args[1],args[2]
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT host FROM giveaways WHERE id=$1",gid)
        if not g or g['host']!=m.from_user.id: return await m.answer("❌ Not your giveaway.")
        if field in("title","prize"): await c.execute(f"UPDATE giveaways SET {field}=$2 WHERE id=$1",gid,value[:500])
        elif field=="duration":
            sec=int(value[:-1])*{'m':60,'h':3600,'d':86400}[value[-1]]
            await c.execute("UPDATE giveaways SET ends=$2 WHERE id=$1",gid,datetime.now(timezone.utc)+timedelta(seconds=sec))
        elif field=="winners" and value.isdigit(): await c.execute("UPDATE giveaways SET winners=$2 WHERE id=$1",gid,int(value))
        else: return await m.answer("❌ Invalid field.")
    await audit(m.bot,"EDITED",m.from_user.id,gid,f"{field}={value}")
    await m.answer("✅ Updated.")

@router.message(Command("pause","resume","cancel"))
async def status_cmd(m:Message,command:CommandObject):
    gid=int(command.args or 0)
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT host FROM giveaways WHERE id=$1",gid)
        if not g or g['host']!=m.from_user.id: return await m.answer("❌ Not your giveaway.")
        await c.execute("UPDATE giveaways SET status=$2 WHERE id=$1",gid,{'pause':'paused','resume':'active','cancel':'cancelled'}[command.command])
    await audit(m.bot,command.command,m.from_user.id,gid)
    await m.answer("✅ Updated.")

@router.message(Command("draw","reroll"))
async def draw_cmd(m:Message,command:CommandObject,bot:Bot):
    from bot.services.draw import draw
    gid=int(command.args or 0)
    try:
        winners=await draw(bot,gid,m.from_user.id,command.command=="reroll")
    except ValueError as e: return await m.answer(f"❌ {e}")
    await m.answer("🏆 Winners: "+(", ".join(map(str,winners)) or "none"))
