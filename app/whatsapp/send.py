import httpx

from app.config import settings

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
MAX_TEXT_LENGTH = 4096


async def mark_as_read(message_id: str) -> None:
    # Note: the stable Cloud API has no separate "typing indicator" endpoint;
    # marking the inbound message read is the closest available signal to the
    # user while analysis is in progress.
    url = f"{GRAPH_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()


async def send_template_message(to: str, template_name: str, language_code: str = "en_US") -> dict:
    """Send a pre-approved template message — the only kind Meta allows once
    the 24h customer-service window has expired (whatsapp-api skill). The
    template itself must already be registered and approved in Meta Business
    Manager; this only sends it by name. See app/whatsapp/templates.py for
    the fallback logic that decides when to call this."""
    url = f"{GRAPH_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template_name, "language": {"code": language_code}},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_text_message(to: str, body: str) -> dict:
    # Raises httpx.HTTPStatusError on a 131047 (24h window expired) same as
    # any other upstream error — this function never falls back on its own.
    # Callers making a proactive push (not a reply to an inbound message —
    # currently only the end-of-day report/target ask, User Story 3) should
    # go through app/whatsapp/templates.py::send_proactive_message instead,
    # which catches exactly that error and falls back to a template send.
    if len(body) > MAX_TEXT_LENGTH:
        body = body[: MAX_TEXT_LENGTH - 1]

    url = f"{GRAPH_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
