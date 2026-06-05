"""JARVIS Telegram Interface v2

Commands:
  /start       - Welcome
  /log         - Last 10 tasks
  /plan <goal> - Create long-horizon plan
  /today       - Today's scheduled tasks
  /debate <q>  - Multi-model debate
  /stats       - Routing intelligence stats
  /world       - Check monitored sites now
  /memory <q>  - Search episodic memory
  /voice       - Trigger voice assistant
  /evolve      - List evolved tools
  /rate        - Rate last task
  /queue       - View or add to queue
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from typing import Any, Final

from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    filters, ContextTypes, CallbackQueryHandler
)

from jarvis.config import TELEGRAM_TOKEN, ALLOWED_USER_IDS, LOG_FILE, FCC_BASE_URL, FCC_AUTH_TOKEN
from jarvis.agent import run_agent

_log = logging.getLogger(__name__)

# ── Bot singleton ────────────────────────────────────────
_bot_app: Any = None


def _get_bot_app() -> Any:
    global _bot_app
    if _bot_app is None and TELEGRAM_TOKEN:
        _bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    return _bot_app


# ═══════════════════════════════════════════════════════════
#  Auth
# ═══════════════════════════════════════════════════════════
def allowed(update: Update) -> bool:
    """Return True if the user is in ALLOWED_USER_IDS."""
    return update.effective_user is not None and update.effective_user.id in ALLOWED_USER_IDS


# ═══════════════════════════════════════════════════════════
#  Live status updater
# ═══════════════════════════════════════════════════════════
class StatusUpdater:
    def __init__(self, message: Any) -> None:
        self.message = message
        self.lines: list[str] = []

    async def update(self, line: str) -> None:
        self.lines.append(line)
        preview = "\n".join(self.lines[-6:])
        try:
            await self.message.edit_text(
                f"⚙️ *Working…*\n\n{preview}",
                parse_mode="Markdown",
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  Queue notifier (breaks circular dep with queue_manager)
# ═══════════════════════════════════════════════════════════
def _queue_notify(user_id: str, task_text: str, result: str) -> None:
    """Called by queue_manager when a queued task finishes.

    We use a helper here so queue_manager never imports telegram_bot.
    """
    app = _get_bot_app()
    if app is None:
        _log.warning("Queue notify: bot app not available")
        return
    asyncio.create_task(
        app.bot.send_message(
            chat_id=int(user_id),
            text=(
                f"✅ **Queue Task Complete**\n\n"
                f"**Task:** {task_text}\n\n"
                f"**Result:**\n{result[:2000]}"
            ),
            parse_mode="Markdown",
        )
    )


# ═══════════════════════════════════════════════════════════
#  Commands
# ═════════════════════════════════════════════════════════==
async def cmd_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/rate good` or `/rate bad`", parse_mode="Markdown"
        )
        return

    rating = context.args[0].lower()
    from jarvis.agent import rate_last_task
    result = rate_last_task(rating)
    await update.message.reply_text(result)


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View queue or add a new task."""
    if not allowed(update):
        return

    task = " ".join(context.args).strip() if context.args else ""
    if not task:
        from jarvis.queue_manager import list_queue
        pending = list_queue()
        if not pending:
            await update.message.reply_text("The queue is empty.")
        else:
            msg = "📋 **Pending Tasks:**\n" + "\n".join(
                f"• {t['task']}" for t in pending
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        return

    from jarvis.queue_manager import add_to_queue
    task_id = add_to_queue(task, str(update.effective_chat.id))
    await update.message.reply_text(
        f"📥 Task added to queue (ID: `{task_id}`). I'll notify you when it's done.",
        parse_mode="Markdown",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    task = update.message.text.strip()
    session_id = f"telegram_{update.effective_chat.id}"
    status_msg = await update.message.reply_text(
        "⚙️ *Working…*", parse_mode="Markdown"
    )
    updater = StatusUpdater(status_msg)
    loop = asyncio.get_event_loop()

    result = await loop.run_in_executor(
        None,
        lambda: run_agent(
            task,
            status_callback=lambda m: asyncio.run_coroutine_threadsafe(
                updater.update(m), loop
            ).result(),
            session_id=session_id,
        ),
    )

    # Check for screenshot path in result
    img_match = re.search(r"(/home/\w+/Pictures/Jarvis/\S+\.png)", result)
    if img_match and os.path.exists(img_match.group(1)):
        with open(img_match.group(1), "rb") as fh:
            await update.message.reply_photo(photo=fh, caption=result[:1024])
        await status_msg.delete()
        return

    if len(result) <= 4000:
        await status_msg.edit_text(result, parse_mode=constants.ParseMode.MARKDOWN)
    else:
        await status_msg.edit_text("📄 *Result (split):*", parse_mode="Markdown")
        for chunk in [result[i : i + 4000] for i in range(0, len(result), 4000)]:
            await update.message.reply_text(chunk)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    status_msg = await update.message.reply_text(
        "🎙️ *Transcribing…*", parse_mode="Markdown"
    )
    voice = update.message.voice or update.message.audio
    if not voice:
        await status_msg.edit_text("❌ No voice detected.")
        return

    file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    transcript = ""
    try:
        import requests
        with open(tmp_path, "rb") as fh:
            r = requests.post(
                f"{FCC_BASE_URL}/v1/audio/transcriptions",
                files={"file": ("audio.ogg", fh, "audio/ogg")},
                data={"model": "openai/whisper-large-v3", "language": "en"},
                headers={"Authorization": f"Bearer {FCC_AUTH_TOKEN}"},
                timeout=30,
            )
            transcript = r.json().get("text", "").strip()
    except Exception as exc:
        await status_msg.edit_text(f"❌ Transcription failed: {exc}")
        return
    finally:
        os.unlink(tmp_path)

    if not transcript:
        await status_msg.edit_text("❌ Could not transcribe. Send text instead.")
        return

    await status_msg.edit_text(f"📝 *Heard:* {transcript}", parse_mode="Markdown")
    fake = update
    fake.message.text = transcript
    await handle_text(fake, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kb = [
        [InlineKeyboardButton("📋 Task Log", callback_data="log"),
         InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("☀️ Today", callback_data="today"),
         InlineKeyboardButton("🌐 World", callback_data="world")],
    ]
    await update.message.reply_text(
        "🤖 *JARVIS v2.0 — Online*\n\n"
        "Send any task as text or voice.\n\n"
        "*Commands:*\n"
        "`/plan <goal>` — Create study/work plan\n"
        "`/debate <q>` — 3-model debate\n"
        "`/today` — Today's tasks\n"
        "`/stats` — Model routing stats\n"
        "`/log` — Recent tasks\n"
        "`/memory <q>` — Search past episodes\n"
        "`/evolve` — List self-evolved tools\n"
        "`/rate good|bad` — Rate last task\n"
        "`/queue` — Task queue\n",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    args = " ".join(context.args).strip() if context.args else ""
    if not args:
        await update.message.reply_text(
            "Usage: `/plan <goal> [by YYYY-MM-DD]`", parse_mode="Markdown"
        )
        return

    deadline_match = re.search(r"by (\d{4}-\d{2}-\d{2})", args)
    deadline = deadline_match.group(1) if deadline_match else None
    goal = re.sub(r"by \d{4}-\d{2}-\d{2}", "", args).strip()

    msg = await update.message.reply_text("📅 *Creating your plan…*", parse_mode="Markdown")
    try:
        from jarvis.planner import create_plan
        loop = asyncio.get_event_loop()
        plan = await loop.run_in_executor(None, lambda: create_plan(goal, deadline))
        if "error" in plan:
            await msg.edit_text(f"❌ {plan['error']}")
            return
        milestones = plan.get("milestones", [])
        summary = f"📅 *Plan: {goal}*\nDeadline: {plan.get('deadline')}\n\n"
        for m in milestones[:3]:
            summary += f"*Week {m['week']}:* {m['focus']}\n"
        summary += f"\n_{len(milestones)} weeks total. Use /today for daily tasks._"
        await msg.edit_text(summary, parse_mode="Markdown")
    except Exception as exc:
        await msg.edit_text(f"❌ {exc}")


async def cmd_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("Usage: `/debate <question>`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text(
        "⚖️ *Initiating 3-model debate…*", parse_mode="Markdown"
    )
    try:
        from jarvis.debate import run_debate
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: run_debate(question))
        if len(result) <= 4000:
            await msg.edit_text(result, parse_mode=constants.ParseMode.MARKDOWN)
        else:
            await msg.edit_text("📄 *Debate complete (split):*", parse_mode="Markdown")
            for chunk in [result[i : i + 4000] for i in range(0, len(result), 4000)]:
                await update.message.reply_text(chunk)
    except Exception as exc:
        await msg.edit_text(f"❌ Debate error: {exc}")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    try:
        from jarvis.planner import get_todays_tasks
        tasks = get_todays_tasks()
        if not tasks:
            await update.message.reply_text(
                "📭 No tasks for today. Create a plan with `/plan`.", parse_mode="Markdown"
            )
        else:
            msg = "☀️ *Today's Tasks*\n\n" + "\n".join(f"• {t}" for t in tasks)
            await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    from jarvis.orchestrator import get_routing_report
    await update.message.reply_text(get_routing_report(), parse_mode="Markdown")


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    try:
        with open(LOG_FILE, encoding="utf-8") as fh:
            lines = fh.readlines()[-10:]
        entries = [json.loads(l) for l in lines]
        msg = "\n\n".join(
            f"• `{e['ts'][:16]}` {e['task'][:50]}\n"
            f"  ✅ {e['model'].split('/')[-1]} • {e['duration_s']}s"
            for e in reversed(entries)
        )
        await update.message.reply_text(f"📋 *Last Tasks*\n\n{msg}", parse_mode="Markdown")
    except FileNotFoundError:
        await update.message.reply_text("No tasks logged yet.")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text("Usage: `/memory <query>`", parse_mode="Markdown")
        return
    from jarvis.episodic_memory import retrieve_past_task
    result = retrieve_past_task(query)
    await update.message.reply_text(f"💾 *Memory Search*\n\n{result}", parse_mode="Markdown")


async def cmd_world(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    msg = await update.message.reply_text(
        "🌐 *Checking monitored sites…*", parse_mode="Markdown"
    )
    loop = asyncio.get_event_loop()
    try:
        changes = await loop.run_in_executor(None, __import__("world_model")._monitor_cycle)
        if changes:
            text = "\n\n".join(f"📍 {url}\n{summary}" for url, summary in changes)
            await msg.edit_text(f"🌐 *Updates Found*\n\n{text}", parse_mode="Markdown")
        else:
            await msg.edit_text("🌐 No changes detected on monitored sites.")
    except Exception as exc:
        await msg.edit_text(f"❌ {exc}")


async def cmd_evolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    from jarvis.config import BASE_DIR
    evolved_dir = BASE_DIR / "evolved_tools"
    tools = [f.stem for f in evolved_dir.glob("*.py") if not f.stem.startswith("test_")]
    if tools:
        await update.message.reply_text(
            f"🧬 *Evolved Tools ({len(tools)})*\n\n" + "\n".join(f"• `{t}`" for t in tools),
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("🧬 No self-evolved tools yet.")


async def btn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    fakes = {"log": cmd_log, "stats": cmd_stats, "today": cmd_today, "world": cmd_world}
    handler = fakes.get(query.data)
    if handler:
        update._effective_message = query.message
        await handler(update, context)


# ═════════════════════════════════════════════════════════==
#  Main
# ═════════════════════════════════════════════════════════==
def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN not set in ~/.jarvis/.env")

    app = _get_bot_app()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("debate", cmd_debate))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("log", cmd_log))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("world", cmd_world))
    app.add_handler(CommandHandler("evolve", cmd_evolve))
    app.add_handler(CommandHandler("rate", cmd_rate))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CallbackQueryHandler(btn_callback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start background world model
    import jarvis.world_model as world_model
    world_model.start_background()

    _log.info("JARVIS Telegram v2 online.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()


__all__ = ["main", "_get_bot_app", "allowed", "cmd_queue"]
