import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Verify X-Hub-Signature-256: HMAC-SHA256 of the raw body with the App Secret."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


@router.get("/webhook")
async def verify_webhook(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
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
    the meal-logging feature (see app/services/meal_logging.py)."""
    from app.services import meal_logging
    from app.whatsapp import send

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") == "image":
                    wa_id = message["from"]
                    media_id = message["image"]["id"]
                    await send.mark_as_read(message["id"])
                    reply_text = await meal_logging.handle_incoming_photo(wa_id, media_id)
                    await send.send_text_message(wa_id, reply_text)
                else:
                    logger.info("Ignoring non-image message type=%s", message.get("type"))
