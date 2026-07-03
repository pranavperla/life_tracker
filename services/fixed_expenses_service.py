"""Monthly fixed commitments vs flexible spending pool."""

from __future__ import annotations

from datetime import date, timedelta

from config import Config
from db.database import Database
from db import models

# Spending you manage from what's left after fixed bills
FLEXIBLE_CATEGORIES = (
    "Food & Groceries",
    "Groceries",
    "Food Delivery",
    "Dining Out",
    "Outings",
    "Credit Card Bill",
    "Miscellaneous",
    "Transport",
    "Fuel",
    "Cab/Auto",
    "Public Transport",
    "Entertainment",
    "Shopping",
    "Health",
    "Personal Care",
)

DEFAULT_FIXED_EXPENSES: list[dict] = [
    {
        "name": "Rent",
        "amount": 14_000,
        "category": "Rent",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": None,
        "sort_order": 1,
    },
    {
        "name": "Maid",
        "amount": 2_000,
        "category": "Household Help",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": None,
        "sort_order": 2,
    },
    {
        "name": "Cursor",
        "amount": 2_000,
        "category": "Subscriptions",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": "Cursor subscription",
        "sort_order": 3,
    },
    {
        "name": "Other Subscriptions",
        "amount": 3_000,
        "category": "Subscriptions",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": "Apps, streaming, etc.",
        "sort_order": 4,
    },
    {
        "name": "Bike petrol",
        "amount": 1_000,
        "category": "Fuel",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": "Regular commute fuel",
        "sort_order": 5,
    },
    {
        "name": "Municipality trash",
        "amount": 300,
        "category": "Utilities",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": None,
        "sort_order": 6,
    },
    {
        "name": "WiFi",
        "amount": 300,
        "category": "Utilities",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": None,
        "sort_order": 7,
    },
    {
        "name": "Electricity",
        "amount": 3_000,
        "category": "Utilities",
        "day_of_month": 1,
        "scheduled_amount": None,
        "scheduled_from": None,
        "notes": None,
        "sort_order": 8,
    },
]


def amount_for_month(item: dict, month_year: str) -> float:
    """Resolve amount including scheduled increases (e.g. rent 8k → 14k)."""
    sched = item.get("scheduled_amount")
    sched_from = item.get("scheduled_from")
    if sched is not None and sched_from:
        effective_month = str(sched_from)[:7]
        if month_year >= effective_month:
            return float(sched)
    return float(item["amount"])


async def ensure_defaults(db: Database) -> None:
    """Seed profile + fixed expenses on first run."""
    await models.ensure_finance_profile(db, Config.MONTHLY_INCOME)
    existing = await models.get_active_fixed_expenses(db)
    if existing:
        return
    for row in DEFAULT_FIXED_EXPENSES:
        await models.add_fixed_expense(db, **row)
    # Mirror into recurring_expenses for monthly confirm prompts
    for row in DEFAULT_FIXED_EXPENSES:
        amt = amount_for_month(row, date.today().strftime("%Y-%m"))
        await models.add_recurring(
            db,
            description=row["name"],
            amount=amt,
            category=row["category"],
            day_of_month=row.get("day_of_month"),
        )


async def build_monthly_plan(db: Database, month_year: str | None = None) -> dict:
    """Income, fixed commitments, flexible pool, and actual flexible spend."""
    month_year = month_year or date.today().strftime("%Y-%m")
    profile = await models.get_finance_profile(db)
    income = float(profile.get("monthly_income") or Config.MONTHLY_INCOME)

    fixed_rows = await models.get_active_fixed_expenses(db)
    fixed_lines: list[dict] = []
    fixed_total = 0.0
    for row in fixed_rows:
        amt = amount_for_month(row, month_year)
        fixed_total += amt
        line = {**row, "resolved_amount": amt}
        if row.get("scheduled_amount") and amount_for_month(row, month_year) != float(
            row["amount"]
        ):
            line["was"] = float(row["amount"])
        fixed_lines.append(line)

    flexible_budget = income - fixed_total

    today = date.today()
    if month_year == today.strftime("%Y-%m"):
        month_start = today.replace(day=1).isoformat()
        month_end = today.isoformat()
    else:
        y, m = map(int, month_year.split("-"))
        month_start = date(y, m, 1).isoformat()
        if m == 12:
            month_end = date(y, 12, 31).isoformat()
        else:
            month_end = (date(y, m + 1, 1) - timedelta(days=1)).isoformat()

    flexible_spent = await models.get_total_expenses_in_categories(
        db, month_start, month_end, list(FLEXIBLE_CATEGORIES)
    )
    all_spent = await models.get_total_expenses(db, month_start, month_end)
    flexible_left = flexible_budget - flexible_spent

    return {
        "month_year": month_year,
        "income": income,
        "fixed_lines": fixed_lines,
        "fixed_total": fixed_total,
        "flexible_budget": flexible_budget,
        "flexible_spent": flexible_spent,
        "flexible_left": flexible_left,
        "all_spent": all_spent,
        "flexible_categories": FLEXIBLE_CATEGORIES,
    }


def format_plan_message(plan: dict) -> str:
    lines = [
        f"📋 **Monthly plan — {plan['month_year']}**\n",
        f"💼 Income: ₹{plan['income']:,.0f}",
        f"🔒 **Fixed commitments:** ₹{plan['fixed_total']:,.0f}",
    ]
    for row in plan["fixed_lines"]:
        amt = row["resolved_amount"]
        fid = row.get("id", "?")
        extra = ""
        if row.get("was"):
            extra = f" _(was ₹{row['was']:,.0f})_"
        if row.get("scheduled_amount") and row.get("scheduled_from"):
            extra += f" _(→ ₹{row['scheduled_amount']:,.0f} from {str(row['scheduled_from'])[:7]})_"
        if row.get("notes"):
            extra += f" — {row['notes']}"
        lines.append(f"  • **[#{fid}]** ₹{amt:,.0f} — {row['name']}{extra}")

    lines.append(
        "\n_Edit: `/fixed set ID AMOUNT` · Remove: `/fixed remove ID` · "
        "Future rent: `/fixed set ID from 2026-04 14000`_"
    )

    lines.extend(
        [
            f"\n🎯 **Flexible pool** (groceries, outings, credit card bill, misc):",
            f"   Budget: ₹{plan['flexible_budget']:,.0f}",
            f"   Spent so far: ₹{plan['flexible_spent']:,.0f}",
            f"   **Left: ₹{plan['flexible_left']:,.0f}**",
            f"\n📊 All logged expenses this month: ₹{plan['all_spent']:,.0f}",
            f"\n_Flexible categories: {', '.join(plan['flexible_categories'][:4])}…_",
        ]
    )
    return "\n".join(lines)


async def set_fixed_amount(
    db: Database,
    fixed_id: int,
    amount: float,
    *,
    scheduled_from: str | None = None,
    as_scheduled: bool = False,
) -> tuple[bool, str]:
    """Update a fixed line. as_scheduled=True sets scheduled_amount/from instead of base amount."""
    row = await models.get_fixed_expense(db, fixed_id)
    if not row:
        return False, f"No active fixed expense with id #{fixed_id}. Use /fixed to see ids."

    if as_scheduled and scheduled_from:
        month = scheduled_from[:7] if len(scheduled_from) >= 7 else scheduled_from
        from_date = f"{month}-01" if len(month) == 7 else scheduled_from
        await models.update_fixed_expense(
            db,
            fixed_id,
            scheduled_amount=amount,
            scheduled_from=from_date,
        )
        msg = f"#{fixed_id} {row['name']}: ₹{amount:,.0f} from {month}"
    else:
        await models.update_fixed_expense(
            db,
            fixed_id,
            amount=amount,
            scheduled_amount=None,
            scheduled_from=None,
        )
        msg = f"#{fixed_id} {row['name']}: ₹{amount:,.0f}/month"

    updated = await models.get_fixed_expense_by_id(db, fixed_id)
    resolved = amount_for_month(updated, date.today().strftime("%Y-%m"))
    await models.sync_recurring_for_fixed_name(db, row["name"], resolved, row["category"])
    return True, msg


async def remove_fixed(db: Database, fixed_id: int) -> tuple[bool, str]:
    row = await models.get_fixed_expense(db, fixed_id)
    if not row:
        return False, f"No active fixed expense with id #{fixed_id}."
    await models.deactivate_fixed_expense(db, fixed_id)
    await models.deactivate_recurring_by_name(db, row["name"])
    return True, f"Removed #{fixed_id} — {row['name']}"
