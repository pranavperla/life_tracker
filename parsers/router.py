"""Classify incoming messages and route to the appropriate parser."""

from __future__ import annotations

import re

import logging
from datetime import date

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

    # Quick SMS detection to help the LLM
    is_sms = _looks_like_sms(text)

    today = date.today().isoformat()

    if is_sms:
        # Still send through LLM for full parsing, but hint it
        prefixed = f"[Forwarded bank SMS] {text}"
        result = await classify_message(prefixed, today)
    else:
        result = await classify_message(text, today)

    result["raw"] = text
    return result
