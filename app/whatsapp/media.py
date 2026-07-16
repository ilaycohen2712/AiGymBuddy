import httpx

from app.config import settings

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


async def download_media(media_id: str) -> bytes:
    """Fetch a WhatsApp media file: GET /{media-id} for a download URL
    (valid 5 min), then download it."""
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    async with httpx.AsyncClient() as client:
        meta_resp = await client.get(f"{GRAPH_API_BASE}/{media_id}", headers=headers)
        meta_resp.raise_for_status()
        download_url = meta_resp.json()["url"]

        file_resp = await client.get(download_url, headers=headers)
        file_resp.raise_for_status()
        return file_resp.content
