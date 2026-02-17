from . import LOGS, Button, Var, bot, events, re
from .database.addwork_db import (
    delete_work,
    edit_work,
    get_all_work_names,
    get_work,
    is_work_present,
    rename_work,
)


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _back_button(task_name: str) -> list:
    return [[Button.inline("« Back to Task", data=f"edwrk_{task_name}")]]


def _back_to_list_button() -> list:
    return [[Button.inline("« Back to Tasks", data="bek")]]


def _build_task_list_buttons(work_names) -> list:
    buttons = [Button.inline(f"{x}", data=f"edwrk_{x}") for x in work_names]
    return [list(buttons[i:i + 3]) for i in range(0, len(buttons), 3)]


def _task_detail_text(task_name: str, data: dict) -> str:
    """Build the task details screen text."""
    status = "Running" if data.get("has_to_forward") else "Paused"
    status_icon = "🟢" if data.get("has_to_forward") else "🔴"
    header = "Enabled" if data.get("show_forward_header") else "Disabled"
    mode = "Forward Header" if data.get("show_forward_header") else "Copy Mode"
    delay = data.get("delay", 0)
    blacklist = "On" if data.get("has_to_blacklist") else "Off"
    edit_sync = "On" if data.get("has_to_edit") else "Off"

    return (
        f"📋 **Task Details**\n\n"
        f"**Name** : {task_name}\n"
        f"**Status** : {status_icon} {status}\n"
        f"**Mode** : {mode}\n"
        f"**Header** : {header}\n"
        f"**Delay** : {delay}s\n"
        f"**Blacklist** : {blacklist}\n"
        f"**Edit Sync** : {edit_sync}"
    )


def _task_detail_buttons(task_name: str, data: dict) -> list:
    """Build the inline buttons for the task details screen."""
    # Dynamic toggle labels
    fwd_label = "Pause" if data.get("has_to_forward") else "Resume"
    fwd_data = f"disfor_{task_name}" if data.get("has_to_forward") else f"enfor_{task_name}"

    header_label = "Disable Header" if data.get("show_forward_header") else "Enable Header"
    bl_label = "Disable Blacklist" if data.get("has_to_blacklist") else "Enable Blacklist"
    edit_label = "Disable Edit Sync" if data.get("has_to_edit") else "Enable Edit Sync"

    return [
        [
            Button.inline(fwd_label, data=fwd_data),
            Button.inline(header_label, data=f"hedfor_{task_name}"),
        ],
        [
            Button.inline("Edit Name", data=f"ned_{task_name}"),
            Button.inline("Edit Delay", data=f"ded_{task_name}"),
        ],
        [
            Button.inline("Edit Source", data=f"sed_{task_name}"),
            Button.inline("Edit Destination", data=f"ted_{task_name}"),
        ],
        [
            Button.inline("Edit Blacklist", data=f"bled_{task_name}"),
            Button.inline(bl_label, data=f"bkhas_{task_name}"),
        ],
        [Button.inline(edit_label, data=f"ehas_{task_name}")],
        [Button.inline("Delete Task", data=f"delt_{task_name}")],
        [Button.inline("« Back", data="bek")],
    ]


async def _send_task_detail(e, task_name: str):
    """Edit the current message to show task details."""
    data = await get_work(task_name)
    text = _task_detail_text(task_name, data)
    buttons = _task_detail_buttons(task_name, data)
    await e.edit(text, buttons=buttons)


async def _conv_send_task_detail(conv, task_name: str):
    """Send task details as a new message in a conversation."""
    data = await get_work(task_name)
    text = _task_detail_text(task_name, data)
    buttons = _task_detail_buttons(task_name, data)
    await conv.send_message(text, buttons=buttons)


# ──────────────────────────────────────────────
#  Task List
# ──────────────────────────────────────────────

TASK_LIST_TEXT = (
    "📂 **Forwarding Tasks**\n\n"
    "• Choose a task to view or manage\n"
    "• View configuration details\n"
    "• Modify settings and control execution"
)

NO_TASKS_TEXT = (
    "📂 **Forwarding Tasks**\n\n"
    "No tasks found.\n"
    "Use /add\\_task to create one."
)


@bot.on(events.NewMessage(incoming=True, pattern=r"^/tasks$"))
async def handle_tasks(event):
    if event.sender_id not in Var.ADMINS:
        return
    work_names = await get_all_work_names()
    if not work_names:
        return await event.reply(NO_TASKS_TEXT)
    buttons = _build_task_list_buttons(work_names)
    await event.reply(TASK_LIST_TEXT, buttons=buttons)


@bot.on(events.callbackquery.CallbackQuery(data=re.compile("bek")))
async def handle_back_to_list(event):
    work_names = await get_all_work_names()
    if not work_names:
        return await event.edit(NO_TASKS_TEXT)
    buttons = _build_task_list_buttons(work_names)
    await event.edit(TASK_LIST_TEXT, buttons=buttons)


# ──────────────────────────────────────────────
#  Task Details
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"edwrk_(.*)")))
async def handle_task_detail(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    await _send_task_detail(e, task_name)


# ──────────────────────────────────────────────
#  Edit Name
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"ned_(.*)")))
async def handle_edit_name(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    try:
        async with bot.conversation(e.sender_id, timeout=2000) as conv:
            await e.delete()
            await conv.send_message(
                "✏️ **Edit Task Name**\n\n"
                f"Current name: **{task_name}**\n\n"
                "Send the new name for this task.\n"
                "Send /cancel to go back."
            )

            while True:
                response = await conv.get_response()
                text = response.text
                if text.startswith("/cancel"):
                    return await _conv_send_task_detail(conv, task_name)

                if await is_work_present(text):
                    await conv.send_message(
                        "⚠️ **Duplicate Name**\n\n"
                        "A task with that name already exists.\n"
                        "Please enter a different name:"
                    )
                    continue

                await rename_work(task_name, text)
                await conv.send_message(
                    f"✅ **Task Renamed**\n\n"
                    f"New name: **{text}**",
                    buttons=_back_button(text),
                )
                return
    except TimeoutError:
        LOGS.info("Edit name conversation timed out for user %s", e.sender_id)


# ──────────────────────────────────────────────
#  Edit Delay
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"ded_(.*)")))
async def handle_edit_delay(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    try:
        async with bot.conversation(e.sender_id, timeout=2000) as conv:
            await e.delete()
            await conv.send_message(
                "⏱ **Edit Delay**\n\n"
                f"Current delay: **{task_data.get('delay', 0)}s**\n\n"
                "Send the new delay time in seconds.\n"
                "Example: 120\n\n"
                "Send /cancel to go back."
            )

            while True:
                response = await conv.get_response()
                text = response.text
                if text.startswith("/cancel"):
                    return await _conv_send_task_detail(conv, task_name)

                try:
                    delay_seconds = int(text)
                except ValueError:
                    await conv.send_message(
                        "⚠️ **Invalid Input**\n\n"
                        "Please send a valid number in seconds.\n"
                        "Try again:"
                    )
                    continue

                await edit_work(work_name=task_name, delay=delay_seconds)
                await conv.send_message(
                    f"✅ **Delay Updated**\n\n"
                    f"New delay: **{delay_seconds}s**",
                    buttons=_back_button(task_name),
                )
                return
    except TimeoutError:
        LOGS.info("Edit delay conversation timed out for user %s", e.sender_id)


# ──────────────────────────────────────────────
#  Edit Source
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"sed_(.*)")))
async def handle_edit_source(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    current = "\n".join(f"  • {cid}" for cid in task_data.get("source", []))
    try:
        async with bot.conversation(e.sender_id, timeout=2000) as conv:
            await e.delete()
            await conv.send_message(
                "📥 **Edit Source Channels**\n\n"
                f"Current sources:\n{current}\n\n"
                "Send the new source channel ID(s).\n"
                "Separate multiple IDs with a space.\n\n"
                "Send /cancel to go back."
            )

            while True:
                response = await conv.get_response()
                text = response.text
                if text.startswith("/cancel"):
                    return await _conv_send_task_detail(conv, task_name)

                try:
                    source_chats = [int(i) for i in text.split()]
                except ValueError:
                    await conv.send_message(
                        "⚠️ **Invalid Input**\n\n"
                        "Please send valid numeric channel IDs.\n"
                        "Try again:"
                    )
                    continue

                failed = []
                for cid in source_chats:
                    try:
                        await bot.get_entity(cid)
                    except Exception:
                        failed.append(cid)

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

                await edit_work(work_name=task_name, source=source_chats)
                await conv.send_message(
                    "✅ **Source Channels Updated**",
                    buttons=_back_button(task_name),
                )
                return
    except TimeoutError:
        LOGS.info("Edit source conversation timed out for user %s", e.sender_id)


# ──────────────────────────────────────────────
#  Edit Destination
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"ted_(.*)")))
async def handle_edit_target(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    current = "\n".join(f"  • {cid}" for cid in task_data.get("target", []))
    try:
        async with bot.conversation(e.sender_id, timeout=2000) as conv:
            await e.delete()
            await conv.send_message(
                "📤 **Edit Target Channels**\n\n"
                f"Current targets:\n{current}\n\n"
                "Send the new destination channel ID(s).\n"
                "Separate multiple IDs with a space.\n\n"
                "Send /cancel to go back."
            )

            while True:
                response = await conv.get_response()
                text = response.text
                if text.startswith("/cancel"):
                    return await _conv_send_task_detail(conv, task_name)

                try:
                    target_chats = [int(i) for i in text.split()]
                except ValueError:
                    await conv.send_message(
                        "⚠️ **Invalid Input**\n\n"
                        "Please send valid numeric channel IDs.\n"
                        "Try again:"
                    )
                    continue

                failed = []
                for cid in target_chats:
                    try:
                        await bot.get_entity(cid)
                    except Exception:
                        failed.append(cid)

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

                await edit_work(work_name=task_name, target=target_chats)
                await conv.send_message(
                    "✅ **Target Channels Updated**",
                    buttons=_back_button(task_name),
                )
                return
    except TimeoutError:
        LOGS.info("Edit target conversation timed out for user %s", e.sender_id)


# ──────────────────────────────────────────────
#  Edit Blacklist
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"bled_(.*)")))
async def handle_edit_blacklist(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    current = ", ".join(task_data.get("blacklist_words", [])) or "None"
    try:
        async with bot.conversation(e.sender_id, timeout=2000) as conv:
            await e.delete()
            await conv.send_message(
                "📋 **Edit Blacklist Words**\n\n"
                f"Current blacklist: {current}\n\n"
                "Send the new blacklist words.\n"
                "Separate multiple words with a space.\n\n"
                "Send /cancel to go back."
            )

            response = await conv.get_response()
            text = response.text
            if text.startswith("/cancel"):
                return await _conv_send_task_detail(conv, task_name)

            blacklisted_words = [word.lower() for word in text.split()]
            await edit_work(work_name=task_name, blacklist_words=blacklisted_words)
            await conv.send_message(
                "✅ **Blacklist Updated**\n\n"
                f"Words: {', '.join(blacklisted_words)}",
                buttons=_back_button(task_name),
            )
    except TimeoutError:
        LOGS.info("Edit blacklist conversation timed out for user %s", e.sender_id)


# ──────────────────────────────────────────────
#  Toggle Actions (single-click, no conversation)
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"disfor_(.*)")))
async def handle_disable_forward(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    await edit_work(work_name=task_name, has_to_forward=False)
    await _send_task_detail(e, task_name)


@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"enfor_(.*)")))
async def handle_enable_forward(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    await edit_work(work_name=task_name, has_to_forward=True)
    await _send_task_detail(e, task_name)


@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"hedfor_(.*)")))
async def handle_toggle_forward_header(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    new_value = not task_data.get("show_forward_header")
    await edit_work(work_name=task_name, show_forward_header=new_value)
    await _send_task_detail(e, task_name)


@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"bkhas_(.*)")))
async def handle_toggle_blacklist(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    new_value = not task_data.get("has_to_blacklist")
    await edit_work(work_name=task_name, has_to_blacklist=new_value)
    await _send_task_detail(e, task_name)


@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"ehas_(.*)")))
async def handle_toggle_edit(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    task_data = await get_work(task_name)
    new_value = not task_data.get("has_to_edit")
    await edit_work(work_name=task_name, has_to_edit=new_value)
    await _send_task_detail(e, task_name)


# ──────────────────────────────────────────────
#  Delete Task
# ──────────────────────────────────────────────

@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"delt_(.*)")))
async def handle_delete_task(e):
    task_name = e.pattern_match.group(1).decode("utf-8")
    await delete_work(task_name)
    await e.edit(
        f"🗑 **Task Deleted**\n\n"
        f"**{task_name}** has been removed.",
        buttons=_back_to_list_button(),
    )
