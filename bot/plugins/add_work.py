import re as _re

from . import CACHE, FORWARD_MODE_KEY, LOGS, Var, bot, events, userbot
from .database.addwork_db import is_work_present, setup_work

# Regex to detect Telegram invite links
_INVITE_RE = _re.compile(r"(?:https?://)?t(?:elegram)?\.me/(?:\+|joinchat/)([a-zA-Z0-9_-]+)")


def _get_active_client():
    """Return the forwarding client based on current mode."""
    mode = CACHE.get(FORWARD_MODE_KEY, "bot")
    if mode == "userbot" and userbot:
        return userbot
    return bot


async def resolve_channel_name(chat_id: int) -> str:
    """Resolve a chat ID to a display name with username or ID fallback."""
    client = _get_active_client()
    try:
        entity = await client.get_entity(chat_id)
        title = getattr(entity, "title", None) or getattr(entity, "first_name", str(chat_id))
        username = getattr(entity, "username", None)
        if username:
            return f"{title} (@{username})"
        return f"{title} (ID: {chat_id})"
    except Exception:
        return f"Unknown (ID: {chat_id})"


async def _try_join_invite(conv, invite_hash: str) -> int | None:
    """Try to join a channel via invite link using userbot. Returns chat_id or None."""
    client = _get_active_client()
    try:
        from telethon.tl.functions.messages import ImportChatInviteRequest
        await conv.send_message(
            "🔗 Invite link detected. Attempting to join..."
        )
        updates = await client(ImportChatInviteRequest(invite_hash))
        chat = updates.chats[0]
        title = getattr(chat, "title", "Unknown")
        chat_id = -1000000000000 - chat.id if hasattr(chat, "id") else chat.id
        # Use the proper peer ID
        from telethon.utils import get_peer_id
        chat_id = get_peer_id(chat)
        await conv.send_message(
            f"✅ Successfully joined channel!\n"
            f"**Name** : {title}\n"
            f"**ID** : {chat_id}"
        )
        return chat_id
    except Exception as exc:
        exc_msg = str(exc).lower()
        # Channel requires admin approval — join request was sent
        if "requested to join" in exc_msg:
            LOGS.info("Join request sent for invite hash: %s", invite_hash)
            await conv.send_message(
                "⏳ **Join Request Sent**\n\n"
                "This channel requires admin approval.\n"
                "Once approved, add the channel using its ID.\n\n"
                "Try again with a different link or channel ID:"
            )
            return None
        LOGS.warning("Failed to join via invite: %s", exc)
        await conv.send_message(
            "⚠️ **Failed to join channel**\n\n"
            f"Error: {exc}\n\n"
            "Try again with a valid invite link or channel ID:"
        )
        return None


async def validate_channels(conv, inputs: list[str]) -> list[int] | None:
    """
    Validate a list of channel IDs or invite links.
    - Numeric IDs: validate access via active client, auto-join with userbot if needed
    - Invite links: auto-join with active client
    Returns list of resolved chat IDs, or None if any failed.
    """
    client = _get_active_client()
    resolved_ids = []
    failed = []

    for raw in inputs:
        # Check if it's an invite link
        match = _INVITE_RE.match(raw.strip())
        if match:
            invite_hash = match.group(1)
            chat_id = await _try_join_invite(conv, invite_hash)
            if chat_id is None:
                return None  # Abort on failed join — user will retry
            resolved_ids.append(chat_id)
            continue

        # Otherwise, parse as numeric ID
        try:
            chat_id = int(raw)
        except ValueError:
            failed.append(raw)
            continue

        # Try to access with the active client
        try:
            await client.get_entity(chat_id)
            resolved_ids.append(chat_id)
            continue
        except Exception:
            pass

        # If userbot is available and active client is bot, try userbot auto-join
        if userbot and client != userbot:
            try:
                await userbot.get_entity(chat_id)
                resolved_ids.append(chat_id)
                continue
            except Exception:
                pass

        # If bot is not the active client, try bot as fallback
        if client != bot:
            try:
                await bot.get_entity(chat_id)
                resolved_ids.append(chat_id)
                continue
            except Exception:
                pass

        failed.append(str(chat_id))

    if failed:
        failed_list = "\n".join(f"  • {cid}" for cid in failed)
        await conv.send_message(
            "⚠️ **Invalid Channel**\n\n"
            f"Could not access:\n{failed_list}\n\n"
            "Ensure:\n"
            "  • The ID is correct\n"
            "  • The bot/userbot has access\n"
            "  • The channel exists\n\n"
            "Try again:"
        )
        return None

    return resolved_ids


async def _ask_task_name(conv) -> str | None:
    """Ask for task name, retry on duplicate. Returns None only on /cancel."""
    while True:
        response = await conv.get_response()
        text = response.text
        if text.startswith("/cancel"):
            await conv.send_message("❌ Process aborted!")
            return None

        if await is_work_present(text):
            await conv.send_message(
                "⚠️ **Duplicate Name**\n\n"
                "A task with that name already exists.\n"
                "Please enter a different name:"
            )
            continue

        return text


async def _ask_channel_ids(conv, prompt: str) -> list[int] | None:
    """Ask for channel IDs or invite links, retry on errors. Returns None only on /cancel."""
    await conv.send_message(prompt)

    while True:
        response = await conv.get_response()
        text = response.text
        if text.startswith("/cancel"):
            await conv.send_message("❌ Process aborted!")
            return None

        # Split input into tokens (IDs or invite links), one per line
        tokens = [t.strip() for t in text.splitlines() if t.strip()]
        if not tokens:
            await conv.send_message(
                "⚠️ **Invalid Input**\n\n"
                "Please send channel IDs or invite links.\n"
                "Try again:"
            )
            continue

        # Check: if all tokens are non-invite and non-numeric, reject early
        has_valid = False
        for t in tokens:
            if _INVITE_RE.match(t.strip()) or t.lstrip("-").isdigit():
                has_valid = True
                break
        if not has_valid:
            await conv.send_message(
                "⚠️ **Invalid Input**\n\n"
                "Please send valid numeric channel IDs or invite links.\n"
                "Try again:"
            )
            continue

        result = await validate_channels(conv, tokens)
        if result is None:
            continue  # Retry — validate_channels already sent error message

        return result


@bot.on(events.NewMessage(incoming=True, pattern=r"^/add_task$"))
async def handle_add_task(event):
    if event.sender_id not in Var.ADMINS:
        return
    try:
        async with bot.conversation(event.sender_id, timeout=2000) as conv:
            # Step 1: Task name
            await conv.send_message(
                "✨ **Create New Forwarding Task**\n\n"
                "You can send /cancel anytime to abort.\n\n"
                "Ensure the bot/userbot has access to both\n"
                "source and target channels.\n\n"
                "Enter a name for this task:"
            )
            task_name = await _ask_task_name(conv)
            if task_name is None:
                return

            # Step 2: Source channels
            source_chats = await _ask_channel_ids(
                conv,
                "📥 **Source Channels**\n\n"
                "Send channel ID(s) or invite link(s).\n"
                "One entry per line.\n\n"
                "Example:\n"
                "-1001234567890\n"
                "https://t.me/+abcdef"
            )
            if source_chats is None:
                return

            # Step 3: Target channels
            target_chats = await _ask_channel_ids(
                conv,
                "📤 **Target Channels**\n\n"
                "Send channel ID(s) or invite link(s).\n"
                "One entry per line.\n\n"
                "Example:\n"
                "-1001111111111\n"
                "https://t.me/+xyz123"
            )
            if target_chats is None:
                return

            # Create the task
            await setup_work(work_name=task_name, source=source_chats, target=target_chats)

            # Build success message with resolved channel names
            source_names = [f"  • {await resolve_channel_name(cid)}" for cid in source_chats]
            target_names = [f"  • {await resolve_channel_name(cid)}" for cid in target_chats]

            await conv.send_message(
                "✅ **Forwarding Task Created**\n\n"
                f"**Task Name** : {task_name}\n\n"
                f"**Sources:**\n" + "\n".join(source_names) + "\n\n"
                f"**Targets:**\n" + "\n".join(target_names) + "\n\n"
                f"**Status** : Active\n\n"
                "Use /tasks to manage this task."
            )

    except TimeoutError:
        LOGS.info("Add task conversation timed out for user %s", event.sender_id)
