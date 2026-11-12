from aiogram import Bot
async def is_member(bot:Bot,chat,user)->bool:
    try:
        m=await bot.get_chat_member(chat,user)
        return m.status in {"creator","administrator","member"} or (m.status=="restricted" and m.is_member)
    except Exception: return False
