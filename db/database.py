from __future__ import annotations

import aiosqlite
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amount      REAL    NOT NULL,
    currency    TEXT    NOT NULL DEFAULT 'INR',
    category    TEXT    NOT NULL,
    subcategory TEXT,
    description TEXT,
    source      TEXT    NOT NULL DEFAULT 'manual',  -- manual | sms | recurring
    original_sms TEXT,
    person      TEXT,   -- for lending / splits
    date        TEXT    NOT NULL,  -- YYYY-MM-DD
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS income (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amount      REAL    NOT NULL,
    source      TEXT    NOT NULL,
    description TEXT,
    person      TEXT,   -- for paybacks
    date        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS food_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_type           TEXT    NOT NULL,  -- breakfast | lunch | dinner | snack
    description         TEXT    NOT NULL,
    items_json          TEXT,              -- JSON array of items
    estimated_calories  REAL,
    estimated_protein   REAL,
    estimated_carbs     REAL,
    estimated_fat       REAL,
    date                TEXT    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS fitbit_data (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT    NOT NULL UNIQUE,
    sleep_score         INTEGER,
    sleep_hours         REAL,
    deep_sleep_mins     INTEGER,
    rem_sleep_mins      INTEGER,
    steps               INTEGER,
    resting_hr          INTEGER,
    hrv                 REAL,
    spo2                REAL,
    active_zone_mins    INTEGER,
    calories_burned     INTEGER,
    skin_temp_variation REAL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS budgets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category      TEXT    NOT NULL,  -- 'total' or a specific category
    monthly_limit REAL    NOT NULL,
    month_year    TEXT    NOT NULL,  -- YYYY-MM
    UNIQUE(category, month_year)
);

CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    parent_category TEXT,
    is_custom       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recurring_expenses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    description     TEXT    NOT NULL,
    amount          REAL    NOT NULL,
    category        TEXT    NOT NULL,
    day_of_month    INTEGER,
    last_confirmed  TEXT,   -- YYYY-MM-DD
    active          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tracking_days (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    date               TEXT    NOT NULL UNIQUE,
    has_expenses       INTEGER NOT NULL DEFAULT 0,
    confirmed_zero_day INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fitbit_tokens (
    id            INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton
    access_token  TEXT    NOT NULL,
    refresh_token TEXT    NOT NULL,
    expires_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- Default categories
INSERT OR IGNORE INTO categories (name, parent_category, is_custom) VALUES
    ('Food & Groceries', NULL, 0),
    ('Food Delivery', 'Food & Groceries', 0),
    ('Groceries', 'Food & Groceries', 0),
    ('Dining Out', 'Food & Groceries', 0),
    ('Transport', NULL, 0),
    ('Fuel', 'Transport', 0),
    ('Cab/Auto', 'Transport', 0),
    ('Public Transport', 'Transport', 0),
    ('Housing', NULL, 0),
    ('Rent', 'Housing', 0),
    ('Utilities', 'Housing', 0),
    ('Maintenance', 'Housing', 0),
    ('Shopping', NULL, 0),
    ('Electronics', 'Shopping', 0),
    ('Clothing', 'Shopping', 0),
    ('Subscriptions', NULL, 0),
    ('Entertainment', NULL, 0),
    ('Health', NULL, 0),
    ('Education', NULL, 0),
    ('Lending', NULL, 0),
    ('Personal Care', NULL, 0),
    ('Miscellaneous', NULL, 0);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)

        # Track schema version
        cur = await self._db.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cur.fetchone()
        if row is None:
            await self._db.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db
