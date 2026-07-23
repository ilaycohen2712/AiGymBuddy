from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from app.config import settings
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
    model_id: str | None = None,
) -> MealRecord:
    """Create a new meal entry, or append to an open one within the 10-minute
    grouping window (FR-014, research.md #2). The window is anchored to the
    *first* photo: appending does not extend it, so a meal always closes
    exactly 10 minutes after it started, no matter how many photos arrive in
    between. A sliding window (refreshing on every append) was tried and found
    live to merge unrelated meals across an entire multi-hour test session.

    `model_id`: which vision model produced `vision_result`, for live
    traceability (FR-008, specs/003-vision-model-comparison)."""
    now = now or dt.datetime.now(dt.UTC)
    foods = vision_result["foods"]
    total_calories = vision_result["total_calories"]
    confidence = vision_result.get("confidence")

    existing = await repo.find_open_meal(user_id, now, GROUPING_WINDOW)
    if existing is not None:
        meal = await repo.append_to_meal(
            existing, media_id, foods, total_calories, confidence, model_id
        )
        bucket_anchor = existing.logged_at
    else:
        meal = await repo.create_meal(
            user_id, media_id, foods, total_calories, confidence, now, model_id
        )
        bucket_anchor = now

    await _accumulate_daily_total(repo, user_id, bucket_anchor, foods, total_calories)
    return meal


async def _accumulate_daily_total(
    repo: MealRepository,
    user_id: str,
    anchor: dt.datetime,
    foods: list[dict],
    total_calories: float,
) -> None:
    """Increments daily_totals by exactly this photo's own contribution —
    the same delta whether it started a new meal or was appended to an open
    one, so a combined meal is never double-counted (spec 002-daily-total-
    tracking, FR-004). Bucketed by the local calendar date of `anchor` — the
    meal's actual start time for an appended photo, not necessarily "now" —
    so a photo that happens to arrive just after a user's local midnight
    still lands in the bucket its meal actually started in (data-model.md).

    KNOWN EDGE CASE (reviewer-flagged, accepted): the time zone is re-read
    fresh on every call, not snapshotted once per meal. If a user's time
    zone changes (User Story 4) in the narrow window between two photos of
    the *same still-open* meal, each photo's delta could bucket into a
    different daily_totals row for that one meal — not double-counting
    (totals still sum correctly overall), but a rare misattribution this
    feature's FR-014 guarantee doesn't fully cover (FR-014 only promises
    already-*closed* meals aren't retroactively reattributed). Fixing this
    properly would mean persisting each meal's bucket date at creation
    (a new `meals` column), which is out of this feature's current scope."""
    time_zone = await repo.get_time_zone(user_id)
    local_date = anchor.astimezone(ZoneInfo(time_zone)).date()
    protein = sum(food.get("protein_g", 0) for food in foods)
    carbs = sum(food.get("carbs_g", 0) for food in foods)
    fat = sum(food.get("fat_g", 0) for food in foods)
    await repo.upsert_daily_total(
        user_id, local_date, calories=total_calories, protein_g=protein, carbs_g=carbs, fat_g=fat
    )


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

    clarifying_question = result.get("clarifying_question")
    if clarifying_question:
        # Per app/prompts/calorie_vision.md (v2) rule 6: only fires when
        # something essential is genuinely not visible (hidden filling,
        # opaque cup, etc) — not for general uncertainty about visible food.
        # Most photos should reach the estimate path below instead.
        await queries.set_pending_clarification(
            pool, user_id, media_id, media_type, clarifying_question
        )
        logger.info(
            "Photo from %s needs clarification (media_id=%s): %s",
            _mask(wa_phone),
            media_id,
            clarifying_question,
        )
        return clarifying_question

    meal = await log_meal_photo(
        user_id, media_id, result, repo, model_id=settings.live_vision_model_id
    )
    logger.info(
        "Logged meal for %s (meal_id=%s, photos_combined=%d, total_calories=%.0f)",
        _mask(wa_phone),
        meal.id,
        len(meal.photo_media_ids),
        meal.total_calories,
    )
    return format_range_reply(meal)


async def handle_clarification_reply(user_id: str, wa_phone: str, text: str) -> str | None:
    """Webhook-facing entrypoint for a text message. Returns None if this user
    has no pending clarifying question (caller should treat the text as
    unhandled — this is not a general-purpose chat, only the completion path
    for calorie_vision.md's clarifying_question flow). Otherwise re-analyzes
    the original photo with the user's answer and logs the meal."""
    from app.db import queries
    from app.db.pool import get_pool
    from app.services import vision
    from app.whatsapp import media as media_client

    pool = await get_pool()
    pending = await queries.get_pending_clarification(pool, user_id)
    if pending is None:
        return None

    repo = queries.AsyncpgMealRepository(pool)
    image_bytes, _ = await media_client.download_media(pending["media_id"])
    result = await vision.analyze_photo(
        image_bytes, media_type=pending["media_type"], clarification=text
    )
    await queries.clear_pending_clarification(pool, user_id)

    if not result["foods"]:
        logger.info(
            "Clarified photo from %s still not recognized as food (media_id=%s)",
            _mask(wa_phone),
            pending["media_id"],
        )
        return NOT_FOOD_REPLY

    # Deliberately not re-triggering a second clarifying_question here, even
    # if the model still returns one — cap the back-and-forth at one round
    # trip and log the best-effort estimate rather than risk an unbounded
    # question loop.
    meal = await log_meal_photo(
        user_id, pending["media_id"], result, repo, model_id=settings.live_vision_model_id
    )
    logger.info(
        "Logged clarified meal for %s (meal_id=%s, total_calories=%.0f)",
        _mask(wa_phone),
        meal.id,
        meal.total_calories,
    )
    return format_range_reply(meal)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
