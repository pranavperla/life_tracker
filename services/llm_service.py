"""Gemini LLM service with all prompt templates."""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from config import Config

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client


async def _ask(prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
    client = get_client()
    config = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=system or None,
    )
    response = await client.aio.models.generate_content(
        model=Config.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text or ""


async def _ask_json(prompt: str, *, system: str = "") -> dict | list:
    """Ask and parse JSON from response. Strips markdown fences if present."""
    raw = await _ask(prompt, system=system)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Message classification / routing
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = """You are a personal life tracker assistant. Classify user messages into one of these intents and extract structured data. Always respond with valid JSON only, no extra text.

Intents:
- "expense": user is logging a spend (e.g. "spent 500 on groceries", "uber 200", "rent 25000")
- "sms_forward": user forwarded a bank/UPI transaction SMS
- "food": user is logging food/meals (e.g. "ate 2 rotis and dal for lunch", "had pizza for dinner")
- "income": user is logging income (e.g. "salary 80000", "freelance 15000")
- "lending": user lent money or someone paid back (e.g. "lent Rahul 5000", "Rahul paid back 2000")
- "purchase_check": user is asking if a purchase is reasonable (e.g. "should I buy AirPods for 18000?")
- "question": user is asking about their data (e.g. "how much did I spend on food this month?")
- "correction": user wants to fix the last entry (e.g. "wrong, that was 300", "delete the uber entry")
- "split": user wants to split an expense (e.g. "dinner 2000 split 4")
- "command": user typed a bot command (starts with /)
- "unknown": cannot determine intent

For date references, resolve them relative to today. If no date is mentioned, use "today".
Date values must be YYYY-MM-DD format.

Response format for each intent:

expense: {"intent": "expense", "amount": number, "description": "...", "category": "...", "subcategory": "...", "date": "YYYY-MM-DD"}
sms_forward: {"intent": "sms_forward", "amount": number, "merchant": "...", "category": "...", "date": "YYYY-MM-DD", "needs_clarification": bool, "clarification_question": "..."}
food: {"intent": "food", "meal_type": "breakfast|lunch|dinner|snack", "description": "...", "items": ["item1", "item2"], "estimated_calories": number, "estimated_protein": number, "estimated_carbs": number, "estimated_fat": number, "date": "YYYY-MM-DD"}
income: {"intent": "income", "amount": number, "source": "...", "description": "...", "date": "YYYY-MM-DD"}
lending: {"intent": "lending", "direction": "lent|payback", "amount": number, "person": "...", "description": "...", "date": "YYYY-MM-DD"}
purchase_check: {"intent": "purchase_check", "item": "...", "amount": number}
question: {"intent": "question", "question": "the user's question as-is"}
correction: {"intent": "correction", "action": "update|delete", "field": "amount|category|description", "new_value": "...", "search_hint": "..."}
split: {"intent": "split", "total_amount": number, "split_count": number, "description": "...", "category": "...", "date": "YYYY-MM-DD"}
command: {"intent": "command"}
unknown: {"intent": "unknown"}

Categories to use: Food & Groceries, Food Delivery, Groceries, Dining Out, Transport, Fuel, Cab/Auto, Public Transport, Housing, Rent, Utilities, Maintenance, Shopping, Electronics, Clothing, Subscriptions, Entertainment, Health, Education, Lending, Personal Care, Miscellaneous"""


async def classify_message(message: str, today: str) -> dict:
    prompt = f"Today's date: {today}\n\nUser message: {message}"
    try:
        result = await _ask_json(prompt, system=ROUTER_SYSTEM)
        return result if isinstance(result, dict) else {"intent": "unknown"}
    except Exception:
        logger.exception("Failed to classify message")
        return {"intent": "unknown"}


# ---------------------------------------------------------------------------
# Text-to-SQL query engine
# ---------------------------------------------------------------------------

QUERY_SYSTEM = """You are a SQL query generator for a personal tracker database. Given a user's natural language question, generate a SQLite SELECT query.

Tables and columns:
- expenses: id, amount, currency, category, subcategory, description, source, original_sms, person, date, created_at
- income: id, amount, source, description, person, date, created_at
- food_log: id, meal_type, description, items_json, estimated_calories, estimated_protein, estimated_carbs, estimated_fat, date, created_at
- fitbit_data: id, date, sleep_score, sleep_hours, deep_sleep_mins, rem_sleep_mins, steps, resting_hr, hrv, spo2, active_zone_mins, calories_burned, skin_temp_variation, created_at
- budgets: id, category, monthly_limit, month_year
- tracking_days: id, date, has_expenses, confirmed_zero_day
- recurring_expenses: id, description, amount, category, day_of_month, last_confirmed, active

All dates are in YYYY-MM-DD format. Use SQLite date functions.
For lending queries: expenses with category='Lending' are loans given, income with person matching is paybacks.

Respond with ONLY valid JSON: {"sql": "SELECT ...", "explanation": "brief explanation"}
ONLY SELECT queries. Never INSERT/UPDATE/DELETE/DROP."""


async def generate_sql(question: str, today: str) -> dict:
    prompt = f"Today's date: {today}\n\nQuestion: {question}"
    try:
        result = await _ask_json(prompt, system=QUERY_SYSTEM)
        return result if isinstance(result, dict) else {"sql": "", "explanation": "Failed to generate query"}
    except Exception:
        logger.exception("Failed to generate SQL")
        return {"sql": "", "explanation": "Failed to generate query"}


ANSWER_SYSTEM = """You are a personal finance assistant. Given raw query results, compose a clear, friendly, concise answer to the user's question. Use Indian Rupee symbol (₹) for amounts. Keep it conversational and brief. If data is empty, say so helpfully."""


async def format_query_answer(question: str, sql_results: list[dict], explanation: str) -> str:
    data_str = json.dumps(sql_results[:50], default=str)
    prompt = (
        f"User asked: {question}\n\n"
        f"Query explanation: {explanation}\n\n"
        f"Raw data ({len(sql_results)} rows):\n{data_str}"
    )
    return await _ask(prompt, system=ANSWER_SYSTEM)


# ---------------------------------------------------------------------------
# Purchase advisor
# ---------------------------------------------------------------------------

ADVISOR_SYSTEM = """You are a personal finance advisor. Given the user's financial context, assess whether a purchase is reasonable.

Provide your response as JSON:
{
    "verdict": "go|wait|skip",
    "reasoning": "2-3 sentences explaining why",
    "budget_impact": "how this affects the monthly budget",
    "suggestion": "optional alternative or tip"
}

Be honest and practical. Consider savings rate, budget remaining, and spending patterns."""


async def purchase_advice(
    item: str,
    amount: float,
    monthly_income: float,
    month_spent: float,
    budget_limit: float,
    category_breakdown: list[dict],
    savings_rate: float,
) -> dict:
    context = (
        f"Item: {item}, Cost: ₹{amount:,.0f}\n"
        f"Monthly income: ₹{monthly_income:,.0f}\n"
        f"Spent this month so far: ₹{month_spent:,.0f}\n"
        f"Monthly budget: ₹{budget_limit:,.0f}\n"
        f"Remaining budget: ₹{budget_limit - month_spent:,.0f}\n"
        f"Current savings rate: {savings_rate:.0%}\n"
        f"Category breakdown this month: {json.dumps(category_breakdown, default=str)}"
    )
    try:
        return await _ask_json(context, system=ADVISOR_SYSTEM)
    except Exception:
        logger.exception("Purchase advice failed")
        return {"verdict": "unknown", "reasoning": "Could not generate advice", "budget_impact": "", "suggestion": ""}


# ---------------------------------------------------------------------------
# Insights / summaries
# ---------------------------------------------------------------------------

DAILY_SYSTEM = """You are a personal life tracker. Generate a brief daily summary from the user's data. Be conversational, use ₹ for amounts. Mention notable things only - skip sections with no data. Keep it under 200 words."""


async def generate_daily_summary(data: dict) -> str:
    prompt = f"Daily data:\n{json.dumps(data, default=str)}"
    return await _ask(prompt, system=DAILY_SYSTEM)


WEEKLY_SYSTEM = """You are a personal life analytics assistant. Generate a weekly insights report from the user's data. Include:
1. Spending overview (total, daily avg, top categories)
2. Food patterns (if data available)
3. Health highlights from Fitbit (sleep, activity trends)
4. Cross-domain insights (correlations between spending, food, sleep, activity)
5. Anomalies or notable patterns
6. Data completeness note (how many days tracked)

Use ₹ for amounts. Be conversational but data-driven. Use bullet points. Under 400 words."""


async def generate_weekly_summary(data: dict) -> str:
    prompt = f"Weekly data:\n{json.dumps(data, default=str)}"
    return await _ask(prompt, system=WEEKLY_SYSTEM)


# ---------------------------------------------------------------------------
# SMS parsing assist
# ---------------------------------------------------------------------------

SMS_SYSTEM = """Extract transaction details from an Indian bank/UPI SMS. Respond with JSON only:
{
    "amount": number,
    "merchant": "merchant or recipient name",
    "category": "best guess category from: Food Delivery, Groceries, Dining Out, Transport, Fuel, Cab/Auto, Shopping, Electronics, Clothing, Subscriptions, Entertainment, Housing, Rent, Utilities, Health, Education, Miscellaneous",
    "is_personal_transfer": bool,
    "date": "YYYY-MM-DD if mentioned, else null"
}"""


async def parse_sms(sms_text: str, today: str) -> dict:
    prompt = f"Today: {today}\n\nSMS: {sms_text}"
    try:
        return await _ask_json(prompt, system=SMS_SYSTEM)
    except Exception:
        logger.exception("SMS parsing failed")
        return {}
