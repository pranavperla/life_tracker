"""CRUD operations for all tables."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from db.database import Database


def _today() -> str:
    return date.today().isoformat()


def _row_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    return dict(row)


def _rows_to_list(rows: list) -> list[dict]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

async def add_expense(
    db: Database,
    *,
    amount: float,
    category: str,
    description: str,
    subcategory: str | None = None,
    source: str = "manual",
    original_sms: str | None = None,
    person: str | None = None,
    currency: str = "INR",
    expense_date: str | None = None,
) -> dict:
    d = expense_date or _today()
    cur = await db.db.execute(
        """INSERT INTO expenses
           (amount, currency, category, subcategory, description, source, original_sms, person, date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (amount, currency, category, subcategory, description, source, original_sms, person, d),
    )
    await db.db.commit()
    # Mark tracking day
    await _mark_tracking_day(db, d, has_expenses=True)
    return {"id": cur.lastrowid, "amount": amount, "category": category,
            "description": description, "date": d}


async def get_expenses_for_date(db: Database, d: str) -> list[dict]:
    cur = await db.db.execute("SELECT * FROM expenses WHERE date = ? ORDER BY created_at", (d,))
    return _rows_to_list(await cur.fetchall())


async def get_expenses_range(db: Database, start: str, end: str) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM expenses WHERE date BETWEEN ? AND ? ORDER BY date, created_at",
        (start, end),
    )
    return _rows_to_list(await cur.fetchall())


async def get_expenses_by_category(db: Database, start: str, end: str) -> list[dict]:
    cur = await db.db.execute(
        """SELECT category, SUM(amount) as total, COUNT(*) as count
           FROM expenses WHERE date BETWEEN ? AND ?
           GROUP BY category ORDER BY total DESC""",
        (start, end),
    )
    return _rows_to_list(await cur.fetchall())


async def get_last_expense(db: Database) -> dict:
    cur = await db.db.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1")
    return _row_to_dict(await cur.fetchone())


async def update_expense(db: Database, expense_id: int, **fields: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [expense_id]
    await db.db.execute(f"UPDATE expenses SET {sets} WHERE id = ?", vals)
    await db.db.commit()


async def delete_expense(db: Database, expense_id: int) -> None:
    await db.db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    await db.db.commit()


async def get_total_expenses(db: Database, start: str, end: str) -> float:
    cur = await db.db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date BETWEEN ? AND ?",
        (start, end),
    )
    row = await cur.fetchone()
    return float(row["total"])


# ---------------------------------------------------------------------------
# Income
# ---------------------------------------------------------------------------

async def add_income(
    db: Database,
    *,
    amount: float,
    source: str,
    description: str | None = None,
    person: str | None = None,
    income_date: str | None = None,
) -> dict:
    d = income_date or _today()
    cur = await db.db.execute(
        "INSERT INTO income (amount, source, description, person, date) VALUES (?, ?, ?, ?, ?)",
        (amount, source, description, person, d),
    )
    await db.db.commit()
    return {"id": cur.lastrowid, "amount": amount, "source": source, "date": d}


async def get_total_income(db: Database, start: str, end: str) -> float:
    cur = await db.db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE date BETWEEN ? AND ?",
        (start, end),
    )
    row = await cur.fetchone()
    return float(row["total"])


async def get_income_range(db: Database, start: str, end: str) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM income WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    )
    return _rows_to_list(await cur.fetchall())


# ---------------------------------------------------------------------------
# Food log
# ---------------------------------------------------------------------------

async def add_food(
    db: Database,
    *,
    meal_type: str,
    description: str,
    items: list[str] | None = None,
    calories: float | None = None,
    protein: float | None = None,
    carbs: float | None = None,
    fat: float | None = None,
    food_date: str | None = None,
) -> dict:
    d = food_date or _today()
    items_json = json.dumps(items) if items else None
    cur = await db.db.execute(
        """INSERT INTO food_log
           (meal_type, description, items_json, estimated_calories, estimated_protein,
            estimated_carbs, estimated_fat, date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (meal_type, description, items_json, calories, protein, carbs, fat, d),
    )
    await db.db.commit()
    return {"id": cur.lastrowid, "meal_type": meal_type, "description": description, "date": d}


async def get_food_for_date(db: Database, d: str) -> list[dict]:
    cur = await db.db.execute("SELECT * FROM food_log WHERE date = ? ORDER BY created_at", (d,))
    return _rows_to_list(await cur.fetchall())


async def get_food_range(db: Database, start: str, end: str) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM food_log WHERE date BETWEEN ? AND ? ORDER BY date, created_at",
        (start, end),
    )
    return _rows_to_list(await cur.fetchall())


# ---------------------------------------------------------------------------
# Fitbit data
# ---------------------------------------------------------------------------

async def upsert_fitbit_data(db: Database, data: dict) -> None:
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    updates = ", ".join(f"{k} = excluded.{k}" for k in data if k != "date")
    await db.db.execute(
        f"""INSERT INTO fitbit_data ({cols}) VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {updates}""",
        tuple(data.values()),
    )
    await db.db.commit()


async def get_fitbit_for_date(db: Database, d: str) -> dict:
    cur = await db.db.execute("SELECT * FROM fitbit_data WHERE date = ?", (d,))
    return _row_to_dict(await cur.fetchone())


async def get_fitbit_range(db: Database, start: str, end: str) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM fitbit_data WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    )
    return _rows_to_list(await cur.fetchall())


async def get_latest_fitbit(db: Database) -> dict:
    cur = await db.db.execute("SELECT * FROM fitbit_data ORDER BY date DESC LIMIT 1")
    return _row_to_dict(await cur.fetchone())


# ---------------------------------------------------------------------------
# Fitbit tokens
# ---------------------------------------------------------------------------

async def save_fitbit_tokens(db: Database, access: str, refresh: str, expires_at: float) -> None:
    await db.db.execute(
        """INSERT INTO fitbit_tokens (id, access_token, refresh_token, expires_at)
           VALUES (1, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             access_token = excluded.access_token,
             refresh_token = excluded.refresh_token,
             expires_at = excluded.expires_at""",
        (access, refresh, expires_at),
    )
    await db.db.commit()


async def get_fitbit_tokens(db: Database) -> dict:
    cur = await db.db.execute("SELECT * FROM fitbit_tokens WHERE id = 1")
    return _row_to_dict(await cur.fetchone())


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

async def set_budget(db: Database, category: str, limit: float, month_year: str) -> None:
    await db.db.execute(
        """INSERT INTO budgets (category, monthly_limit, month_year)
           VALUES (?, ?, ?)
           ON CONFLICT(category, month_year) DO UPDATE SET monthly_limit = excluded.monthly_limit""",
        (category, limit, month_year),
    )
    await db.db.commit()


async def get_budget(db: Database, category: str, month_year: str) -> dict:
    cur = await db.db.execute(
        "SELECT * FROM budgets WHERE category = ? AND month_year = ?",
        (category, month_year),
    )
    return _row_to_dict(await cur.fetchone())


async def get_all_budgets(db: Database, month_year: str) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM budgets WHERE month_year = ?", (month_year,)
    )
    return _rows_to_list(await cur.fetchall())


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

async def get_categories(db: Database) -> list[dict]:
    cur = await db.db.execute("SELECT * FROM categories ORDER BY name")
    return _rows_to_list(await cur.fetchall())


async def add_category(db: Database, name: str, parent: str | None = None) -> None:
    await db.db.execute(
        "INSERT OR IGNORE INTO categories (name, parent_category, is_custom) VALUES (?, ?, 1)",
        (name, parent),
    )
    await db.db.commit()


# ---------------------------------------------------------------------------
# Recurring expenses
# ---------------------------------------------------------------------------

async def add_recurring(
    db: Database, description: str, amount: float, category: str, day_of_month: int | None = None
) -> dict:
    cur = await db.db.execute(
        "INSERT INTO recurring_expenses (description, amount, category, day_of_month) VALUES (?, ?, ?, ?)",
        (description, amount, category, day_of_month),
    )
    await db.db.commit()
    return {"id": cur.lastrowid, "description": description, "amount": amount}


async def get_active_recurring(db: Database) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM recurring_expenses WHERE active = 1 ORDER BY day_of_month"
    )
    return _rows_to_list(await cur.fetchall())


async def confirm_recurring(db: Database, rec_id: int, d: str) -> None:
    await db.db.execute(
        "UPDATE recurring_expenses SET last_confirmed = ? WHERE id = ?", (d, rec_id)
    )
    await db.db.commit()


async def deactivate_recurring(db: Database, rec_id: int) -> None:
    await db.db.execute(
        "UPDATE recurring_expenses SET active = 0 WHERE id = ?", (rec_id,)
    )
    await db.db.commit()


# ---------------------------------------------------------------------------
# Tracking days
# ---------------------------------------------------------------------------

async def _mark_tracking_day(db: Database, d: str, has_expenses: bool = False) -> None:
    if has_expenses:
        await db.db.execute(
            """INSERT INTO tracking_days (date, has_expenses)
               VALUES (?, 1)
               ON CONFLICT(date) DO UPDATE SET has_expenses = 1""",
            (d,),
        )
    await db.db.commit()


async def confirm_zero_day(db: Database, d: str) -> None:
    await db.db.execute(
        """INSERT INTO tracking_days (date, confirmed_zero_day)
           VALUES (?, 1)
           ON CONFLICT(date) DO UPDATE SET confirmed_zero_day = 1""",
        (d,),
    )
    await db.db.commit()


async def get_tracked_days(db: Database, start: str, end: str) -> list[dict]:
    cur = await db.db.execute(
        "SELECT * FROM tracking_days WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    )
    return _rows_to_list(await cur.fetchall())


async def has_expenses_today(db: Database) -> bool:
    d = _today()
    cur = await db.db.execute(
        "SELECT has_expenses FROM tracking_days WHERE date = ?", (d,)
    )
    row = await cur.fetchone()
    return bool(row and row["has_expenses"])


# ---------------------------------------------------------------------------
# Generic query (for text-to-SQL engine)
# ---------------------------------------------------------------------------

async def run_readonly_query(db: Database, sql: str) -> list[dict]:
    """Execute a read-only SQL query. Rejects anything that isn't SELECT."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")
    for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH"):
        if forbidden in stripped.split("SELECT", 1)[-1].split("FROM")[0:1]:
            continue
        # Check in the full query after SELECT
        rest = stripped.split("SELECT", 1)[-1]
        if f" {forbidden} " in f" {rest} ":
            raise ValueError(f"Forbidden keyword: {forbidden}")
    cur = await db.db.execute(sql)
    rows = await cur.fetchall()
    return _rows_to_list(rows)
