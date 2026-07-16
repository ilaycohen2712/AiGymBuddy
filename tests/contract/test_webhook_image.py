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


def _stub_db(monkeypatch, *, already_processed: bool = False):
    """Stub out the DB layer used by webhook dispatch (pool + queries), so
    these contract tests never touch a real Postgres instance."""
    from app.db import pool as pool_module
    from app.db import queries

    calls: dict = {"recorded": None}

    async def fake_get_pool():
        return object()

    async def fake_get_or_create_user_id(pool, wa_phone):
        return f"user-for-{wa_phone}"

    async def fake_is_message_processed(pool, wa_message_id):
        return already_processed

    async def fake_record_message(pool, user_id, wa_message_id, direction, kind, body=None):
        calls["recorded"] = (user_id, wa_message_id, direction, kind)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_or_create_user_id", fake_get_or_create_user_id)
    monkeypatch.setattr(queries, "is_message_processed", fake_is_message_processed)
    monkeypatch.setattr(queries, "record_message", fake_record_message)
    return calls


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


def test_get_verification_handshake_rejects_when_token_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "")
    client = TestClient(app)

    resp = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "12345"},
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


def test_post_webhook_rejects_when_secret_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    client = TestClient(app)
    body = json.dumps(_image_payload()).encode()
    # Signature computed with an empty key — must still be rejected rather
    # than trivially "matching" an empty configured secret.
    digest = hmac.new(b"", body, hashlib.sha256).hexdigest()

    resp = client.post(
        "/webhook", content=body, headers={"X-Hub-Signature-256": f"sha256={digest}"}
    )

    assert resp.status_code == 403


def test_post_webhook_image_message_replies_with_range(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.services import meal_logging
    from app.whatsapp import send

    handled = {}

    async def fake_handle_incoming_photo(user_id, wa_id, media_id):
        handled["args"] = (user_id, wa_id, media_id)
        return "That's about 400-600 kcal (protein ~30g, carbs ~50g, fat ~15g)."

    async def fake_mark_as_read(message_id):
        handled["marked_read"] = message_id

    async def fake_send_text_message(to, body):
        handled["sent"] = (to, body)
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(meal_logging, "handle_incoming_photo", fake_handle_incoming_photo)
    monkeypatch.setattr(send, "mark_as_read", fake_mark_as_read)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    payload = _image_payload(wa_id="15551234567", media_id="media-42", message_id="wamid.99")
    body = json.dumps(payload).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert handled["args"] == ("user-for-15551234567", "15551234567", "media-42")
    assert handled["marked_read"] == "wamid.99"
    assert handled["sent"][0] == "15551234567"
    assert "kcal" in handled["sent"][1]
    assert calls["recorded"] == ("user-for-15551234567", "wamid.99", "in", "image")


def test_post_webhook_duplicate_message_id_skips_reprocessing(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    _stub_db(monkeypatch, already_processed=True)

    from app.services import meal_logging
    from app.whatsapp import send

    handled = {"called": False}

    async def fake_handle_incoming_photo(user_id, wa_id, media_id):
        handled["called"] = True
        return "should not be reached"

    async def fake_mark_as_read(message_id):
        handled["called"] = True

    monkeypatch.setattr(meal_logging, "handle_incoming_photo", fake_handle_incoming_photo)
    monkeypatch.setattr(send, "mark_as_read", fake_mark_as_read)

    client = TestClient(app)
    body = json.dumps(_image_payload(message_id="wamid.duplicate")).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert handled["called"] is False


def test_post_webhook_falls_back_gracefully_when_processing_fails(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    _stub_db(monkeypatch)

    from app.services import meal_logging
    from app.whatsapp import send

    sent = {}

    async def fake_handle_incoming_photo(user_id, wa_id, media_id):
        raise ValueError("vision pipeline exploded")

    async def fake_mark_as_read(message_id):
        return None

    async def fake_send_text_message(to, body):
        sent["args"] = (to, body)
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(meal_logging, "handle_incoming_photo", fake_handle_incoming_photo)
    monkeypatch.setattr(send, "mark_as_read", fake_mark_as_read)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    body = json.dumps(_image_payload(message_id="wamid.error")).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert "try" in sent["args"][1].lower() or "sorry" in sent["args"][1].lower()
