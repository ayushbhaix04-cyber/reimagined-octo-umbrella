import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN=os.environ["BOT_TOKEN"]
DATABASE_URL=os.environ["DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://")
REDIS_URL=os.environ["REDIS_URL"]
OWNER_ID=int(os.getenv("OWNER_ID","0"))
LOG_CHANNEL_ID=int(os.getenv("LOG_CHANNEL_ID","0"))
DISCOVERY_CHANNEL_ID=int(os.getenv("DISCOVERY_CHANNEL_ID","0"))
SUPPORT_USERNAME=os.getenv("SUPPORT_USERNAME","support")
