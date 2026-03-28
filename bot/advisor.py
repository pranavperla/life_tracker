"""Purchase advisor: assesses if a purchase is reasonable."""

from __future__ import annotations

import json
from datetime import date

from db.database import Database
from db import models
from services.llm_service import purchase_advice
from config import Config


async def assess_purchase(db: Database, item: str, amount: float) -> str:
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    month_end = today.isoformat()
    month_year = today.strftime("%Y-%m")

    month_spent = await models.get_total_expenses(db, month_start, month_end)
    month_income = await models.get_total_income(db, month_start, month_end)
    categories = await models.get_expenses_by_category(db, month_start, month_end)

    budget_row = await models.get_budget(db, "total", month_year)
    budget_limit = budget_row.get("monthly_limit", Config.DEFAULT_MONTHLY_BUDGET) if budget_row else Config.DEFAULT_MONTHLY_BUDGET

    savings_rate = 0.0
    if month_income > 0:
        savings_rate = (month_income - month_spent) / month_income

    result = await purchase_advice(
        item=item,
        amount=amount,
        monthly_income=month_income,
        month_spent=month_spent,
        budget_limit=budget_limit,
        category_breakdown=categories,
        savings_rate=savings_rate,
    )

    verdict_emoji = {"go": "✅", "wait": "⏳", "skip": "❌"}.get(
        result.get("verdict", ""), "🤔"
    )

    parts = [
        f"{verdict_emoji} **{result.get('verdict', 'unknown').upper()}**: {item} for ₹{amount:,.0f}",
        "",
        f"💬 {result.get('reasoning', '')}",
    ]
    if result.get("budget_impact"):
        parts.append(f"\n📊 {result['budget_impact']}")
    if result.get("suggestion"):
        parts.append(f"\n💡 {result['suggestion']}")

    return "\n".join(parts)
