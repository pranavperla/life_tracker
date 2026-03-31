"""Natural-language to SQL query engine."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from db.database import Database
from db.models import run_readonly_query
from services.llm_service import generate_sql, format_query_answer

logger = logging.getLogger(__name__)

# Rupee food-related spending (not food_log meals, not a literal category named 'Food')
_FOOD_EXPENSE_CATEGORIES_SQL = (
    "'Food Delivery', 'Groceries', 'Dining Out', 'Food & Groceries'"
)


def _is_food_money_question(q: str) -> bool:
    """User is asking about money on food, not meal calories or food_log."""
    if not re.search(
        r"\bfood\b|grocer|grocery|zomato|swiggy|dining|delivery|restaurant|uber\s*eats",
        q,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"\b(spend|spent|spending|cost|pay|paid|money|how much|rupee|rs\.?|₹)",
            q,
            re.I,
        )
    )


def _rows_effectively_empty(rows: list[dict]) -> bool:
    if not rows:
        return True
    for r in rows:
        for v in r.values():
            if v is None:
                continue
            if isinstance(v, (int, float)) and v != 0:
                return False
            if isinstance(v, str) and v.strip() not in ("", "0", "0.0"):
                return False
    return True


def _fallback_food_expenses_sql(question: str, today: str) -> str:
    """Deterministic SUM for food categories when the model targeted food_log or category='Food'."""
    d = date.fromisoformat(today)
    if re.search(r"\bweek\b", question, re.I):
        start = (d - timedelta(days=d.weekday())).isoformat()
        return (
            "SELECT COALESCE(SUM(amount), 0) AS total_spent, COUNT(*) AS transaction_count "
            f"FROM expenses WHERE date >= '{start}' AND date <= '{today}' "
            f"AND category IN ({_FOOD_EXPENSE_CATEGORIES_SQL})"
        )
    ym = today[:7]
    return (
        "SELECT COALESCE(SUM(amount), 0) AS total_spent, COUNT(*) AS transaction_count "
        f"FROM expenses WHERE substr(date, 1, 7) = '{ym}' "
        f"AND category IN ({_FOOD_EXPENSE_CATEGORIES_SQL})"
    )


def _should_use_food_expense_fallback(sql: str, rows: list[dict]) -> bool:
    """LLM often queries food_log or category='Food' for money questions."""
    sql_l = sql.lower()
    if "food_log" in sql_l:
        return True
    if re.search(r"category\s*=\s*['\"]Food['\"]", sql):
        return True
    return _rows_effectively_empty(rows)


async def answer_question(db: Database, question: str) -> str:
    today = date.today().isoformat()

    result = await generate_sql(question, today)
    sql = result.get("sql", "").strip()
    explanation = result.get("explanation", "")

    if not sql:
        return "I couldn't understand that question. Could you rephrase it?"

    try:
        rows = await run_readonly_query(db, sql)
    except ValueError as exc:
        logger.warning("Blocked unsafe query: %s – %s", sql, exc)
        return "That query isn't allowed for safety reasons. Try rephrasing?"
    except Exception:
        logger.exception("Query execution failed: %s", sql)
        return "Something went wrong running that query. Try asking differently?"

    if _is_food_money_question(question) and _should_use_food_expense_fallback(
        sql, rows
    ):
        fb_sql = _fallback_food_expenses_sql(question, today)
        try:
            rows = await run_readonly_query(db, fb_sql)
            explanation = (
                "Food-related spending in expenses (Food Delivery, Groceries, "
                "Dining Out, Food & Groceries)."
            )
        except Exception:
            logger.exception("Food expense fallback failed: %s", fb_sql)

    return await format_query_answer(question, rows, explanation)
