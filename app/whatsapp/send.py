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


async def send_text_message(to: str, body: str) -> dict:
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
