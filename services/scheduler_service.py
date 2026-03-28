"""APScheduler setup for all scheduled jobs."""

from __future__ import annotations

import logging

from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import Config
from db.database import Database
from db.backup import backup_database
from db import models
from bot.keyboards import zero_day_keyboard, recurring_confirm_keyboard

logger = logging.getLogger(__name__)


def create_scheduler(app: Application, db: Database) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    chat_id = Config.TELEGRAM_USER_ID

    # --- Evening nudge (8 PM) ---
    async def evening_nudge():
        try:
            has = await models.has_expenses_today(db)
            if not has:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text="💭 No expenses logged today. Zero-spend day?",
                    reply_markup=zero_day_keyboard(),
                )
        except Exception:
            logger.exception("Evening nudge failed")

    scheduler.add_job(
        evening_nudge, "cron",
        hour=Config.EVENING_NUDGE_HOUR, minute=0,
        id="evening_nudge",
    )

    # --- Daily summary (9 PM) ---
    async def daily_summary():
        try:
            from services.insights_service import generate_daily_report
            from services.email_service import send_daily_summary

            report = await generate_daily_report(db)

            # Send via Telegram
            await app.bot.send_message(chat_id=chat_id, text=report)

            # Send via email
            await send_daily_summary(report)

        except Exception:
            logger.exception("Daily summary failed")

    scheduler.add_job(
        daily_summary, "cron",
        hour=Config.DAILY_SUMMARY_HOUR, minute=0,
        id="daily_summary",
    )

    # --- Weekly summary (Monday 9 AM) ---
    async def weekly_summary():
        try:
            from services.insights_service import generate_weekly_report
            from services.excel_service import generate_report
            from services.email_service import send_weekly_summary

            report = await generate_weekly_report(db)
            excel_path = await generate_report(db)

            # Telegram: send text + file
            await app.bot.send_message(chat_id=chat_id, text=report)
            with open(excel_path, "rb") as f:
                await app.bot.send_document(
                    chat_id=chat_id, document=f,
                    filename=excel_path.name,
                    caption="📊 Weekly Excel report attached"
                )

            # Email with attachment
            await send_weekly_summary(report, excel_path)

        except Exception:
            logger.exception("Weekly summary failed")

    scheduler.add_job(
        weekly_summary, "cron",
        day_of_week=Config.WEEKLY_SUMMARY_DAY,
        hour=Config.WEEKLY_SUMMARY_HOUR, minute=0,
        id="weekly_summary",
    )

    # --- Fitbit sync (every N hours) ---
    async def fitbit_sync():
        try:
            from services.fitbit_service import sync_recent
            count = await sync_recent(db, days=2)
            logger.info("Fitbit sync complete: %d days synced", count)
        except Exception:
            logger.exception("Fitbit sync failed")

    scheduler.add_job(
        fitbit_sync, "interval",
        hours=Config.FITBIT_SYNC_INTERVAL_HOURS,
        id="fitbit_sync",
    )

    # --- Database backup (daily at 3 AM) ---
    async def db_backup():
        try:
            path = await backup_database(
                Config.DB_PATH, Config.BACKUP_DIR, Config.BACKUP_RETENTION_DAYS
            )
            if path:
                logger.info("DB backup completed: %s", path)
        except Exception:
            logger.exception("DB backup failed")

    scheduler.add_job(
        db_backup, "cron",
        hour=3, minute=0,
        id="db_backup",
    )

    # --- Recurring expense reminders (daily at 10 AM) ---
    async def check_recurring():
        try:
            today = date.today()
            recurring = await models.get_active_recurring(db)
            for r in recurring:
                day = r.get("day_of_month")
                if day and abs(today.day - day) <= 2:
                    last = r.get("last_confirmed")
                    if last and last.startswith(today.strftime("%Y-%m")):
                        continue  # Already confirmed this month
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"🔄 Recurring expense: ₹{r['amount']:,.0f} — {r['description']}\nDue around day {day} of the month.",
                        reply_markup=recurring_confirm_keyboard(r["id"]),
                    )
        except Exception:
            logger.exception("Recurring check failed")

    scheduler.add_job(
        check_recurring, "cron",
        hour=10, minute=0,
        id="recurring_check",
    )

    return scheduler
