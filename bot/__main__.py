import json
from glob import glob
from importlib import import_module
from traceback import format_exc

from . import CACHE, LOGS, Var, bot, db, loop
from redis.asyncio import Redis


async def sync_redis_to_cache(redis_db: Redis, cache: dict) -> None:
    """Load all task data from Redis into local CACHE on startup."""
    try:
        keys = await redis_db.keys()
        for key in keys:
            raw = await redis_db.get(key)
            if raw:
                cache[key] = json.loads(raw)
    except Exception as e:
        LOGS.exception("Failed to sync Redis to local cache: %s", e)


try:
    bot.start(bot_token=Var.BOT_TOKEN)
except Exception as e:
    LOGS.critical("Failed to start bot: %s", e)
    exit(1)

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
LOGS.info("Successfully synced Redis into local cache.")

LOGS.info("Bot started.")

try:
    bot.run_until_disconnected()
except KeyboardInterrupt:
    LOGS.info("Shutting down bot...")
    exit(0)
