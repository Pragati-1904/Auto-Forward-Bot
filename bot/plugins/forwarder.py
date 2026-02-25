from . import CACHE, FORWARD_MODE_KEY, LOGS, asyncio, bot, events, userbot
from .database.addwork_db import edit_work, get_tasks_for_source
from telethon.utils import get_peer_id


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
    is_bot_event = (e.client == bot)
    if mode == "bot" and not is_bot_event:
        return False
    if mode == "userbot" and is_bot_event:
        return False
    return True


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

    for chat in target_chats:
        try:
            if use_blacklist and blacklist_words:
                message_text = (e.message.message or "").lower()
                if any(word in message_text for word in blacklist_words):
                    continue

            if show_header:
                msg = await client.get_messages(e.chat_id, ids=e.id)
                if msg:
                    await msg.forward_to(chat)
                else:
                    await e.message.forward_to(chat)
            else:
                msg = await client.send_message(chat, e.message)
                cross_ids.setdefault(str(e.chat_id), {}).setdefault(str(e.id), {})[str(chat)] = msg.id
                await edit_work(task["work_name"], crossids=cross_ids)
        except Exception as exc:
            LOGS.warning("Failed to forward message to %s: %s", chat, exc)


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

    for chat_str, target_msg_id in mapped.items():
        try:
            if use_blacklist and blacklist_words:
                message_text = (e.message.message or "").lower()
                if any(word in message_text for word in blacklist_words):
                    continue

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

        for chat_str, target_msg_id in mapped.items():
            try:
                await client.delete_messages(int(chat_str), int(target_msg_id))
            except Exception as exc:
                LOGS.warning("Failed to delete message in chat %s: %s", chat_str, exc)

        chat_map.pop(msg_id_key, None)

    cross_ids[chat_id_key] = chat_map
    await edit_work(task["work_name"], crossids=cross_ids)


# ──────────────────────────────────────────────
#  Shared handler logic
# ──────────────────────────────────────────────

async def _on_new_message(e):
    if not _should_process(e):
        return
    ch = await e.get_chat()
    chat_id = get_peer_id(ch)
    tasks = await get_tasks_for_source(chat_id)
    for task in tasks:
        if task.get("has_to_forward"):
            asyncio.ensure_future(_forward_message(e, task))


async def _on_message_edit(e):
    if not _should_process(e):
        return
    ch = await e.get_chat()
    chat_id = get_peer_id(ch)
    tasks = await get_tasks_for_source(chat_id)
    for task in tasks:
        if task.get("has_to_edit"):
            asyncio.ensure_future(_forward_edit(e, task))


async def _on_message_delete(e):
    if not _should_process(e):
        return
    chat_id = e.chat_id
    if not chat_id:
        return
    tasks = await get_tasks_for_source(chat_id)
    for task in tasks:
        if task.get("has_to_forward"):
            asyncio.ensure_future(_delete_forwarded(chat_id, e.deleted_ids, task))


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
    @userbot.on(events.NewMessage(incoming=True))
    async def handle_new_message_userbot(e):
        await _on_new_message(e)

    @userbot.on(events.MessageEdited(incoming=True))
    async def handle_message_edit_userbot(e):
        await _on_message_edit(e)

    @userbot.on(events.MessageDeleted())
    async def handle_message_delete_userbot(e):
        await _on_message_delete(e)
