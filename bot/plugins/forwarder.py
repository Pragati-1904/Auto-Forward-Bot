import time

from . import CACHE, FORWARD_MODE_KEY, LOGS, asyncio, bot, events, userbot
from .database.addwork_db import edit_work, get_tasks_for_source

# Crossids entries older than this (seconds) are pruned
_CROSSIDS_TTL = 2 * 24 * 3600  # 2 days


def _get_active_client():
    """Return the client that should perform forwarding actions."""
    mode = CACHE.get(FORWARD_MODE_KEY, "bot")
    if mode == "userbot" and userbot:
        return userbot
    return bot


def _should_process(e) -> bool:
    """Dedup check: only process if the receiving client matches the active mode."""
    if not userbot:
        return True
    mode = CACHE.get(FORWARD_MODE_KEY, "bot")
    is_bot_event = (e.client is bot)
    if mode == "bot" and not is_bot_event:
        return False
    if mode == "userbot" and is_bot_event:
        return False
    return True


async def _send_to_target(client, chat, e, show_header: bool):
    """Send a single message to one target chat. Returns (chat, msg_id) or None."""
    if show_header:
        await e.message.forward_to(chat)
        return None
    else:
        msg = await client.send_message(chat, e.message)
        return (chat, msg.id)


async def _forward_message(e, task: dict) -> None:
    """Forward a new message to all target channels for a given task."""
    if task.get("delay"):
        await asyncio.sleep(task["delay"])

    client = _get_active_client()
    target_chats = task["target"]
    cross_ids = task["crossids"]
    blacklist_words = task["blacklist_words"]
    show_header = task.get("show_forward_header", False)
    use_blacklist = task.get("has_to_blacklist", False)

    # Blacklist check — done once, skip entire message if matched
    if use_blacklist and blacklist_words:
        message_text = (e.message.message or "").lower()
        if any(word in message_text for word in blacklist_words):
            return

    # Fire off all targets in parallel
    coros = [_send_to_target(client, chat, e, show_header) for chat in target_chats]
    results = await asyncio.gather(*coros, return_exceptions=True)

    # Collect crossids from successful sends (non-header mode only)
    ts = int(time.time())
    needs_persist = False
    for result in results:
        if isinstance(result, Exception):
            LOGS.warning("Failed to forward message: %s", result)
        elif result is not None:
            chat, msg_id = result
            entry = cross_ids.setdefault(str(e.chat_id), {}).setdefault(str(e.id), {})
            entry[str(chat)] = {"id": msg_id, "ts": ts}
            needs_persist = True

    # Single Redis write after all targets
    if needs_persist:
        await edit_work(task["work_name"], crossids=cross_ids)


async def _forward_edit(e, task: dict) -> None:
    """Forward an edited message to all target channels for a given task."""
    client = _get_active_client()
    cross_ids = task["crossids"]
    blacklist_words = task["blacklist_words"]
    use_blacklist = task.get("has_to_blacklist", False)

    chat_id_key = str(e.chat_id)
    msg_id_key = str(e.id)

    mapped = cross_ids.get(chat_id_key, {}).get(msg_id_key)
    if not mapped:
        return

    if use_blacklist and blacklist_words:
        message_text = (e.message.message or "").lower()
        if any(word in message_text for word in blacklist_words):
            return

    for chat_str, value in mapped.items():
        try:
            # Backward compat: value can be int (old format) or dict (new format)
            target_msg_id = value["id"] if isinstance(value, dict) else value
            chat = int(chat_str)
            msg = await client.get_messages(chat, ids=int(target_msg_id))
            if msg:
                await msg.edit(e.text)
        except Exception as exc:
            LOGS.warning("Failed to forward edit to chat %s: %s", chat_str, exc)


async def _delete_forwarded(chat_id: int, deleted_ids: list[int], task: dict) -> None:
    """Delete forwarded messages in target channels when source messages are deleted."""
    client = _get_active_client()
    cross_ids = task["crossids"]
    chat_id_key = str(chat_id)

    chat_map = cross_ids.get(chat_id_key, {})
    if not chat_map:
        return

    for msg_id in deleted_ids:
        msg_id_key = str(msg_id)
        mapped = chat_map.get(msg_id_key)
        if not mapped:
            continue

        for chat_str, value in mapped.items():
            try:
                target_msg_id = value["id"] if isinstance(value, dict) else value
                await client.delete_messages(int(chat_str), int(target_msg_id))
            except Exception as exc:
                LOGS.warning("Failed to delete message in chat %s: %s", chat_str, exc)

        chat_map.pop(msg_id_key, None)

    cross_ids[chat_id_key] = chat_map
    await edit_work(task["work_name"], crossids=cross_ids)


# ──────────────────────────────────────────────
#  Crossids cleanup (hourly, prunes entries > 2 days)
# ──────────────────────────────────────────────

async def _cleanup_crossids():
    """Periodically prune old crossids entries to prevent unbounded growth."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        try:
            now = int(time.time())
            for task_name, task in list(CACHE.items()):
                if not isinstance(task, dict) or "crossids" not in task:
                    continue
                cross_ids = task["crossids"]
                changed = False
                for chat_key in list(cross_ids.keys()):
                    msg_map = cross_ids[chat_key]
                    for msg_key in list(msg_map.keys()):
                        entry = msg_map[msg_key]
                        # Check any target's timestamp; if all are old format (no ts), skip
                        should_prune = False
                        for value in entry.values():
                            if isinstance(value, dict) and "ts" in value:
                                if now - value["ts"] > _CROSSIDS_TTL:
                                    should_prune = True
                                break
                        if should_prune:
                            del msg_map[msg_key]
                            changed = True
                    # Clean up empty chat maps
                    if not msg_map:
                        del cross_ids[chat_key]
                        changed = True
                if changed:
                    await edit_work(task_name, crossids=cross_ids)
            LOGS.info("Crossids cleanup completed.")
        except Exception as exc:
            LOGS.warning("Crossids cleanup error: %s", exc)


# Start the cleanup task
asyncio.ensure_future(_cleanup_crossids())


# ──────────────────────────────────────────────
#  Shared handler logic
# ──────────────────────────────────────────────

async def _on_new_message(e):
    # Skip outgoing non-channel messages (channel posts appear as "out" for userbots)
    if getattr(e, "out", False) and not getattr(e, "is_channel", False):
        return
    if not _should_process(e):
        return
    try:
        chat_id = e.chat_id
        if not chat_id:
            return
        tasks = await get_tasks_for_source(chat_id)
        for task in tasks:
            if task.get("has_to_forward"):
                asyncio.ensure_future(_forward_message(e, task))
    except Exception as exc:
        LOGS.warning("Error in new message handler: %s", exc)


async def _on_message_edit(e):
    if getattr(e, "out", False):
        return
    if not _should_process(e):
        return
    try:
        chat_id = e.chat_id
        if not chat_id:
            return
        tasks = await get_tasks_for_source(chat_id)
        for task in tasks:
            if task.get("has_to_edit"):
                asyncio.ensure_future(_forward_edit(e, task))
    except Exception as exc:
        LOGS.warning("Error in message edit handler: %s", exc)


async def _on_message_delete(e):
    if not _should_process(e):
        return
    try:
        chat_id = e.chat_id
        if not chat_id:
            return
        tasks = await get_tasks_for_source(chat_id)
        for task in tasks:
            if task.get("has_to_forward"):
                asyncio.ensure_future(_delete_forwarded(chat_id, e.deleted_ids, task))
    except Exception as exc:
        LOGS.warning("Error in message delete handler: %s", exc)


# ──────────────────────────────────────────────
#  Register handlers on bot (always)
# ──────────────────────────────────────────────

@bot.on(events.NewMessage(incoming=True))
async def handle_new_message_bot(e):
    await _on_new_message(e)


@bot.on(events.MessageEdited(incoming=True))
async def handle_message_edit_bot(e):
    await _on_message_edit(e)


@bot.on(events.MessageDeleted())
async def handle_message_delete_bot(e):
    await _on_message_delete(e)


# ──────────────────────────────────────────────
#  Register handlers on userbot (if available)
# ──────────────────────────────────────────────

if userbot:
    @userbot.on(events.NewMessage())  # No incoming=True — channels post as "out"
    async def handle_new_message_userbot(e):
        await _on_new_message(e)

    @userbot.on(events.MessageEdited())
    async def handle_message_edit_userbot(e):
        await _on_message_edit(e)

    @userbot.on(events.MessageDeleted())
    async def handle_message_delete_userbot(e):
        await _on_message_delete(e)
