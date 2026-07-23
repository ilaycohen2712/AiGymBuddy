import hashlib
import hmac
import json

import httpx
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


def test_mark_as_read_failure_does_not_block_meal_logging(monkeypatch):
    """Regression test for a bug found via live verification: mark_as_read and
    handle_incoming_photo used to share one try block, so mark_as_read failing
    (e.g. a transient Meta hiccup) silently dropped the user's photo — the
    core feature never even ran."""
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    _stub_db(monkeypatch)

    from app.services import meal_logging
    from app.whatsapp import send

    handled = {"called": False}

    async def failing_mark_as_read(message_id):
        raise httpx.HTTPStatusError(
            "unauthorized",
            request=httpx.Request("POST", "https://graph.facebook.com/x"),
            response=httpx.Response(401, request=httpx.Request("POST", "https://x")),
        )

    async def fake_handle_incoming_photo(user_id, wa_id, media_id):
        handled["called"] = True
        return "That's about 400-600 kcal (protein ~30g, carbs ~50g, fat ~15g)."

    async def fake_send_text_message(to, body):
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(send, "mark_as_read", failing_mark_as_read)
    monkeypatch.setattr(meal_logging, "handle_incoming_photo", fake_handle_incoming_photo)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    body = json.dumps(_image_payload(message_id="wamid.markreadfails")).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert handled["called"] is True


def test_message_is_recorded_even_when_reply_send_fails_after_meal_logged(monkeypatch):
    """Regression test: if the meal was already logged successfully but sending
    the reply then fails (e.g. a timeout that also triggers a Meta redelivery),
    the message must still be recorded as processed. Otherwise a retry would
    re-run vision + the DB write and log the same photo a second time."""
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.services import meal_logging
    from app.whatsapp import send

    async def fake_handle_incoming_photo(user_id, wa_id, media_id):
        return "That's about 400-600 kcal (protein ~30g, carbs ~50g, fat ~15g)."

    async def fake_mark_as_read(message_id):
        return None

    async def failing_send_text_message(to, body):
        raise httpx.HTTPStatusError(
            "server error",
            request=httpx.Request("POST", "https://graph.facebook.com/x"),
            response=httpx.Response(500, request=httpx.Request("POST", "https://x")),
        )

    monkeypatch.setattr(meal_logging, "handle_incoming_photo", fake_handle_incoming_photo)
    monkeypatch.setattr(send, "mark_as_read", fake_mark_as_read)
    monkeypatch.setattr(send, "send_text_message", failing_send_text_message)

    client = TestClient(app)
    body = json.dumps(_image_payload(message_id="wamid.sendfails")).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert calls["recorded"] == ("user-for-15551234567", "wamid.sendfails", "in", "image")


def test_message_is_not_recorded_when_photo_handling_fails_and_send_fails(monkeypatch):
    """Complement to the above: if nothing was persisted (handle_incoming_photo
    itself failed), and the fallback reply also fails to send, a retry should
    still be allowed — there's no duplicate-write risk since no meal exists yet."""
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.services import meal_logging
    from app.whatsapp import send

    async def failing_handle_incoming_photo(user_id, wa_id, media_id):
        raise ValueError("vision pipeline exploded")

    async def fake_mark_as_read(message_id):
        return None

    async def failing_send_text_message(to, body):
        raise httpx.HTTPStatusError(
            "server error",
            request=httpx.Request("POST", "https://graph.facebook.com/x"),
            response=httpx.Response(500, request=httpx.Request("POST", "https://x")),
        )

    monkeypatch.setattr(meal_logging, "handle_incoming_photo", failing_handle_incoming_photo)
    monkeypatch.setattr(send, "mark_as_read", fake_mark_as_read)
    monkeypatch.setattr(send, "send_text_message", failing_send_text_message)

    client = TestClient(app)
    body = json.dumps(_image_payload(message_id="wamid.bothfail")).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert calls["recorded"] is None


def _text_payload(
    wa_id: str = "15551234567", body_text: str = "hi", message_id: str = "wamid.text1"
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
                                    "type": "text",
                                    "text": {"body": body_text},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_text_reply_completes_pending_clarification(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.services import meal_logging

    captured = {}

    async def fake_handle_clarification_reply(user_id, wa_id, text):
        captured["args"] = (user_id, wa_id, text)
        return "That's about 176-264 kcal (protein ~6g, carbs ~24g, fat ~6g)."

    monkeypatch.setattr(meal_logging, "handle_clarification_reply", fake_handle_clarification_reply)

    client = TestClient(app)
    body = json.dumps(
        _text_payload(wa_id="15551234567", body_text="It's vegetable", message_id="wamid.clarify1")
    ).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert captured["args"] == ("user-for-15551234567", "15551234567", "It's vegetable")
    assert calls["recorded"] == ("user-for-15551234567", "wamid.clarify1", "in", "text")


def test_text_message_ignored_when_nothing_pending(monkeypatch):
    """This bot isn't a general chat — a text message with no outstanding
    clarifying question must be silently ignored, no reply sent."""
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.services import meal_logging
    from app.whatsapp import send

    sent = {"called": False}

    async def fake_handle_clarification_reply(user_id, wa_id, text):
        return None

    async def fake_send_text_message(to, body):
        sent["called"] = True
        return {"messages": [{"id": "wamid.reply"}]}

    async def fake_extract_timezone_from_text(text):
        return None

    from app.services import timezone as timezone_service

    monkeypatch.setattr(meal_logging, "handle_clarification_reply", fake_handle_clarification_reply)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)
    monkeypatch.setattr(
        timezone_service, "extract_timezone_from_text", fake_extract_timezone_from_text
    )

    client = TestClient(app)
    body = json.dumps(
        _text_payload(body_text="random chit chat", message_id="wamid.random1")
    ).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert sent["called"] is False
    assert calls["recorded"] is None


def test_total_request_replies_with_range_from_daily_totals(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.db import queries
    from app.services import meal_logging

    async def fake_handle_clarification_reply(user_id, wa_id, text):
        return None

    async def fake_get_user_time_zone(pool, user_id):
        return "UTC"

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 900.0, "protein_g": 40.0, "carbs_g": 90.0, "fat_g": 20.0}

    sent = {}

    async def fake_send_text_message(to, body):
        sent["body"] = body
        return {"messages": [{"id": "wamid.reply"}]}

    async def fake_extract_timezone_from_text(text):
        return None

    from app.services import timezone as timezone_service
    from app.whatsapp import send

    monkeypatch.setattr(meal_logging, "handle_clarification_reply", fake_handle_clarification_reply)
    monkeypatch.setattr(queries, "get_user_time_zone", fake_get_user_time_zone)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(
        timezone_service, "extract_timezone_from_text", fake_extract_timezone_from_text
    )
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    body = json.dumps(
        _text_payload(body_text="what's my total today?", message_id="wamid.total1")
    ).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert "kcal" in sent["body"]
    assert "720" in sent["body"]  # 900 * 0.8
    assert "1080" in sent["body"]  # 900 * 1.2
    assert calls["recorded"] == ("user-for-15551234567", "wamid.total1", "in", "text")


def test_total_request_zero_meals_gets_friendly_reply(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    _stub_db(monkeypatch)

    from app.db import queries
    from app.services import meal_logging

    async def fake_handle_clarification_reply(user_id, wa_id, text):
        return None

    async def fake_get_user_time_zone(pool, user_id):
        return "UTC"

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    sent = {}

    async def fake_send_text_message(to, body):
        sent["body"] = body
        return {"messages": [{"id": "wamid.reply"}]}

    async def fake_extract_timezone_from_text(text):
        return None

    from app.services import timezone as timezone_service
    from app.whatsapp import send

    monkeypatch.setattr(meal_logging, "handle_clarification_reply", fake_handle_clarification_reply)
    monkeypatch.setattr(queries, "get_user_time_zone", fake_get_user_time_zone)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(
        timezone_service, "extract_timezone_from_text", fake_extract_timezone_from_text
    )
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    body = json.dumps(
        _text_payload(body_text="my total?", message_id="wamid.total2")
    ).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert "kcal" not in sent["body"]


def _location_payload(
    wa_id: str = "15551234567",
    latitude: float = 35.6895,
    longitude: float = 139.6917,
    message_id: str = "wamid.loc1",
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
                                    "type": "location",
                                    "location": {"latitude": latitude, "longitude": longitude},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_location_message_updates_time_zone_and_confirms(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.db import queries
    from app.whatsapp import send

    updated = {}

    async def fake_update_user_time_zone(pool, user_id, time_zone):
        updated["args"] = (user_id, time_zone)

    sent = {}

    async def fake_send_text_message(to, body):
        sent["body"] = body
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(queries, "update_user_time_zone", fake_update_user_time_zone)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)
    # Real timezonefinder call (Tokyo coordinates) — no need to mock, it's
    # offline/deterministic, per research.md #3.

    client = TestClient(app)
    body = json.dumps(_location_payload()).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert updated["args"] == ("user-for-15551234567", "Asia/Tokyo")
    assert "time zone" in sent["body"].lower()
    assert calls["recorded"] == ("user-for-15551234567", "wamid.loc1", "in", "location")


def test_location_message_unresolvable_coordinates_leaves_time_zone_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    _stub_db(monkeypatch)

    from app.db import queries
    from app.whatsapp import send

    called = {"update": False}

    async def fake_update_user_time_zone(pool, user_id, time_zone):
        called["update"] = True

    sent = {}

    async def fake_send_text_message(to, body):
        sent["body"] = body
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(queries, "update_user_time_zone", fake_update_user_time_zone)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    # Out-of-range latitude — a malformed payload, per timezone.py's ValueError handling.
    body = json.dumps(
        _location_payload(latitude=200.0, longitude=34.7818, message_id="wamid.loc2")
    ).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert called["update"] is False
    assert "couldn't" in sent["body"].lower()


def test_text_place_mention_updates_time_zone_silently(monkeypatch):
    """spec 002-daily-total-tracking, User Story 4, Acceptance Scenario 2: a
    place mentioned in ordinary text (not a location share, not a
    total-request) updates the stored time zone with no dedicated reply —
    it rides along silently."""
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET)
    calls = _stub_db(monkeypatch)

    from app.db import queries
    from app.services import meal_logging
    from app.services import timezone as timezone_service
    from app.whatsapp import send

    async def fake_handle_clarification_reply(user_id, wa_id, text):
        return None

    async def fake_extract_timezone_from_text(text):
        return "Asia/Tokyo"

    updated = {}

    async def fake_update_user_time_zone(pool, user_id, time_zone):
        updated["args"] = (user_id, time_zone)

    sent = {"called": False}

    async def fake_send_text_message(to, body):
        sent["called"] = True
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(meal_logging, "handle_clarification_reply", fake_handle_clarification_reply)
    monkeypatch.setattr(
        timezone_service, "extract_timezone_from_text", fake_extract_timezone_from_text
    )
    monkeypatch.setattr(queries, "update_user_time_zone", fake_update_user_time_zone)
    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    client = TestClient(app)
    body = json.dumps(
        _text_payload(body_text="just landed in Tokyo!", message_id="wamid.place1")
    ).encode()

    resp = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert resp.status_code == 200
    assert updated["args"] == ("user-for-15551234567", "Asia/Tokyo")
    assert sent["called"] is False
    assert calls["recorded"] is None
