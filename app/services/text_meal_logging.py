from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def handle_text_meal_description(user_id: str, wa_phone: str, text: str) -> str | None:
    """Webhook-facing entrypoint for `webhook.py`'s text dispatch chain
    (specs/005-text-meal-logging, contracts/text-dispatch-precedence.md).

    Returns `None` if this text should be handled by a later dispatch layer
    instead — either it's safety-relevant (deferred entirely to
    `chat_fallback.py`'s own, unchanged safety-first check, per FR-008) or
    it isn't a food-logging attempt at all. Otherwise returns the reply to
    send: a clarifying question, or a calorie-range meal-logged reply."""
    from app.db import queries
    from app.db.pool import get_pool
    from app.services import meal_logging, safety, text_analysis

    if safety.check_safety_signal(text) is not None:
        # Never even call the estimation model on safety-flagged text — the
        # existing safety escalation (chat_fallback.py) must be the only
        # thing that responds to it (FR-008, research.md #2).
        return None

    result = await text_analysis.analyze_text(text)
    if not result.get("is_food_description"):
        return None

    pool = await get_pool()

    clarifying_question = result.get("clarifying_question")
    if clarifying_question:
        # Per calorie_text.md rule 5: only fires when a quantity is genuinely
        # missing and materially affects the estimate — most food
        # descriptions with stated amounts reach the logging path below.
        await queries.set_pending_clarification(
            pool, user_id, "text", clarifying_question, text_body=text
        )
        logger.info("Text meal description from %s needs clarification", _mask(wa_phone))
        return clarifying_question

    repo = queries.AsyncpgMealRepository(pool)
    meal = await meal_logging.log_meal_contribution(
        user_id, result, repo, model_id=settings.live_vision_model_id, text_entry=text
    )
    logger.info(
        "Logged text-described meal for %s (meal_id=%s, total_calories=%.0f)",
        _mask(wa_phone),
        meal.id,
        meal.total_calories,
    )
    return meal_logging.reply_for_logged_meal(result, meal)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
