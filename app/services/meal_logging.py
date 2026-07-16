from __future__ import annotations

import datetime as dt
import logging

from app.db.queries import MealRecord, MealRepository

logger = logging.getLogger(__name__)

GROUPING_WINDOW = dt.timedelta(minutes=10)

NOT_FOOD_REPLY = (
    "I couldn't spot any food in that photo — could you send a clearer picture of your meal?"
)


async def log_meal_photo(
    user_id: str,
    media_id: str,
    vision_result: dict,
    repo: MealRepository,
    now: dt.datetime | None = None,
) -> MealRecord:
    """Create a new meal entry, or append to an open one within the 10-minute
    grouping window (FR-014, research.md #2). The window slides: appending a
    photo refreshes the meal's logged_at to `now`, so a meal stays "open" as
    long as photos keep arriving within 10 minutes of the *previous* one,
    rather than being anchored only to the first photo."""
    now = now or dt.datetime.now(dt.UTC)
    foods = vision_result["foods"]
    total_calories = vision_result["total_calories"]
    confidence = vision_result.get("confidence")

    existing = await repo.find_open_meal(user_id, now, GROUPING_WINDOW)
    if existing is not None:
        return await repo.append_to_meal(existing, media_id, foods, total_calories, confidence, now)
    return await repo.create_meal(user_id, media_id, foods, total_calories, confidence, now)


def format_range_reply(meal: MealRecord) -> str:
    """Present the meal's totals as a ±20% range, never a false-precision exact
    number (FR-002, FR-003, FR-012)."""
    calorie_low = meal.total_calories * 0.8
    calorie_high = meal.total_calories * 1.2
    protein = sum(food.get("protein_g", 0) for food in meal.foods)
    carbs = sum(food.get("carbs_g", 0) for food in meal.foods)
    fat = sum(food.get("fat_g", 0) for food in meal.foods)
    return (
        f"That's about {calorie_low:.0f}-{calorie_high:.0f} kcal "
        f"(protein ~{protein:.0f}g, carbs ~{carbs:.0f}g, fat ~{fat:.0f}g)."
    )


async def handle_incoming_photo(user_id: str, wa_phone: str, media_id: str) -> str:
    """Webhook-facing entrypoint: `user_id` is resolved by the caller (webhook
    dispatch) so it can also be used for message-dedupe bookkeeping without
    resolving the user twice. Returns the reply text to send back."""
    from app.db import queries
    from app.db.pool import get_pool
    from app.services import vision
    from app.whatsapp import media as media_client

    pool = await get_pool()
    repo = queries.AsyncpgMealRepository(pool)

    image_bytes = await media_client.download_media(media_id)
    result = await vision.analyze_photo(image_bytes)

    if not result["foods"]:
        logger.info("Photo from %s not recognized as food (media_id=%s)", _mask(wa_phone), media_id)
        return NOT_FOOD_REPLY

    meal = await log_meal_photo(user_id, media_id, result, repo)
    logger.info(
        "Logged meal for %s (meal_id=%s, photos_combined=%d, total_calories=%.0f)",
        _mask(wa_phone),
        meal.id,
        len(meal.photo_media_ids),
        meal.total_calories,
    )
    return format_range_reply(meal)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
