"""Process classified food messages and store them."""

from __future__ import annotations

import logging

from db.database import Database
from db import models

logger = logging.getLogger(__name__)


async def handle_food(db: Database, parsed: dict) -> str:
    meal_type = parsed.get("meal_type", "snack")
    description = parsed.get("description", "")
    items = parsed.get("items")
    calories = parsed.get("estimated_calories")
    protein = parsed.get("estimated_protein")
    carbs = parsed.get("estimated_carbs")
    fat = parsed.get("estimated_fat")
    food_date = parsed.get("date")

    if not description:
        return "I couldn't figure out what you ate. Could you try again?"

    result = await models.add_food(
        db,
        meal_type=meal_type,
        description=description,
        items=items,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        food_date=food_date,
    )

    parts = [f"🍽 Logged {meal_type}: {description}"]
    if calories:
        nutrition = f"~{calories:.0f} cal"
        if protein:
            nutrition += f" | {protein:.0f}g protein"
        parts.append(f"📊 {nutrition}")
    parts.append(f"📅 {result['date']}")

    return "\n".join(parts)
