"""Natural-language to SQL query engine."""

from __future__ import annotations

import logging
from datetime import date

from db.database import Database
from db.models import run_readonly_query
from services.llm_service import generate_sql, format_query_answer

logger = logging.getLogger(__name__)


async def answer_question(db: Database, question: str) -> str:
    today = date.today().isoformat()

    result = await generate_sql(question, today)
    sql = result.get("sql", "").strip()
    explanation = result.get("explanation", "")

    if not sql:
        return "I couldn't understand that question. Could you rephrase it?"

    try:
        rows = await run_readonly_query(db, sql)
    except ValueError as exc:
        logger.warning("Blocked unsafe query: %s – %s", sql, exc)
        return "That query isn't allowed for safety reasons. Try rephrasing?"
    except Exception:
        logger.exception("Query execution failed: %s", sql)
        return "Something went wrong running that query. Try asking differently?"

    return await format_query_answer(question, rows, explanation)
