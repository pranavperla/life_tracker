"""Classify incoming messages and route to the appropriate parser."""

from __future__ import annotations

import re

import logging
from datetime import date

from parsers.heuristic import try_parse_expense_heuristic
from services.llm_service import classify_message

logger = logging.getLogger(__name__)

# Heuristics to skip LLM for obvious commands
_COMMAND_RE = re.compile(r"^/\w+")

# Common UPI / bank SMS patterns
_SMS_PATTERNS = [
    re.compile(r"(debited|credited|paid|transferred|received)", re.I),
    re.compile(r"(UPI|NEFT|IMPS|A/c|Acct)", re.I),
    re.compile(r"Rs\.?\s*\d+", re.I),
]


def _looks_like_sms(text: str) -> bool:
    matches = sum(1 for p in _SMS_PATTERNS if p.search(text))
    return matches >= 2


async def route_message(text: str) -> dict:
    """Return a classification dict with at least an 'intent' key."""
    text = text.strip()

    if _COMMAND_RE.match(text):
        return {"intent": "command", "raw": text}

    today = date.today().isoformat()

    # 1) Fast offline parse for common expense shapes (no Gemini quota needed)
    quick = try_parse_expense_heuristic(text, today)
    if quick:
        quick["raw"] = text
        return quick

    # 2) LLM classification for everything else
    is_sms = _looks_like_sms(text)
    try:
        if is_sms:
            prefixed = f"[Forwarded bank SMS] {text}"
            result = await classify_message(prefixed, today)
        else:
            result = await classify_message(text, today)
    except Exception as exc:
        logger.warning("Gemini classification failed (%s); retrying heuristics", exc)
        result = {"intent": "unknown"}

    # 3) If LLM unavailable (429, etc.) or unknown, try heuristics again (broader attempt)
    if result.get("intent") == "unknown":
        fallback = try_parse_expense_heuristic(text, today)
        if fallback:
            fallback["raw"] = text
            return fallback

    result["raw"] = text
    return result
