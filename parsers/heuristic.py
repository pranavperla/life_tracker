"""Offline parsing for common expense phrases when Gemini is unavailable or to save quota."""

from __future__ import annotations

import re
from typing import Any

# (keywords substrings), category
_MERCHANT_CATEGORIES: list[tuple[list[str], str]] = [
    (["zomato", "swiggy", "blinkit", "instamart", "dunzo", "foodpanda"], "Food Delivery"),
    (["uber", "ola", "rapido", "auto", "meru"], "Cab/Auto"),
    (["metro", "bus", "irctc", "railway"], "Public Transport"),
    (["shell", "petrol", "fuel", "bharat", "hpcl", "iocl"], "Fuel"),
    (["netflix", "spotify", "prime video", "hotstar", "youtube premium"], "Subscriptions"),
    (["amazon", "flipkart", "myntra", "nykaa"], "Shopping"),
    (["bigbasket", "grofers", "dmart", "reliance fresh"], "Groceries"),
    (["cafe", "starbucks", "costa"], "Dining Out"),
    (["rent", "landlord", "housing"], "Rent"),
    (["electricity", "bescom", "mseb", "utility"], "Utilities"),
]


def _guess_category(description: str) -> str:
    d = description.lower().strip()
    for keywords, cat in _MERCHANT_CATEGORIES:
        for kw in keywords:
            if kw in d:
                return cat
    return "Miscellaneous"


def try_parse_expense_heuristic(text: str, today: str) -> dict[str, Any] | None:
    """
    Parse simple expense strings without LLM.
    Returns an 'expense' intent dict or None.
    """
    t = text.strip()
    if not t or len(t) > 500:
        return None

    amount: float | None = None
    rest: str | None = None

    # "344 rs on zomato" / "500 INR on swiggy" (rs/inr before on/for/at)
    m = re.match(
        r"^(\d+(?:[.,]\d+)?)\s*(?:rs|rupees|inr|₹)\s+(?:on|for|at)\s+(.+)$",
        t,
        re.I,
    )
    if m:
        amount = float(m.group(1).replace(",", ""))
        rest = m.group(2).strip()

    # "500 on zomato" (amount then on/for/at, no rs)
    if amount is None:
        m = re.match(
            r"^(\d+(?:[.,]\d+)?)\s+(?:on|for|at)\s+(.+)$",
            t,
            re.I,
        )
        if m:
            amount = float(m.group(1).replace(",", ""))
            rest = m.group(2).strip()

    # "spent 500 on groceries"
    if amount is None:
        m = re.match(r"^spent\s+(\d+(?:[.,]\d+)?)\s+on\s+(.+)$", t, re.I)
        if m:
            amount = float(m.group(1).replace(",", ""))
            rest = m.group(2).strip()

    # "uber 200" / "zomato 344"
    if amount is None:
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9\s]{0,40}?)\s+(\d+(?:[.,]\d+)?)$", t)
        if m:
            rest = m.group(1).strip()
            amount = float(m.group(2).replace(",", ""))

    # "200 uber"
    if amount is None:
        m = re.match(r"^(\d+(?:[.,]\d+)?)\s+([a-zA-Z][a-zA-Z0-9\s]{0,40})$", t)
        if m:
            amount = float(m.group(1).replace(",", ""))
            rest = m.group(2).strip()

    if amount is None or amount <= 0 or not rest:
        return None

    category = _guess_category(rest)
    return {
        "intent": "expense",
        "amount": amount,
        "description": rest.title() if rest.islower() else rest,
        "category": category,
        "subcategory": None,
        "date": today,
    }
