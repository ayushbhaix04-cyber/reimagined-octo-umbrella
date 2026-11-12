# GiveawayX — Telegram Giveaway Platform

Multi-host Telegram giveaway bot + Mini App. Any Telegram user can instantly become a host (no approval) and create/manage giveaways. Participants complete channel joins, captcha, optional chat-activity targets, and optional bio/name bonus tasks.

## Stack
- Bot: Python + aiogram 3
- API + Mini App backend: FastAPI
- Database: PostgreSQL (Neon)
- Cache/locks/captcha: Redis (Upstash)
- Hosting: Railway
- Mini App: static HTML/JS served by FastAPI

## Features
- Instant host onboarding (no approval)
- Create giveaways via bot or Mini App
- Global required channels (owner-managed)
- Per-giveaway required channels (public/private/request links)
- Math captcha with attempts + cooldown
- Mandatory chat-activity target (send N messages in a group)
- Optional bio/name bonus entries (+1 each)
- Referral entries with self-referral block and cap
- Weighted random draw, reroll, fixed-winner override (/winner, owner-only)
- Public Discovery Channel (all giveaways auto-posted)
- Private Log Channel (all audit events)
- Mini App dashboard: browse, join, requirements, leaderboard, host panel

## Environment variables
BOT_TOKEN, DATABASE_URL, REDIS_URL, OWNER_ID, LOG_CHANNEL_ID, DISCOVERY_CHANNEL_ID, WEBAPP_URL, SUPPORT_USERNAME

## Run locally
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --port 8000 &
python -m bot.main

## Deploy (Railway)
1. Push to GitHub, connect repo in Railway.
2. Add Postgres (Neon) via DATABASE_URL and Redis (Upstash) via REDIS_URL.
3. Set BOT_TOKEN, OWNER_ID, LOG_CHANNEL_ID, DISCOVERY_CHANNEL_ID.
4. Deploy. Schema auto-initializes on first start.
