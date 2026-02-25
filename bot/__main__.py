import json
from glob import glob
from importlib import import_module
from traceback import format_exc

import bot as _bot_pkg
from . import CACHE, FORWARD_MODE_KEY, LOGS, Var, bot, db, loop, userbot
from redis.asyncio import Redis


async def sync_redis_to_cache(redis_db: Redis, cache: dict) -> None:
    """Load all task data from Redis into local CACHE on startup."""
    try:
        keys = await redis_db.keys()
        for key in keys:
            if key == FORWARD_MODE_KEY:
                continue
            raw = await redis_db.get(key)
            if raw:
                cache[key] = json.loads(raw)
    except Exception as e:
        LOGS.exception("Failed to sync Redis to local cache: %s", e)


async def load_forward_mode(redis_db: Redis, cache: dict) -> None:
    """Load the forwarding mode from Redis into CACHE."""
    mode = await redis_db.get(FORWARD_MODE_KEY)
    if mode not in ("bot", "userbot"):
        mode = "bot"
    # Auto-correct: if mode is userbot but client is unavailable
    if mode == "userbot" and not _bot_pkg.userbot:
        LOGS.warning("Forward mode is 'userbot' but userbot unavailable. Falling back to 'bot'.")
        mode = "bot"
        await redis_db.set(FORWARD_MODE_KEY, mode)
    cache[FORWARD_MODE_KEY] = mode
    LOGS.info("Forwarding mode: %s", mode)


# --- Start the bot client ---
try:
    bot.start(bot_token=Var.BOT_TOKEN)
except Exception as e:
    LOGS.critical("Failed to start bot: %s", e)
    exit(1)

# --- Start the userbot client (if available) ---
if userbot:
    try:
        userbot.start()
        LOGS.info("Userbot client started.")
    except Exception as e:
        LOGS.error("Failed to start userbot: %s (falling back to bot)", e)
        _bot_pkg.userbot = None

# Dynamically load all plugin modules
plugins = sorted(glob("bot/plugins/*.py"))
for plugin in plugins:
    if plugin.endswith("_.py"):
        continue
    module_path = plugin.replace(".py", "").replace("/", ".").replace("\\", ".")
    try:
        import_module(module_path)
        LOGS.info("Loaded plugin: %s", module_path)
    except Exception:
        LOGS.error("Failed to load plugin: %s\n%s", module_path, format_exc())

LOGS.info("Syncing Redis into local cache...")
loop.run_until_complete(sync_redis_to_cache(db, CACHE))
loop.run_until_complete(load_forward_mode(db, CACHE))
LOGS.info("Successfully synced Redis into local cache.")

LOGS.info("Bot started.")

try:
    bot.run_until_disconnected()
except KeyboardInterrupt:
    LOGS.info("Shutting down bot...")
    exit(0)
