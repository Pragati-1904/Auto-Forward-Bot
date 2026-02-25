import asyncio
import logging

from redis.asyncio import Redis
from telethon import TelegramClient
from telethon.sessions import StringSession

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

# Redis key for storing the forwarding mode ("bot" or "userbot")
FORWARD_MODE_KEY = "__FORWARD_MODE__"

# --- Bot client (always created) ---
try:
    LOGS.info("Creating bot client...")
    bot = TelegramClient(None, Var.API_ID, Var.API_HASH, loop=loop)
    LOGS.info("Bot client created.")
except Exception as e:
    LOGS.critical("Failed to create bot client: %s", e)
    exit(1)

# --- Userbot client (only if SESSION_STRING is provided) ---
userbot: TelegramClient | None = None
if Var.SESSION_STRING:
    try:
        LOGS.info("Creating userbot client...")
        userbot = TelegramClient(
            StringSession(Var.SESSION_STRING), Var.API_ID, Var.API_HASH, loop=loop
        )
        LOGS.info("Userbot client created.")
    except Exception as e:
        LOGS.error("Failed to create userbot client: %s", e)
        userbot = None
else:
    LOGS.info("SESSION_STRING not provided. Userbot disabled.")

# --- Redis ---
try:
    db = Redis.from_url(Var.REDIS_URL, decode_responses=True)
    CACHE: dict[str, dict] = {}
except Exception as e:
    LOGS.critical("Failed to connect to Redis: %s", e)
    exit(1)


async def get_forward_mode() -> str:
    """Read the current forwarding mode from Redis. Defaults to 'bot'."""
    mode = await db.get(FORWARD_MODE_KEY)
    if mode not in ("bot", "userbot"):
        return "bot"
    return mode


async def set_forward_mode(mode: str) -> None:
    """Persist the forwarding mode to Redis."""
    await db.set(FORWARD_MODE_KEY, mode)
