"""Process classified expense messages and store them."""

from __future__ import annotations

import logging

from db.database import Database
from db import models

logger = logging.getLogger(__name__)


async def handle_expense(db: Database, parsed: dict) -> str:
    amount = parsed.get("amount")
    if not amount or amount <= 0:
        return "I couldn't figure out the amount. Could you try again?"

    category = parsed.get("category", "Miscellaneous")
    subcategory = parsed.get("subcategory")
    description = parsed.get("description", "")
    expense_date = parsed.get("date")

    result = await models.add_expense(
        db,
        amount=float(amount),
        category=category,
        subcategory=subcategory,
        description=description,
        expense_date=expense_date,
    )

    return (
        f"Logged: ₹{amount:,.0f} → {category}"
        + (f" / {subcategory}" if subcategory else "")
        + (f"\n📝 {description}" if description else "")
        + f"\n📅 {result['date']}"
    )


async def handle_split(db: Database, parsed: dict) -> str:
    total = parsed.get("total_amount", 0)
    split_count = parsed.get("split_count", 1)
    if total <= 0 or split_count <= 0:
        return "I couldn't parse the split. Try: 'dinner 2000 split 4'"

    share = round(total / split_count, 2)
    category = parsed.get("category", "Miscellaneous")
    description = parsed.get("description", "")
    expense_date = parsed.get("date")

    result = await models.add_expense(
        db,
        amount=share,
        category=category,
        description=f"{description} (split {split_count} ways, total ₹{total:,.0f})",
        expense_date=expense_date,
    )

    return (
        f"Logged your share: ₹{share:,.0f} (₹{total:,.0f} ÷ {split_count})"
        f"\n→ {category}"
        + (f"\n📝 {description}" if description else "")
        + f"\n📅 {result['date']}"
    )


async def handle_lending(db: Database, parsed: dict) -> str:
    direction = parsed.get("direction", "lent")
    amount = parsed.get("amount", 0)
    person = parsed.get("person", "someone")
    description = parsed.get("description", "")
    expense_date = parsed.get("date")

    if amount <= 0:
        return "I couldn't figure out the amount. Try again?"

    if direction == "lent":
        result = await models.add_expense(
            db,
            amount=float(amount),
            category="Lending",
            description=description or f"Lent to {person}",
            person=person,
            expense_date=expense_date,
        )
        return f"Logged: Lent ₹{amount:,.0f} to {person}\n📅 {result['date']}"
    else:
        result = await models.add_income(
            db,
            amount=float(amount),
            source="Payback",
            description=description or f"Payback from {person}",
            person=person,
            income_date=expense_date,
        )
        return f"Logged: ₹{amount:,.0f} payback from {person}\n📅 {result['date']}"
