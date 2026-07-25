import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_ERROR_REPLY = (
    "Sorry, I couldn't process that just now — could you try again?"
)


def verify_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Verify X-Hub-Signature-256: HMAC-SHA256 of the raw body with the App Secret.

    An empty/unset app_secret always rejects rather than silently computing a
    valid HMAC with an empty key, which would make signature verification
    trivially forgeable against a misconfigured deployment.
    """
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


@router.get("/webhook")
async def verify_webhook(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token") or ""
    challenge = request.query_params.get("hub.challenge")

    configured_token = settings.whatsapp_verify_token
    token_matches = bool(configured_token) and hmac.compare_digest(token, configured_token)

    if mode == "subscribe" and token_matches:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(settings.whatsapp_app_secret, raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    await _dispatch_messages(payload)
    return {"status": "received"}


async def _dispatch_messages(payload: dict) -> None:
    """Route inbound messages to their handlers. Image handling is wired in by
    the meal-logging feature; text handling completes an outstanding
    clarifying question (app/services/meal_logging.py), a pending daily-
    target ask (app/services/daily_target.py), a typed food description to
    log as a meal (app/services/text_meal_logging.py), or a recognized
    total-request (app/services/daily_total.py) — this is not a
    general-purpose chat.

    Every message is: claimed atomically by wa_message_id *before* any
    expensive work starts (Meta redelivers webhooks on timeout/non-2xx, and
    this handler is slow enough — real Claude API calls — that redelivery is
    a real risk, not theoretical; queries.claim_message closes the race
    window a check-then-record-at-the-end pattern would leave open), and
    processed with a graceful fallback reply on any failure (a bad photo/
    reply or a Claude/DB hiccup must never leave the user with silence).
    """
    from app.db import queries
    from app.db.pool import get_pool
    from app.services import chat_fallback, daily_target, meal_logging, text_meal_logging
    from app.services import timezone as timezone_service
    from app.whatsapp import send

    pool = await get_pool()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                msg_type = message.get("type")
                if msg_type == "image":
                    await _handle_image_message(pool, message, meal_logging, send, queries)
                elif msg_type == "text":
                    await _handle_text_message(
                        pool,
                        message,
                        meal_logging,
                        daily_target,
                        text_meal_logging,
                        chat_fallback,
                        timezone_service,
                        send,
                        queries,
                    )
                elif msg_type == "location":
                    await _handle_location_message(
                        pool, message, timezone_service, send, queries
                    )
                else:
                    await _handle_unsupported_message(
                        pool, message, msg_type, chat_fallback, send, queries
                    )


async def _handle_image_message(pool, message: dict, meal_logging, send, queries) -> None:
    message_id = message.get("id")
    wa_id = message.get("from")
    media_id = (message.get("image") or {}).get("id")
    if not message_id or not wa_id or not media_id:
        logger.warning("Malformed image message payload, skipping")
        return

    user_id = await queries.get_or_create_user_id(pool, wa_id)
    if not await queries.claim_message(pool, user_id, message_id, kind="image"):
        logger.info("Duplicate webhook delivery for message_id=%s, skipping", message_id)
        return

    await _best_effort_mark_as_read(send, message_id)

    try:
        reply_text = await meal_logging.handle_incoming_photo(user_id, wa_id, media_id)
    except httpx.HTTPStatusError as exc:
        # Deliberately not logging exc's default string form: for media
        # downloads it embeds a signed, time-limited CDN URL, which would leak
        # into logs otherwise.
        logger.error(
            "Upstream API error (status=%s) handling message_id=%s",
            exc.response.status_code,
            message_id,
        )
        reply_text = FALLBACK_ERROR_REPLY
    except Exception:
        logger.exception("Failed to handle image message (message_id=%s)", message_id)
        reply_text = FALLBACK_ERROR_REPLY

    await _send_reply(send, wa_id, message_id, reply_text)


async def _handle_text_message(
    pool,
    message: dict,
    meal_logging,
    daily_target,
    text_meal_logging,
    chat_fallback,
    timezone_service,
    send,
    queries,
) -> None:
    message_id = message.get("id")
    wa_id = message.get("from")
    text_body = (message.get("text") or {}).get("body")
    if not message_id or not wa_id or not text_body:
        logger.warning("Malformed text message payload, skipping")
        return

    user_id = await queries.get_or_create_user_id(pool, wa_id)
    if not await queries.claim_message(pool, user_id, message_id, kind="text"):
        logger.info("Duplicate webhook delivery for message_id=%s, skipping", message_id)
        return

    try:
        reply_text = await meal_logging.handle_clarification_reply(user_id, wa_id, text_body)
        if reply_text is None:
            # Not completing a pending clarification (FR-002: that flow
            # still takes priority, unaffected, and this branch is never
            # reached while one is pending). Next: a pending daily-target
            # ask (specs/001-photo-calorie-tracking User Story 3,
            # contracts/daily-target-collection.md) — added as a new layer
            # after clarification, same shape as chat_fallback's own
            # addition below, so neither disturbs the other's behavior.
            reply_text = await daily_target.handle_daily_target_reply(user_id, wa_id, text_body)
        if reply_text is None:
            # Not a pending daily-target ask either. Next: is this a
            # food-description message to log as a meal (specs/005-text-
            # meal-logging, contracts/text-dispatch-precedence.md)? Returns
            # None if the text is safety-relevant or isn't about food at
            # all, deferring to chat_fallback below in either case.
            reply_text = await text_meal_logging.handle_text_meal_description(
                user_id, wa_id, text_body
            )
        if reply_text is None:
            # Not a pending structured flow at all. Every other free-form
            # text now always gets a reply — a safety escalation, a
            # recognized supported-question answer, or the fixed fallback
            # (spec 004-chat-responsiveness, FR-001/FR-009) — never silence.
            reply_text = await chat_fallback.handle_free_form_text(user_id, wa_id, text_body)
            # Independently of what chat_fallback answered, check for a
            # place mention that should update the user's stored time zone
            # (spec 002-daily-total-tracking User Story 4, FR-012). A
            # clarification answer or a daily-target reply (the branches
            # above) are deliberately excluded — each is descriptive/
            # structured data about something specific, not a general
            # message about where the user is.
            await _maybe_update_timezone_from_text(
                pool, queries, timezone_service, user_id, wa_id, text_body
            )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Upstream API error (status=%s) handling message_id=%s",
            exc.response.status_code,
            message_id,
        )
        reply_text = FALLBACK_ERROR_REPLY
    except Exception:
        logger.exception("Failed to handle text message (message_id=%s)", message_id)
        reply_text = FALLBACK_ERROR_REPLY

    await _send_reply(send, wa_id, message_id, reply_text)


async def _maybe_update_timezone_from_text(
    pool, queries, timezone_service, user_id: str, wa_id: str, text: str
) -> None:
    # Best-effort only, like _best_effort_mark_as_read: a failure here (e.g.
    # an upstream Claude error) must never turn an otherwise-successful
    # total-request reply into a failure — this is a side effect, not the
    # message's primary content.
    try:
        time_zone = await timezone_service.extract_timezone_from_text(text)
    except Exception:
        logger.warning("Time zone extraction failed, leaving stored value unchanged")
        return

    if time_zone is not None:
        await queries.update_user_time_zone(pool, user_id, time_zone)
        logger.info(
            "Updated time zone for %s to %s via text mention", _mask(wa_id), time_zone
        )


async def _handle_location_message(pool, message: dict, timezone_service, send, queries) -> None:
    message_id = message.get("id")
    wa_id = message.get("from")
    location = message.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if not message_id or not wa_id or latitude is None or longitude is None:
        logger.warning("Malformed location message payload, skipping")
        return

    user_id = await queries.get_or_create_user_id(pool, wa_id)
    if not await queries.claim_message(pool, user_id, message_id, kind="location"):
        logger.info("Duplicate webhook delivery for message_id=%s, skipping", message_id)
        return

    try:
        time_zone = timezone_service.timezone_from_location(latitude, longitude)
        if time_zone is not None:
            await queries.update_user_time_zone(pool, user_id, time_zone)
            logger.info(
                "Updated time zone for %s to %s via location share", _mask(wa_id), time_zone
            )
            reply_text = "Got it — updated your time zone based on your location."
        else:
            reply_text = (
                "I couldn't figure out a time zone from that location — "
                "could you try sharing it again?"
            )
    except Exception:
        logger.exception("Failed to handle location message (message_id=%s)", message_id)
        reply_text = FALLBACK_ERROR_REPLY

    await _send_reply(send, wa_id, message_id, reply_text)


async def _handle_unsupported_message(
    pool, message: dict, msg_type: str, chat_fallback, send, queries
) -> None:
    """Any inbound message type this bot has no dedicated handler for
    (voice note, sticker, document, video, etc.) — spec 004-chat-
    responsiveness, User Story 2. The reply is fixed regardless of
    `msg_type` (research.md #5), so unlike the other handlers this never
    inspects the message body itself beyond the envelope fields every
    WhatsApp message type shares."""
    message_id = message.get("id")
    wa_id = message.get("from")
    if not message_id or not wa_id:
        logger.warning("Malformed message payload (type=%s), skipping", msg_type)
        return

    user_id = await queries.get_or_create_user_id(pool, wa_id)
    if not await queries.claim_message(pool, user_id, message_id, kind="other"):
        logger.info("Duplicate webhook delivery for message_id=%s, skipping", message_id)
        return

    try:
        reply_text = chat_fallback.acknowledge_unsupported_type()
    except Exception:
        logger.exception("Failed to handle unsupported message (message_id=%s)", message_id)
        reply_text = FALLBACK_ERROR_REPLY

    await _send_reply(send, wa_id, message_id, reply_text)


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"


async def _best_effort_mark_as_read(send, message_id: str) -> None:
    # Best-effort only: mark_as_read is a UX nicety (closest stand-in for a
    # typing indicator), not core functionality. It must never be able to
    # block the actual processing pipeline — verified live: a failing
    # mark_as_read call previously short-circuited the whole handler before
    # meal_logging ever ran, silently dropping the user's photo.
    try:
        await send.mark_as_read(message_id)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "mark_as_read failed (status=%s) for message_id=%s, continuing anyway",
            exc.response.status_code,
            message_id,
        )
    except Exception:
        logger.warning("mark_as_read failed for message_id=%s, continuing anyway", message_id)


async def _send_reply(send, wa_id: str, message_id: str, reply_text: str) -> None:
    """The inbound message is already claimed (queries.claim_message, at the
    top of every handler) before this runs, so there's nothing left to
    record here — sending is the only remaining step. A failure to send
    doesn't un-claim the message: see claim_message's docstring for the
    accepted trade-off (no automatic Meta-retry recovery from a transient
    failure, in exchange for closing the duplicate-processing race)."""
    try:
        await send.send_text_message(wa_id, reply_text)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to send reply (status=%s) for message_id=%s",
            exc.response.status_code,
            message_id,
        )
    except Exception:
        logger.exception("Failed to send reply for message_id=%s", message_id)
