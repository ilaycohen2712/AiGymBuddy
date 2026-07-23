from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Best-effort phrase/keyword recognition (Hebrew + English), not open-ended
# NLU — matches spec 002-daily-total-tracking's Assumptions. Substring match,
# case-insensitive (Hebrew has no case, so .lower() is a harmless no-op there).
_TOTAL_REQUEST_PHRASES = (
    "total",
    "so far today",
    "today so far",
    "how many calories",
    "how much have i eaten",
    "כמה אכלתי",
    "סך הכל",
    "כמה קלוריות",
    "מה הסך הכל",
)

NO_MEALS_YET_REPLY = "You haven't logged any meals yet today — send a photo whenever you eat."


def _is_daily_total_request(text: str) -> bool:
    lowered = text.strip().lower()
    return any(phrase in lowered for phrase in _TOTAL_REQUEST_PHRASES)


def format_daily_total_reply(totals: dict) -> str:
    """Present today's running total as a ±20% range, same convention as
    meal_logging.format_range_reply (FR-006 — never a false-precision exact
    number). A zero total (SC-004) gets a friendly fixed message instead of
    a literal "0-0 kcal" range."""
    calories = totals["calories"]
    if calories <= 0:
        return NO_MEALS_YET_REPLY
    return (
        f"So far today: about {calories * 0.8:.0f}-{calories * 1.2:.0f} kcal "
        f"(protein ~{totals['protein_g']:.0f}g, carbs ~{totals['carbs_g']:.0f}g, "
        f"fat ~{totals['fat_g']:.0f}g)."
    )


async def handle_daily_total_request(
    user_id: str, wa_phone: str, text: str, now: dt.datetime | None = None
) -> str | None:
    """Webhook-facing entrypoint for a text message asking for today's
    running total (spec 002-daily-total-tracking, User Story 1). Returns
    `None` if `text` doesn't match a recognized total-request phrase —
    without touching the DB at all — so the caller can treat it the same
    way as "no pending clarification" (not a general-purpose chat, FR-009).
    Otherwise sums every meal logged so far in the user's current local
    calendar day and replies with it.

    `now`: injectable for testing the midnight reset boundary (User Story
    3); defaults to the real current time in production."""
    if not _is_daily_total_request(text):
        return None

    now = now or dt.datetime.now(dt.UTC)
    from app.db import queries
    from app.db.pool import get_pool

    pool = await get_pool()
    time_zone = await queries.get_user_time_zone(pool, user_id)
    today = now.astimezone(ZoneInfo(time_zone)).date()
    totals = await queries.get_daily_total(pool, user_id, today)
    logger.info(
        "Daily total requested by %s: %.0f kcal so far today", _mask(wa_phone), totals["calories"]
    )
    return format_daily_total_reply(totals)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
