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


# ±10%, narrowed from the original ±20% at the user's explicit request
# (2026-07-24), after comparing a bot reply against an external nutrition
# reference that used a tighter band. Accepted trade-off, not free: a
# tighter range is more likely to miss the true value than ±20% was, given
# this app's own measured model MAE (13-30%+ across models/metrics — see
# specs/003-vision-model-comparison's real accuracy-comparison runs). Still
# a range, never a bare number, so Constitution I ("never false-precision")
# is not violated — only how conservative the range is has changed.
RANGE_FACTOR = 0.10


def _range_text(calories: float) -> str:
    """A zero-calorie item (e.g. a diet soda) is shown as a bare "0 kcal",
    not the redundant-looking "0-0 kcal" a literal range would produce —
    there is nothing uncertain about zero."""
    if calories <= 0:
        return "0 kcal"
    low = calories * (1 - RANGE_FACTOR)
    high = calories * (1 + RANGE_FACTOR)
    return f"~{low:.0f}-{high:.0f} kcal"


def _titlecase_food_name(name: str) -> str:
    return f"{name[:1].upper()}{name[1:]}" if name else name


def _food_lines(foods: list[dict]) -> list[str]:
    """One line per distinct food item with its own range — requested
    (2026-07-24) so a reply shows *how* a total was built, not just the
    total itself, matching how the user's external reference presented a
    calorie estimate (per-ingredient, not a single opaque number)."""
    return [
        f"{_titlecase_food_name(food['name'])}: {_range_text(food.get('calories', 0))}"
        for food in foods
    ]


def _meal_macros(meal: MealRecord) -> tuple[float, float, float]:
    protein = sum(food.get("protein_g", 0) for food in meal.foods)
    carbs = sum(food.get("carbs_g", 0) for food in meal.foods)
    fat = sum(food.get("fat_g", 0) for food in meal.foods)
    return protein, carbs, fat


def format_range_reply(meal: MealRecord) -> str:
    """Present the meal as a per-ingredient breakdown plus an overall range
    — never a false-precision exact number (FR-002, FR-003, FR-012).

    A single-food meal collapses to one line rather than showing the item
    and the Total on separate lines with the identical number — a
    coach-simulator pass found that redundant two-line form for the common
    single-food-photo case read as mechanical repetition, not chat copy."""
    protein, carbs, fat = _meal_macros(meal)
    if len(meal.foods) == 1:
        name = _titlecase_food_name(meal.foods[0]["name"])
        return (
            f"{name}: {_range_text(meal.total_calories)} "
            f"(protein ~{protein:.0f}g, carbs ~{carbs:.0f}g, fat ~{fat:.0f}g)."
        )
    lines = _food_lines(meal.foods)
    lines.append(
        f"Total: {_range_text(meal.total_calories)} "
        f"(protein ~{protein:.0f}g, carbs ~{carbs:.0f}g, fat ~{fat:.0f}g)."
    )
    return "\n".join(lines)


def format_item_and_meal_reply(item_result: dict, meal: MealRecord) -> str:
    """When a photo is appended to an already-open meal, one message tells
    the user this photo's own per-ingredient breakdown, what it added in
    total, and the meal's updated running total — never two separate
    messages for one photo. Requested after live testing: a photo that adds
    ~0 kcal to an existing meal (e.g. a diet soda) previously produced a
    reply identical to before it was sent, with no acknowledgment of that
    specific photo at all.

    A single-food photo collapses its item line and "Added:" line (same
    coach-simulator finding as format_range_reply) into one "X: ~Y kcal
    added." line, since they'd otherwise show the identical number twice."""
    item_foods = item_result["foods"]
    if len(item_foods) == 1:
        name = _titlecase_food_name(item_foods[0]["name"])
        lines = [f"{name}: {_range_text(item_result['total_calories'])} added."]
    else:
        lines = _food_lines(item_foods)
        lines.append(f"Added: {_range_text(item_result['total_calories'])}")
    protein, carbs, fat = _meal_macros(meal)
    lines.append(
        f"Meal total: {_range_text(meal.total_calories)} "
        f"(protein ~{protein:.0f}g, carbs ~{carbs:.0f}g, fat ~{fat:.0f}g)."
    )
    return "\n".join(lines)


def _reply_for_logged_meal(item_result: dict, meal: MealRecord) -> str:
    """One reply per photo, always — its shape depends on whether this photo
    started a new meal (`format_range_reply`) or was appended to an
    already-open one (`format_item_and_meal_reply`, showing this photo's own
    contribution inline with the updated running total). A meal's
    `photo_media_ids` has exactly 1 entry after `create_meal` and 2+ after
    any `append_to_meal` — a reliable, already-available signal for which
    case this is, with no extra DB read needed."""
    if len(meal.photo_media_ids) > 1:
        return format_item_and_meal_reply(item_result, meal)
    return format_range_reply(meal)


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
    return _reply_for_logged_meal(result, meal)


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
    return _reply_for_logged_meal(result, meal)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
