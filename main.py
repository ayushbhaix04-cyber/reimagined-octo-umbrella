from fastapi import FastAPI,HTTPException,Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import hmac, hashlib, json, os, time
from bot.db import pool
from bot.config import BOT_TOKEN

app=FastAPI(title="GiveawayX API")

def validate_init(init_data:str)->dict:
    try:
        pairs=dict(pair.split("=",1) for pair in init_data.split("&"))
        hash_=pairs.pop("hash")
        check="\n".join(f"{k}={v}" for k,v in sorted(pairs.items()))
        secret=hmac.new(b"WebAppData",BOT_TOKEN.encode(),hashlib.sha256).digest()
        calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if calc!=hash_: raise ValueError("bad signature")
        user=json.loads(pairs["user"])
        if time.time()-int(pairs["auth_date"])>86400: raise ValueError("expired")
        return user
    except Exception as e: raise HTTPException(401,"Invalid Telegram initData")

@app.get("/api/giveaways")
async def giveaways(request:Request):
    async with pool.acquire() as c:
        rows=await c.fetch("SELECT id,title,prize,winners,ends FROM giveaways WHERE status='active' AND ends>now() ORDER BY id DESC LIMIT 50")
    return [dict(r) for r in rows]

@app.post("/api/join/{gid}")
async def join(gid:int,request:Request):
    init=request.headers.get("Authorization","").replace("tma ","")
    user=validate_init(init)
    async with pool.acquire() as c:
        p=await c.fetchrow("SELECT * FROM participants WHERE giveaway=$1 AND user_id=$2",gid,user["id"])
        if not p:
            await c.execute("INSERT INTO participants(giveaway,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",gid,user["id"])
    return {"ok":True,"message":"Check bot for captcha and requirements."}

@app.get("/api/requirements/{gid}")
async def requirements(gid:int,request:Request):
    init=request.headers.get("Authorization","").replace("tma ","")
    user=validate_init(init)
    async with pool.acquire() as c:
        g=await c.fetchrow("SELECT * FROM giveaways WHERE id=$1",gid)
        p=await c.fetchrow("SELECT * FROM participants WHERE giveaway=$1 AND user_id=$2",gid,user["id"])
        chans=await c.fetch("SELECT title,link FROM giveaway_channels WHERE giveaway=$1",gid)
    if not g: raise HTTPException(404)
    return {"giveaway":dict(g),"participant":dict(p) if p else None,"channels":[dict(c) for c in chans]}

@app.get("/api/leaderboard/{gid}")
async def leaderboard(gid:int,request:Request):
    init=request.headers.get("Authorization","").replace("tma ","")
    validate_init(init)
    async with pool.acquire() as c:
        rows=await c.fetch("SELECT user_id,total_entries FROM participants WHERE giveaway=$1 ORDER BY total_entries DESC LIMIT 20",gid)
    return [dict(r) for r in rows]

@app.get("/health")
async def health(): return {"ok":True}

app.mount("/miniapp",StaticFiles(directory="miniapp",html=True),name="miniapp")
