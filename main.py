"""Entry point: starts the Telegram bot and all scheduled jobs."""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram.ext import ApplicationBuilder

from config import Config
from db.database import Database
from bot.handlers import register_handlers
from services.scheduler_service import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Config.BASE_DIR / "life_tracker.log"),
    ],
)
# Avoid httpx/httpcore INFO logs — they include the full Telegram API URL with the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(app):
    """Run after the bot application is initialized."""
    commands = [
        ("start", "Welcome message"),
        ("help", "List all commands"),
        ("summary", "Today's overview"),
        ("week", "This week's summary"),
        ("month", "Monthly breakdown"),
        ("export", "Get Excel report"),
        ("budget", "View/set budgets"),
        ("income", "View income & savings"),
        ("trends", "Spending trends"),
        ("insights", "Cross-domain insights"),
        ("undo", "Remove last entry"),
        ("recurring", "Recurring expenses"),
        ("fitbit", "Fitbit sync status"),
        ("fitbit_login", "Get Fitbit OAuth link"),
        ("fitbit_auth", "Complete Fitbit OAuth with code"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


async def run() -> None:
    # Connect database
    db = Database(Config.DB_PATH)
    await db.connect()
    logger.info("Database connected at %s", Config.DB_PATH)

    # Build Telegram app
    app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    register_handlers(app, db)

    # Start scheduler
    scheduler = create_scheduler(app, db)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # Run the bot
    logger.info("Starting bot... (polling)")
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Keep running until interrupted
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await db.close()
        logger.info("Shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")


if __name__ == "__main__":
    main()
