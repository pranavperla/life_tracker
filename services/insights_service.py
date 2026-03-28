"""Cross-domain insight engine: trends, anomalies, and correlations."""

from __future__ import annotations

import json

import logging
from datetime import date, timedelta

from db.database import Database
from db import models
from services.llm_service import generate_daily_summary, generate_weekly_summary

logger = logging.getLogger(__name__)


def _month_range() -> tuple[str, str]:
    today = date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


def _week_range() -> tuple[str, str]:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    return start.isoformat(), today.isoformat()


def _prev_week_range() -> tuple[str, str]:
    today = date.today()
    end = today - timedelta(days=today.weekday()) - timedelta(days=1)
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _prev_month_range() -> tuple[str, str]:
    today = date.today()
    first_this_month = today.replace(day=1)
    last_prev = first_this_month - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev.isoformat(), last_prev.isoformat()


async def _gather_daily_data(db: Database) -> dict:
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    month_start, month_end = _month_range()

    expenses_today = await models.get_expenses_for_date(db, today)
    food_today = await models.get_food_for_date(db, today)
    fitbit_yesterday = await models.get_fitbit_for_date(db, yesterday)
    month_total = await models.get_total_expenses(db, month_start, month_end)
    month_categories = await models.get_expenses_by_category(db, month_start, month_end)

    from config import Config
    month_year = date.today().strftime("%Y-%m")
    budget_row = await models.get_budget(db, "total", month_year)
    budget = budget_row.get("monthly_limit", Config.DEFAULT_MONTHLY_BUDGET) if budget_row else Config.DEFAULT_MONTHLY_BUDGET

    return {
        "date": today,
        "expenses_today": expenses_today,
        "total_today": sum(e["amount"] for e in expenses_today),
        "food_today": food_today,
        "fitbit_yesterday": fitbit_yesterday,
        "month_total": month_total,
        "month_budget": budget,
        "month_remaining": budget - month_total,
        "month_categories": month_categories,
    }


async def _gather_weekly_data(db: Database) -> dict:
    ws, we = _week_range()
    pws, pwe = _prev_week_range()
    ms, me = _month_range()

    expenses = await models.get_expenses_range(db, ws, we)
    prev_expenses = await models.get_expenses_range(db, pws, pwe)
    categories = await models.get_expenses_by_category(db, ws, we)
    prev_categories = await models.get_expenses_by_category(db, pws, pwe)
    food = await models.get_food_range(db, ws, we)
    fitbit = await models.get_fitbit_range(db, ws, we)
    tracked = await models.get_tracked_days(db, ws, we)
    income = await models.get_total_income(db, ms, me)
    month_total = await models.get_total_expenses(db, ms, me)

    week_total = sum(e["amount"] for e in expenses)
    prev_total = sum(e["amount"] for e in prev_expenses)
    days_tracked = len(tracked)

    return {
        "period": f"{ws} to {we}",
        "week_total": week_total,
        "prev_week_total": prev_total,
        "week_change_pct": ((week_total - prev_total) / prev_total * 100) if prev_total else 0,
        "daily_avg": week_total / days_tracked if days_tracked else 0,
        "days_tracked": days_tracked,
        "categories": categories,
        "prev_categories": prev_categories,
        "food_log": food,
        "fitbit_data": fitbit,
        "month_income": income,
        "month_total": month_total,
        "savings_rate": ((income - month_total) / income * 100) if income > 0 else 0,
    }


async def get_daily_summary_data(db: Database) -> dict:
    return await _gather_daily_data(db)


async def get_weekly_summary_data(db: Database) -> dict:
    return await _gather_weekly_data(db)


async def generate_daily_report(db: Database) -> str:
    data = await _gather_daily_data(db)
    return await generate_daily_summary(data)


async def generate_weekly_report(db: Database) -> str:
    data = await _gather_weekly_data(db)
    return await generate_weekly_summary(data)


async def generate_trends(db: Database) -> str:
    """On-demand trend analysis for /trends command."""
    ws, we = _week_range()
    pws, pwe = _prev_week_range()
    ms, me = _month_range()
    pms, pme = _prev_month_range()

    data = {
        "this_week": {
            "total": await models.get_total_expenses(db, ws, we),
            "categories": await models.get_expenses_by_category(db, ws, we),
        },
        "prev_week": {
            "total": await models.get_total_expenses(db, pws, pwe),
            "categories": await models.get_expenses_by_category(db, pws, pwe),
        },
        "this_month": {
            "total": await models.get_total_expenses(db, ms, me),
            "categories": await models.get_expenses_by_category(db, ms, me),
        },
        "prev_month": {
            "total": await models.get_total_expenses(db, pms, pme),
            "categories": await models.get_expenses_by_category(db, pms, pme),
        },
        "tracked_days_this_week": len(await models.get_tracked_days(db, ws, we)),
    }

    from services.llm_service import _ask
    prompt = f"Spending trend data:\n{json.dumps(data, default=str)}"
    system = (
        "You are a personal finance analyst. Analyze spending trends from the data. "
        "Highlight week-over-week and month-over-month changes, anomalies in specific categories, "
        "and any concerning or positive patterns. Use ₹ for amounts. Keep it under 300 words. "
        "Use bullet points. Be specific with numbers."
    )
    return await _ask(prompt, system=system)


async def generate_insights(db: Database) -> str:
    """Deep cross-domain analysis for /insights command."""
    ws, we = _week_range()
    ms, me = _month_range()

    expenses = await models.get_expenses_range(db, ms, me)
    food = await models.get_food_range(db, ms, me)
    fitbit = await models.get_fitbit_range(db, ms, me)
    income = await models.get_total_income(db, ms, me)

    data = {
        "expenses_summary": await models.get_expenses_by_category(db, ms, me),
        "total_spent": sum(e["amount"] for e in expenses),
        "income": income,
        "food_log_count": len(food),
        "food_entries": food[:20],
        "fitbit_data": fitbit,
        "expense_dates_and_amounts": [
            {"date": e["date"], "amount": e["amount"], "category": e["category"]}
            for e in expenses
        ],
    }

    from services.llm_service import _ask
    prompt = f"Cross-domain data for insights:\n{json.dumps(data, default=str)}"
    system = (
        "You are a personal life analytics expert. Analyze the data looking for cross-domain "
        "correlations and insights. Connect spending patterns with health data (sleep, steps, "
        "heart rate) and food habits. Look for:\n"
        "1. Sleep quality vs spending behavior\n"
        "2. Activity levels vs food choices\n"
        "3. Day-of-week patterns\n"
        "4. Health metric trends\n"
        "5. Actionable suggestions\n\n"
        "Use ₹ for amounts. Be specific and data-driven. Under 400 words. Use bullet points."
    )
    return await _ask(prompt, system=system)
