from . import (
    CACHE, Button, FORWARD_MODE_KEY, Var,
    bot, events, re, set_forward_mode, userbot,
)
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
    "/add\\_task  – Add a new forwarding task\n"
    "/tasks     – Manage existing tasks\n"
    "/mode      – Switch forwarding client\n"
    "/status    – View system status\n"
    "/stats     – View forwarding statistics\n\n"
    "Use commands carefully."
)


def _start_buttons(is_admin: bool) -> list:
    rows = [[Button.inline("Help", data="hlp")]]
    if is_admin:
        rows.append([Button.inline("Forwarding Mode", data="fwd_mode")])
    return rows


@bot.on(events.NewMessage(incoming=True, pattern=r"^/start$"))
async def handle_start(e):
    is_admin = e.sender_id in Var.ADMINS
    await e.reply(START_TEXT, buttons=_start_buttons(is_admin))


@bot.on(events.callbackquery.CallbackQuery(data=re.compile("hlp")))
async def handle_help_callback(e):
    await e.edit(HELP_TEXT)


@bot.on(events.callbackquery.CallbackQuery(data=re.compile("back_start")))
async def handle_back_to_start(e):
    is_admin = e.sender_id in Var.ADMINS
    await e.edit(START_TEXT, buttons=_start_buttons(is_admin))


@bot.on(events.NewMessage(incoming=True, pattern=r"^/help$"))
async def handle_help(e):
    await e.reply(HELP_TEXT)


# ──────────────────────────────────────────────
#  Forwarding Mode Selection
# ──────────────────────────────────────────────

def _mode_text(current_mode: str) -> str:
    ub_available = "Yes" if userbot else "No"
    return (
        "**Forwarding Mode**\n\n"
        f"**Current** : {current_mode.capitalize()}\n"
        f"**Userbot Available** : {ub_available}\n\n"
        "Choose which client forwards messages.\n"
        "Commands always run on the Bot client."
    )


def _mode_buttons(current_mode: str) -> list:
    bot_label = "Bot  [active]" if current_mode == "bot" else "Bot"
    ub_label = "Userbot  [active]" if current_mode == "userbot" else "Userbot"
    return [
        [
            Button.inline(bot_label, data="set_mode_bot"),
            Button.inline(ub_label, data="set_mode_userbot"),
        ],
        [Button.inline("« Back", data="back_start")],
    ]


@bot.on(events.NewMessage(incoming=True, pattern=r"^/mode$"))
async def handle_mode_command(e):
    if e.sender_id not in Var.ADMINS:
        return
    current_mode = CACHE.get(FORWARD_MODE_KEY, "bot")
    await e.reply(_mode_text(current_mode), buttons=_mode_buttons(current_mode))


@bot.on(events.callbackquery.CallbackQuery(data=re.compile("fwd_mode")))
async def handle_mode_callback(e):
    if e.sender_id not in Var.ADMINS:
        return await e.answer("Admins only.", alert=True)
    current_mode = CACHE.get(FORWARD_MODE_KEY, "bot")
    await e.edit(_mode_text(current_mode), buttons=_mode_buttons(current_mode))


@bot.on(events.callbackquery.CallbackQuery(data=re.compile(r"set_mode_(bot|userbot)")))
async def handle_set_mode(e):
    if e.sender_id not in Var.ADMINS:
        return await e.answer("Admins only.", alert=True)

    requested_mode = e.pattern_match.group(1).decode("utf-8")

    if requested_mode == "userbot" and not userbot:
        return await e.answer(
            "Userbot unavailable. Set SESSION_STRING in .env and restart.",
            alert=True,
        )

    await set_forward_mode(requested_mode)
    CACHE[FORWARD_MODE_KEY] = requested_mode

    await e.edit(_mode_text(requested_mode), buttons=_mode_buttons(requested_mode))
    await e.answer(f"Switched to {requested_mode} mode.")


# ──────────────────────────────────────────────
#  Status & Stats
# ──────────────────────────────────────────────

@bot.on(events.NewMessage(incoming=True, pattern=r"^/status$"))
async def handle_status(e):
    if e.sender_id not in Var.ADMINS:
        return
    work_names = await get_all_work_names()
    total = len(work_names)
    active = sum(1 for name in work_names if CACHE.get(name, {}).get("has_to_forward"))
    stopped = total - active
    current_mode = CACHE.get(FORWARD_MODE_KEY, "bot")
    ub_status = "Connected" if userbot else "Not configured"

    txt = (
        "📊 **System Status**\n\n"
        f"**Total Tasks** : {total}\n"
        f"**Active** : {active}\n"
        f"**Stopped** : {stopped}\n"
        f"**Forward Mode** : {current_mode.capitalize()}\n"
        f"**Userbot** : {ub_status}\n"
        f"**Bot** : Online"
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
            f"    Sources: {sources} │ Targets: {targets} │ Forwarded: {forwarded}"
        )

    txt = "📈 **Forwarding Statistics**\n\n" + "\n\n".join(lines)
    await e.reply(txt)
