"""Automatic SQLite database backup with rotation."""

from __future__ import annotations

import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


async def backup_database(db_path: Path, backup_dir: Path, retention_days: int = 30) -> Path | None:
    if not db_path.exists():
        logger.warning("Database file not found, skipping backup")
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"life_tracker_backup_{timestamp}.db"

    try:
        shutil.copy2(str(db_path), str(dest))
        logger.info("Database backed up to %s", dest)
    except Exception:
        logger.exception("Database backup failed")
        return None

    # Rotate old backups
    cutoff = datetime.now() - timedelta(days=retention_days)
    for f in sorted(backup_dir.glob("life_tracker_backup_*.db")):
        try:
            ts_str = f.stem.replace("life_tracker_backup_", "")
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if ts < cutoff:
                f.unlink()
                logger.info("Removed old backup: %s", f.name)
        except (ValueError, OSError):
            continue

    return dest
