"""Purchase advisor: assesses if a purchase is reasonable."""

from __future__ import annotations

from datetime import date

from db.database import Database
from db import models
from services.llm_service import purchase_advice
from services.fixed_expenses_service import build_monthly_plan


async def assess_purchase(db: Database, item: str, amount: float) -> str:
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    month_end = today.isoformat()
    month_year = today.strftime("%Y-%m")

    month_income = await models.get_total_income(db, month_start, month_end)
    categories = await models.get_expenses_by_category(db, month_start, month_end)
    plan = await build_monthly_plan(db, month_year)

    budget_row = await models.get_budget(db, "total", month_year)
    budget_limit = budget_row.get("monthly_limit", plan["flexible_budget"]) if budget_row else plan["flexible_budget"]

    savings_rate = 0.0
    if plan["income"] > 0:
        savings_rate = (plan["income"] - plan["flexible_spent"]) / plan["income"]

    result = await purchase_advice(
        item=item,
        amount=amount,
        monthly_income=month_income or plan["income"],
        month_spent=plan["flexible_spent"],
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
