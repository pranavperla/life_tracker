"""Parse forwarded UPI / bank SMS messages."""

from __future__ import annotations

import re
import logging
from datetime import date

from db.database import Database
from db import models
from services.llm_service import parse_sms

logger = logging.getLogger(__name__)

# Regex fallback for amount extraction from Indian bank SMS
_AMOUNT_RE = re.compile(
    r"(?:Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", re.I
)


def _extract_amount_regex(text: str) -> float | None:
    m = _AMOUNT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


async def handle_sms(db: Database, parsed: dict, raw_text: str) -> dict:
    """
    Returns a dict with:
      - "response": str to send back
      - "needs_clarification": bool
      - "pending_expense": dict or None  (to be stored after user clarifies)
    """
    today = date.today().isoformat()

    amount = parsed.get("amount")
    merchant = parsed.get("merchant", "")
    category = parsed.get("category", "Miscellaneous")
    needs_clarification = parsed.get("needs_clarification", False)
    expense_date = parsed.get("date") or today

    # Fallback: extract amount from raw SMS if LLM missed it
    if not amount:
        amount = _extract_amount_regex(raw_text)
        if not amount:
            return {
                "response": "I couldn't find the transaction amount in that SMS. Can you type the expense manually?",
                "needs_clarification": False,
                "pending_expense": None,
            }

    if needs_clarification or not merchant:
        clarification = parsed.get(
            "clarification_question",
            f"₹{amount:,.0f} transaction detected. What was this for?"
        )
        return {
            "response": clarification,
            "needs_clarification": True,
            "pending_expense": {
                "amount": float(amount),
                "original_sms": raw_text,
                "date": expense_date,
            },
        }

    # Auto-categorized — store and confirm
    result = await models.add_expense(
        db,
        amount=float(amount),
        category=category,
        description=merchant,
        source="sms",
        original_sms=raw_text,
        expense_date=expense_date,
    )

    return {
        "response": (
            f"📱 SMS logged: ₹{amount:,.0f} → {category}"
            f"\n🏪 {merchant}"
            f"\n📅 {result['date']}"
            f"\n\nWrong? Say 'wrong' to correct."
        ),
        "needs_clarification": False,
        "pending_expense": None,
    }


async def complete_sms_expense(db: Database, pending: dict, category: str, description: str) -> str:
    """Store a pending SMS expense after user clarifies the category."""
    result = await models.add_expense(
        db,
        amount=pending["amount"],
        category=category,
        description=description,
        source="sms",
        original_sms=pending.get("original_sms", ""),
        expense_date=pending.get("date"),
    )
    return (
        f"📱 SMS logged: ₹{pending['amount']:,.0f} → {category}"
        f"\n📝 {description}"
        f"\n📅 {result['date']}"
    )
