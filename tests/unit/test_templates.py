import httpx
import pytest

from app.config import settings
from app.whatsapp import send, templates


def _window_expired_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://graph.facebook.com/x")
    response = httpx.Response(
        400, request=request, json={"error": {"code": 131047, "message": "window expired"}}
    )
    return httpx.HTTPStatusError("window expired", request=request, response=response)


def _other_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://graph.facebook.com/x")
    response = httpx.Response(500, request=request, json={"error": {"code": 1, "message": "oops"}})
    return httpx.HTTPStatusError("server error", request=request, response=response)


@pytest.mark.asyncio
async def test_send_proactive_message_sends_plain_text_when_window_open(monkeypatch):
    sent = {}

    async def fake_send_text_message(to, body):
        sent["args"] = (to, body)
        return {"messages": [{"id": "wamid.reply"}]}

    monkeypatch.setattr(send, "send_text_message", fake_send_text_message)

    await templates.send_proactive_message("15551234567", "hello")

    assert sent["args"] == ("15551234567", "hello")


@pytest.mark.asyncio
async def test_send_proactive_message_falls_back_to_template_on_window_expired(monkeypatch):
    async def failing_send_text_message(to, body):
        raise _window_expired_error()

    fallback_called = {}

    async def fake_send_template_message(to, template_name, language_code="en_US"):
        fallback_called["args"] = (to, template_name)
        return {"messages": [{"id": "wamid.template"}]}

    monkeypatch.setattr(settings, "eod_template_name", "eod_report_v1")
    monkeypatch.setattr(send, "send_text_message", failing_send_text_message)
    monkeypatch.setattr(send, "send_template_message", fake_send_template_message)

    await templates.send_proactive_message("15551234567", "hello")

    assert fallback_called["args"] == ("15551234567", "eod_report_v1")


@pytest.mark.asyncio
async def test_send_proactive_message_logs_and_does_not_raise_without_configured_template(
    monkeypatch,
):
    async def failing_send_text_message(to, body):
        raise _window_expired_error()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("must not attempt a template send with no template configured")

    monkeypatch.setattr(settings, "eod_template_name", "")
    monkeypatch.setattr(send, "send_text_message", failing_send_text_message)
    monkeypatch.setattr(send, "send_template_message", fail_if_called)

    await templates.send_proactive_message("15551234567", "hello")  # must not raise


@pytest.mark.asyncio
async def test_send_proactive_message_propagates_non_window_errors(monkeypatch):
    async def failing_send_text_message(to, body):
        raise _other_error()

    monkeypatch.setattr(send, "send_text_message", failing_send_text_message)

    with pytest.raises(httpx.HTTPStatusError):
        await templates.send_proactive_message("15551234567", "hello")
