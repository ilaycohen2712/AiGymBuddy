from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Spec cites two commonly-referenced floors ("1200/1500 kcal") without a rule
# for which applies to which individual, and this MVP doesn't reliably
# collect the user's sex needed to differentiate between them (users.sex is
# nullable and nothing in the current flow ever sets it) — so a single, more
# conservative floor is used uniformly. Safety first (Constitution III): err
# toward caution rather than risk storing a target that's unsafe for a given
# individual just because it clears the lower of the two cited numbers.
SAFETY_FLOOR_KCAL = 1500

TARGET_ASK = (
    "One more thing — what's your daily calorie target? Send me a number and "
    "I'll use it to personalize your daily reports."
)

_BELOW_FLOOR_REPLY = (
    f"That's below the safe minimum of {SAFETY_FLOOR_KCAL} kcal/day, so I can't "
    "set it that low — what's a daily calorie target at or above that?"
)

_UNPARSEABLE_REPLY = (
    "I didn't catch a number there — what's your daily calorie target? "
    '(e.g. "2000")'
)

_CONFIRMATION_TEMPLATE = "Got it — {target} kcal/day, saved for your daily reports."


def _parse_calorie_target(text: str) -> int | None:
    """Extract a plausible calorie number from free text (e.g. "2000", "2,000
    kcal", "around 2000"). Not a generative step — a simple digit extraction
    (contracts/daily-target-collection.md). Returns None if no number is
    found at all."""
    match = re.search(r"\d[\d,]*", text)
    if not match:
        return None
    return int(match.group().replace(",", ""))


async def send_target_ask(user_id: str, wa_phone: str) -> str:
    """Composes the target-collection ask and records that it was asked today
    (contracts/daily-target-collection.md) — called by the scheduler in
    place of the end-of-day report when no target is on file yet (FR-007).
    This is a proactive push (FR-009: must be answerable — it's a direct
    question) rather than a reply to an inbound message."""
    from app.db import queries
    from app.db.pool import get_pool

    pool = await get_pool()
    await queries.set_pending_daily_target_ask(pool, user_id)
    logger.info("Asked %s for daily calorie target", _mask(wa_phone))
    return TARGET_ASK


async def handle_daily_target_reply(user_id: str, wa_phone: str, text: str) -> str | None:
    """Webhook-facing entrypoint for a text message. Returns None if this
    user has no pending daily-target ask outstanding — the caller should
    treat the text as unhandled and fall through to the next handler in the
    dispatch chain (same shape as meal_logging.handle_clarification_reply).
    Otherwise parses the numeric reply, enforcing the safety floor (FR-015)
    and re-asking on anything that doesn't clear it."""
    from app.db import queries
    from app.db.pool import get_pool

    pool = await get_pool()
    pending = await queries.get_pending_daily_target_ask(pool, user_id)
    if pending is None:
        return None

    target = _parse_calorie_target(text)
    if target is None:
        return _UNPARSEABLE_REPLY
    if target < SAFETY_FLOOR_KCAL:
        logger.info("Rejected below-floor daily calorie target from %s", _mask(wa_phone))
        return _BELOW_FLOOR_REPLY

    await queries.set_daily_calorie_target(pool, user_id, target)
    await queries.clear_pending_daily_target_ask(pool, user_id)
    logger.info("Stored daily calorie target for %s: %d kcal", _mask(wa_phone), target)
    return _CONFIRMATION_TEMPLATE.format(target=target)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
