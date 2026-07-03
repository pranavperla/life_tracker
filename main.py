"""Entry point: starts the Telegram bot and all scheduled jobs."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import sys

from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder

from config import Config
from db.database import Database
from bot.handlers import register_handlers
from services.scheduler_service import create_scheduler
from services.fixed_expenses_service import ensure_defaults

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

_LOCK_PATH = Config.BASE_DIR / "data" / ".life_tracker.lock"
_lock_fd: int | None = None
_STARTUP_RETRY_SECONDS = (15, 30, 60, 120, 300)


def _acquire_single_instance_lock() -> None:
    """Prevent two pollers (manual terminal + launchd) from causing Telegram 409 Conflict."""
    global _lock_fd
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _lock_fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error(
            "Another Life Tracker instance is already running (lock: %s). Exiting.",
            _LOCK_PATH,
        )
        sys.exit(0)


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
        ("fixed", "Fixed bills & flexible spending pool"),
        ("fitbit", "Fitbit sync status"),
        ("fitbit_login", "Get Fitbit OAuth link"),
        ("fitbit_auth", "Complete Fitbit OAuth with code"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


def build_app(db: Database):
    """Create a fresh Telegram application for each startup attempt."""
    app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).build()
    register_handlers(app, db)
    return app


async def stop_app(app, *, polling_started: bool, app_started: bool, initialized: bool) -> None:
    """Best-effort cleanup for partially started Telegram apps."""
    if polling_started and app.updater is not None:
        with contextlib.suppress(Exception):
            await app.updater.stop()
    if app_started:
        with contextlib.suppress(Exception):
            await app.stop()
    if initialized:
        with contextlib.suppress(Exception):
            await app.shutdown()


async def start_app_with_retries(db: Database):
    """Start Telegram polling, waiting out boot-time network delays."""
    attempt = 0
    while True:
        delay = _STARTUP_RETRY_SECONDS[min(attempt, len(_STARTUP_RETRY_SECONDS) - 1)]
        app = build_app(db)
        initialized = False
        app_started = False
        polling_started = False

        try:
            logger.info("Starting bot... (polling)")
            await app.initialize()
            initialized = True
            await post_init(app)
            await app.start()
            app_started = True
            await app.updater.start_polling(drop_pending_updates=True)
            polling_started = True
            return app
        except (NetworkError, TimedOut, OSError) as exc:
            attempt += 1
            logger.warning(
                "Telegram startup failed, likely because networking is not ready yet. "
                "Retrying in %d seconds. Error: %s",
                delay,
                exc,
                exc_info=True,
            )
            await stop_app(
                app,
                polling_started=polling_started,
                app_started=app_started,
                initialized=initialized,
            )
            await asyncio.sleep(delay)


async def run() -> None:
    # Connect database
    db = Database(Config.DB_PATH)
    await db.connect()
    logger.info("Database connected at %s", Config.DB_PATH)
    await ensure_defaults(db)

    app = None
    scheduler = None
    try:
        app = await start_app_with_retries(db)

        # Start scheduled jobs only after the bot is ready to send messages.
        scheduler = create_scheduler(app, db)
        scheduler.start()
        logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

        # Keep running until interrupted
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        logger.info("Shutting down...")
        if scheduler is not None:
            with contextlib.suppress(Exception):
                scheduler.shutdown(wait=False)
        if app is not None:
            await stop_app(app, polling_started=True, app_started=True, initialized=True)
        await db.close()
        logger.info("Shutdown complete")


def main() -> None:
    _acquire_single_instance_lock()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")


if __name__ == "__main__":
    main()
