import secrets
from bot.db import pool
from bot.services.channels import is_member
async def eligible(bot,g,p)->bool:
    if not p["captcha"] or (g["chat_target"] and p["messages"]<g["chat_target"]): return False
    async with pool.acquire() as c:
        chans=await c.fetch("SELECT chat_id FROM giveaway_channels WHERE giveaway=$1 AND required",g["id"])
    for ch in chans:
        if not await is_member(bot,ch["chat_id"],p["user_id"]): return False
    if g["chat_id"] and not await is_member(bot,g["chat_id"],p["user_id"]): return False
    return True
async def draw(bot,gid,actor=None,reroll=False):
    async with pool.acquire() as c:
        async with c.transaction():
            g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1 FOR UPDATE",gid)
            if not g: raise ValueError("Giveaway not found")
            if actor is not None and actor!=g["host"] and actor!=0: raise ValueError("Not your giveaway")
            if not reroll and g["status"]!="active": return []
            if reroll and g["status"]!="ended": raise ValueError("Reroll requires ended giveaway")
            prev={r["user_id"] for r in await c.fetch("SELECT user_id FROM winners WHERE giveaway=$1",gid)}
            parts=await c.fetch("SELECT * FROM participants WHERE giveaway=$1 AND valid",gid)
            pool=[]
            for p in parts:
                if p["user_id"] in prev or not await eligible(bot,g,p): continue
                profile=await bot.get_chat(p["user_id"])
                full=" ".join(filter(None,[profile.first_name,profile.last_name]))
                bio=profile.bio or ""
                bonus=int(bool(g["bio_bonus"]) and g["bio_bonus"].casefold() in bio.casefold())+int(bool(g["name_bonus"]) and g["name_bonus"].casefold() in full.casefold())
                weight=1+p["bonus"]+bonus+p["referral_entries"]
                pool += [p["user_id"]]*weight
            winners=[]
            for _ in range(min(g["winners"],len(set(pool)))):
                if not pool: break
                w=secrets.choice(pool)
                while w in winners and pool: w=secrets.choice(pool)
                if w not in winners: winners.append(w)
            rnd=await c.fetchval("SELECT COALESCE(MAX(round),0)+1 FROM winners WHERE giveaway=$1",gid)
            for u in winners: await c.execute("INSERT INTO winners(giveaway,user_id,round,selection) VALUES($1,$2,$3,$4)",gid,u,rnd,"reroll" if reroll else "random")
            if not reroll: await c.execute("UPDATE giveaways SET status='ended' WHERE id=$1",gid)
    return winners
