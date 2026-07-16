import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


def _sign(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _image_payload(
    wa_id: str = "15551234567", media_id: str = "media-1", message_id: str = "wamid.1"
) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": wa_id,
                                    "type": "image",
                                    "image": {"id": media_id},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_get_verification_handshake_echoes_challenge(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", VERIFY_TOKEN)
    client = TestClient(app)

    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )

    assert resp.status_code == 200
    assert resp.text == "12345"


def test_get_verification_handshake_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", VERIFY_TOKEN)
    client = TestClient(app)

    resp = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
    )

    assert resp.status_code == 403


def test_post_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    client = TestClient(app)
    body = json.dumps(_image_payload()).encode()

    resp = client.post(
        "/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=invalid"}
    )

    assert resp.status_code == 403


def test_post_webhook_image_message_replies_with_range(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)

    from app.services import meal_logging
    from app.whatsapp import send

    calls = {}

    async def fake_handle_incoming_photo(wa_id, media_id):
        calls["handled"] = (wa_id, media_id)
        return "That's about 400-600 kcal (protein ~30g, carbs ~50g, fat ~15g)."

    async def fake_mark_as_read(message_id):
        calls["marked_read"] = message_id

    async def fake_send_text_message(to, body):
        calls["sent"] = (to, body)
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(meal_logging, "handle_incoming_photo", fake_handle_incoming_photo)
    monkeypatch.setattr(send, "mark_as_read", fake_mark_as_read)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    payload = _image_payload(wa_id="15551234567", media_id="media-42", message_id="wamid.99")
    body = json.dumps(payload).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert calls["handled"] == ("15551234567", "media-42")
    assert calls["marked_read"] == "wamid.99"
    assert calls["sent"][0] == "15551234567"
    assert "kcal" in calls["sent"][1]
