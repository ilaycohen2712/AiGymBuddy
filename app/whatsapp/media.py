import httpx

from app.config import settings

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Fetch a WhatsApp media file: GET /{media-id} for a download URL
    (valid 5 min) and its mime_type, then download the file itself.

    Returns (content_bytes, mime_type) — the mime_type must be passed through
    to the vision pipeline rather than assumed, since WhatsApp photos aren't
    guaranteed to be JPEG (can be PNG/WebP depending on the sending client).
    """
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    async with httpx.AsyncClient() as client:
        meta_resp = await client.get(f"{GRAPH_API_BASE}/{media_id}", headers=headers)
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        download_url = meta["url"]
        mime_type = meta.get("mime_type", "image/jpeg")

        file_resp = await client.get(download_url, headers=headers)
        file_resp.raise_for_status()
        return file_resp.content, mime_type
