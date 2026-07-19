import httpx
import pytest
import respx

from app.config import settings
from app.whatsapp import media

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


@pytest.mark.asyncio
async def test_download_media_returns_bytes_and_mime_type(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_access_token", "test-token")

    with respx.mock:
        respx.get(f"{GRAPH_API_BASE}/media-123").mock(
            return_value=httpx.Response(
                200, json={"url": "https://cdn.example.com/file", "mime_type": "image/png"}
            )
        )
        respx.get("https://cdn.example.com/file").mock(
            return_value=httpx.Response(200, content=b"fake-png-bytes")
        )

        content, mime_type = await media.download_media("media-123")

    assert content == b"fake-png-bytes"
    assert mime_type == "image/png"


@pytest.mark.asyncio
async def test_download_media_defaults_mime_type_when_missing(monkeypatch):
    """The Graph API metadata response is expected to include mime_type, but
    fall back to image/jpeg rather than crashing if it's ever absent."""
    monkeypatch.setattr(settings, "whatsapp_access_token", "test-token")

    with respx.mock:
        respx.get(f"{GRAPH_API_BASE}/media-456").mock(
            return_value=httpx.Response(200, json={"url": "https://cdn.example.com/file2"})
        )
        respx.get("https://cdn.example.com/file2").mock(
            return_value=httpx.Response(200, content=b"fake-bytes")
        )

        content, mime_type = await media.download_media("media-456")

    assert content == b"fake-bytes"
    assert mime_type == "image/jpeg"
