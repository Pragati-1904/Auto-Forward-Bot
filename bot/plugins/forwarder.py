from . import LOGS, asyncio, bot, events
from .database.addwork_db import edit_work, get_tasks_for_source
from telethon.utils import get_peer_id


async def _forward_message(e, task: dict) -> None:
    """Forward a new message to all target channels for a given task."""
    if task.get("delay"):
        await asyncio.sleep(task["delay"])

    target_chats = task["target"]
    cross_ids = task["crossids"]
    blacklist_words = task["blacklist_words"]
    show_header = task.get("show_forward_header", False)
    use_blacklist = task.get("has_to_blacklist", False)

    for chat in target_chats:
        try:
            # Check blacklist
            if use_blacklist and blacklist_words:
                message_text = (e.message.message or "").lower()
                if any(word in message_text for word in blacklist_words):
                    continue

            if show_header:
                await e.message.forward_to(chat)
            else:
                msg = await e.client.send_message(chat, e.message)
                # Track cross-chat message IDs for edit forwarding
                cross_ids.setdefault(e.chat_id, {}).setdefault(e.id, {})[chat] = msg.id
                await edit_work(task["work_name"], crossids=cross_ids)
        except Exception as exc:
            LOGS.warning("Failed to forward message to %s: %s", chat, exc)


async def _forward_edit(e, task: dict) -> None:
    """Forward an edited message to all target channels for a given task."""
    cross_ids = task["crossids"]
    blacklist_words = task["blacklist_words"]
    use_blacklist = task.get("has_to_blacklist", False)

    # cross_ids keys are strings after JSON deserialization
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
            msg = await bot.get_messages(chat, ids=int(target_msg_id))
            if msg:
                await msg.edit(e.text)
        except Exception as exc:
            LOGS.warning("Failed to forward edit to chat %s: %s", chat_str, exc)


@bot.on(events.NewMessage(incoming=True))
async def handle_new_message(e):
    ch = await e.get_chat()
    chat_id = get_peer_id(ch)
    tasks = await get_tasks_for_source(chat_id)
    for task in tasks:
        if task.get("has_to_forward"):
            asyncio.ensure_future(_forward_message(e, task))


@bot.on(events.MessageEdited(incoming=True))
async def handle_message_edit(e):
    ch = await e.get_chat()
    chat_id = get_peer_id(ch)
    tasks = await get_tasks_for_source(chat_id)
    for task in tasks:
        if task.get("has_to_edit"):
            asyncio.ensure_future(_forward_edit(e, task))
