from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.whatsapp import send

logger = logging.getLogger(__name__)

# Meta error code for "the 24h customer-service window is closed" — the only
# case this module exists to handle (whatsapp-api skill). Every other httpx
# error propagates unchanged; this is not a general retry/fallback layer.
WINDOW_EXPIRED_ERROR_CODE = 131047


async def send_proactive_message(to: str, body: str) -> None:
    """Send a bot-initiated message that isn't a reply to an inbound message
    — used by the end-of-day report and daily-target ask (specs/001-photo-
    calorie-tracking, User Story 3), the first proactive pushes in this bot
    that aren't guaranteed to land inside the 24h window an inbound message
    would have just reopened. Falls back to the configured pre-approved
    template on a 131047 (window expired) error; any other failure
    propagates unchanged, same as a direct send.text_message call."""
    try:
        await send.send_text_message(to, body)
    except httpx.HTTPStatusError as exc:
        if not _is_window_expired(exc):
            raise
        logger.warning("24h window expired for a proactive send, falling back to template")
        await _send_template_fallback(to)


def _is_window_expired(exc: httpx.HTTPStatusError) -> bool:
    try:
        error = exc.response.json().get("error", {})
    except ValueError:
        return False
    return error.get("code") == WINDOW_EXPIRED_ERROR_CODE


async def _send_template_fallback(to: str) -> None:
    # settings.eod_template_name is empty until a template is registered and
    # approved in Meta Business Manager — an operational step outside this
    # codebase (whatsapp-api skill: "must be registered in Meta Business
    # Manager first"). Until then this can only log the gap, not recover the
    # send — there is no content to send that Meta would accept.
    if not settings.eod_template_name:
        logger.error(
            "No approved WhatsApp template configured (settings.eod_template_name) — "
            "a proactive message outside the 24h window could not be delivered"
        )
        return
    await send.send_template_message(to, settings.eod_template_name)
