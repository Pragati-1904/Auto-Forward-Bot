import asyncio
import logging

from redis.asyncio import Redis
from telethon import TelegramClient

from .config import Var

logging.basicConfig(
    format="%(asctime)s || %(name)s [%(levelname)s] : %(message)s",
    level=logging.INFO,
    datefmt="%m/%d/%Y, %H:%M:%S",
)
LOGS = logging.getLogger(__name__)
logging.getLogger("Telethon").setLevel(logging.INFO)

# Create a shared event loop for Telethon compatibility
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

try:
    LOGS.info("Connecting to Telegram...")
    bot = TelegramClient(None, Var.API_ID, Var.API_HASH, loop=loop)
    LOGS.info("Successfully connected to Telegram.")
except Exception as e:
    LOGS.critical("Failed to create Telegram client: %s", e)
    exit(1)

try:
    db = Redis.from_url(Var.REDIS_URL, decode_responses=True)
    CACHE: dict[str, dict] = {}
except Exception as e:
    LOGS.critical("Failed to connect to Redis: %s", e)
    exit(1)
