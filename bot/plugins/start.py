from . import CACHE, Button, Var, bot, events, re
from .database.addwork_db import get_all_work_names

START_TEXT = (
    "🚀 **Auto Forward Bot**\n\n"
    "• Forward between any chats\n"
    "• Filter & transform content\n"
    "• Supports multiple forwarding routes\n"
    "• Zero latency delivery\n\n"
    "Use /help to manage settings and commands."
)

HELP_TEXT = (
    "💎 **Command Panel**\n\n"
    "/add_task  – Add a new forwarding task\n"
    "/tasks     – Manage existing tasks\n"
    "/status    – View system status\n"
    "/stats     – View forwarding statistics\n\n"
    "Use commands carefully."
)


@bot.on(events.NewMessage(incoming=True, pattern=r"^/start$"))
async def handle_start(e):
    await e.reply(START_TEXT, buttons=[[Button.inline("💎 Help", data="hlp")]])


@bot.on(events.callbackquery.CallbackQuery(data=re.compile("hlp")))
async def handle_help_callback(e):
    await e.edit(HELP_TEXT)


@bot.on(events.NewMessage(incoming=True, pattern=r"^/help$"))
async def handle_help(e):
    await e.reply(HELP_TEXT)


@bot.on(events.NewMessage(incoming=True, pattern=r"^/status$"))
async def handle_status(e):
    if e.sender_id not in Var.ADMINS:
        return
    work_names = await get_all_work_names()
    total = len(work_names)
    active = sum(1 for name in work_names if CACHE.get(name, {}).get("has_to_forward"))
    stopped = total - active

    txt = (
        "📊 **System Status**\n\n"
        f"**Total Tasks**: `{total}`\n"
        f"**Active**: `{active}`\n"
        f"**Stopped**: `{stopped}`\n"
        f"**Bot**: `Online`"
    )
    await e.reply(txt)


@bot.on(events.NewMessage(incoming=True, pattern=r"^/stats$"))
async def handle_stats(e):
    if e.sender_id not in Var.ADMINS:
        return
    work_names = await get_all_work_names()
    if not work_names:
        return await e.reply("📈 **Forwarding Statistics**\n\nNo tasks found.")

    lines = []
    for name in work_names:
        task = CACHE.get(name, {})
        status = "🟢" if task.get("has_to_forward") else "🔴"
        sources = len(task.get("source", []))
        targets = len(task.get("target", []))
        forwarded = sum(len(msgs) for msgs in task.get("crossids", {}).values())
        lines.append(
            f"{status} **{name}**\n"
            f"    Sources: `{sources}` │ Targets: `{targets}` │ Forwarded: `{forwarded}`"
        )

    txt = "📈 **Forwarding Statistics**\n\n" + "\n\n".join(lines)
    await e.reply(txt)
