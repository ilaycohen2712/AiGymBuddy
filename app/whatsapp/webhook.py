import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_ERROR_REPLY = (
    "Sorry, I couldn't process that photo just now — could you try sending it again?"
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
    the meal-logging feature (see app/services/meal_logging.py).

    Every image message is: deduped by wa_message_id (Meta redelivers webhooks
    on timeout/non-2xx, and this handler is slow enough that redelivery is a
    real risk, not theoretical), processed with a graceful fallback reply on
    any failure (a bad photo or a Claude/DB hiccup must never leave the user
    with silence), and recorded in `messages` once handled so a retry is a
    no-op.
    """
    from app.db import queries
    from app.db.pool import get_pool
    from app.services import meal_logging
    from app.whatsapp import send

    pool = await get_pool()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                await _handle_message(pool, message, meal_logging, send, queries)


async def _handle_message(pool, message: dict, meal_logging, send, queries) -> None:
    if message.get("type") != "image":
        logger.info("Ignoring non-image message type=%s", message.get("type"))
        return

    message_id = message.get("id")
    wa_id = message.get("from")
    media_id = (message.get("image") or {}).get("id")
    if not message_id or not wa_id or not media_id:
        logger.warning("Malformed image message payload, skipping")
        return

    user_id = await queries.get_or_create_user_id(pool, wa_id)

    if await queries.is_message_processed(pool, message_id):
        logger.info("Duplicate webhook delivery for message_id=%s, skipping", message_id)
        return

    # Best-effort only: mark_as_read is a UX nicety (closest stand-in for a
    # typing indicator), not core functionality. It must never be able to
    # block the actual photo-processing pipeline below — verified live: a
    # failing mark_as_read call previously short-circuited the whole handler
    # before meal_logging ever ran, silently dropping the user's photo.
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

    try:
        await send.send_text_message(wa_id, reply_text)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to send reply (status=%s) for message_id=%s",
            exc.response.status_code,
            message_id,
        )
        return  # don't mark as processed if we couldn't reply — allow a retry
    except Exception:
        logger.exception("Failed to send reply for message_id=%s", message_id)
        return

    await queries.record_message(pool, user_id, message_id, direction="in", kind="image")
