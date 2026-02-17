from . import LOGS, Var, bot, events
from .database.addwork_db import is_work_present, setup_work


async def _resolve_channel_name(chat_id: int) -> str:
    """Resolve a chat ID to a display name with username or ID fallback."""
    try:
        entity = await bot.get_entity(chat_id)
        title = getattr(entity, "title", None) or getattr(entity, "first_name", str(chat_id))
        username = getattr(entity, "username", None)
        if username:
            return f"{title} (@{username})"
        return f"{title} (ID: {chat_id})"
    except Exception:
        return f"Unknown (ID: {chat_id})"


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
    """Ask for channel IDs, retry on parse or validation errors. Returns None only on /cancel."""
    await conv.send_message(prompt)

    while True:
        response = await conv.get_response()
        text = response.text
        if text.startswith("/cancel"):
            await conv.send_message("❌ Process aborted!")
            return None

        # Parse IDs
        try:
            chat_ids = [int(i) for i in text.split()]
        except ValueError:
            await conv.send_message(
                "⚠️ **Invalid Input**\n\n"
                "Please send valid numeric channel IDs.\n"
                "Try again:"
            )
            continue

        # Validate channels
        failed = []
        for chat_id in chat_ids:
            try:
                await bot.get_entity(chat_id)
            except Exception:
                failed.append(chat_id)

        if failed:
            failed_list = "\n".join(f"  • {cid}" for cid in failed)
            await conv.send_message(
                "⚠️ **Invalid Channel**\n\n"
                f"Could not access:\n{failed_list}\n\n"
                "Ensure:\n"
                "  • The ID is correct\n"
                "  • The bot is an admin\n"
                "  • The channel exists\n\n"
                "Try again:"
            )
            continue

        return chat_ids


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
                "Ensure the bot is an admin in both\n"
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
                "Send the source channel ID(s) in one message.\n"
                "Separate multiple IDs with a space.\n\n"
                "Example:\n"
                "-1001234567890 -1009876543210"
            )
            if source_chats is None:
                return

            # Step 3: Target channels
            target_chats = await _ask_channel_ids(
                conv,
                "📤 **Target Channels**\n\n"
                "Send the destination channel ID(s) in one message.\n"
                "Separate multiple IDs with a space.\n\n"
                "Example:\n"
                "-1001111111111 -1002222222222"
            )
            if target_chats is None:
                return

            # Create the task
            await setup_work(work_name=task_name, source=source_chats, target=target_chats)

            # Build success message with resolved channel names
            source_names = [f"  • {await _resolve_channel_name(cid)}" for cid in source_chats]
            target_names = [f"  • {await _resolve_channel_name(cid)}" for cid in target_chats]

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
