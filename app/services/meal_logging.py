from __future__ import annotations

import datetime as dt
import logging

from app.db.queries import MealRecord, MealRepository

logger = logging.getLogger(__name__)

GROUPING_WINDOW = dt.timedelta(minutes=10)
LOW_CONFIDENCE_THRESHOLD = 0.6

NOT_FOOD_REPLY = (
    "I couldn't spot any food in that photo — could you send a clearer picture of your meal?"
)
LOW_CONFIDENCE_FALLBACK_REPLY = (
    "I'm not confident enough about that photo to log it — could you send a clearer one?"
)


async def log_meal_photo(
    user_id: str,
    media_id: str,
    vision_result: dict,
    repo: MealRepository,
    now: dt.datetime | None = None,
) -> MealRecord:
    """Create a new meal entry, or append to an open one within the 10-minute
    grouping window (FR-014, research.md #2). The window is anchored to the
    *first* photo: appending does not extend it, so a meal always closes
    exactly 10 minutes after it started, no matter how many photos arrive in
    between. A sliding window (refreshing on every append) was tried and found
    live to merge unrelated meals across an entire multi-hour test session."""
    now = now or dt.datetime.now(dt.UTC)
    foods = vision_result["foods"]
    total_calories = vision_result["total_calories"]
    confidence = vision_result.get("confidence")

    existing = await repo.find_open_meal(user_id, now, GROUPING_WINDOW)
    if existing is not None:
        return await repo.append_to_meal(existing, media_id, foods, total_calories, confidence)
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

    image_bytes, media_type = await media_client.download_media(media_id)
    result = await vision.analyze_photo(image_bytes, media_type=media_type)

    if not result["foods"]:
        logger.info("Photo from %s not recognized as food (media_id=%s)", _mask(wa_phone), media_id)
        return NOT_FOOD_REPLY

    confidence = result.get("confidence")
    clarifying_question = result.get("clarifying_question")
    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        # Per app/prompts/calorie_vision.md rule 6: below this threshold the
        # model is instructed to ask ONE clarifying question rather than
        # guess. This was previously never wired up — the code logged and
        # replied with the guess regardless of confidence, which live testing
        # showed producing unreliable, hard-to-trust totals (e.g. 0.55
        # confidence treated identically to 0.95).
        logger.info(
            "Low-confidence photo from %s (confidence=%.2f, media_id=%s), "
            "asking for clarification instead of logging",
            _mask(wa_phone),
            confidence,
            media_id,
        )
        return clarifying_question or LOW_CONFIDENCE_FALLBACK_REPLY

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
