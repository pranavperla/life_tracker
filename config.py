from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_USER_ID: int = int(os.environ["TELEGRAM_USER_ID"])

    # Gemini
    GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Fitbit
    FITBIT_CLIENT_ID: str = os.getenv("FITBIT_CLIENT_ID", "")
    FITBIT_CLIENT_SECRET: str = os.getenv("FITBIT_CLIENT_SECRET", "")
    FITBIT_REDIRECT_URI: str = os.getenv(
        "FITBIT_REDIRECT_URI", "http://localhost:8080/fitbit/callback"
    )

    # Gmail
    GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
    NOTIFICATION_EMAIL: str = os.getenv("NOTIFICATION_EMAIL", "")

    # Defaults
    DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "INR")
    DEFAULT_MONTHLY_BUDGET: int = int(os.getenv("DEFAULT_MONTHLY_BUDGET", "50000"))

    # Schedule
    DAILY_SUMMARY_HOUR: int = int(os.getenv("DAILY_SUMMARY_HOUR", "21"))
    EVENING_NUDGE_HOUR: int = int(os.getenv("EVENING_NUDGE_HOUR", "20"))
    WEEKLY_SUMMARY_DAY: str = os.getenv("WEEKLY_SUMMARY_DAY", "mon")
    WEEKLY_SUMMARY_HOUR: int = int(os.getenv("WEEKLY_SUMMARY_HOUR", "9"))
    FITBIT_SYNC_INTERVAL_HOURS: int = int(
        os.getenv("FITBIT_SYNC_INTERVAL_HOURS", "4")
    )

    # Database
    DB_PATH: Path = BASE_DIR / os.getenv("DB_PATH", "data/life_tracker.db")
    BACKUP_DIR: Path = BASE_DIR / os.getenv("BACKUP_DIR", "backups")
    BACKUP_RETENTION_DAYS: int = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

    # Exports
    EXPORT_DIR: Path = BASE_DIR / "exports"
