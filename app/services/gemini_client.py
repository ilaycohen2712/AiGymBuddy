import asyncio

from google import genai

from app.config import settings

_client: genai.Client | None = None
_client_lock = asyncio.Lock()


async def get_client() -> genai.Client:
    """Shared Gemini client singleton, same double-checked-lock pattern each
    call site previously used for its own `anthropic.AsyncAnthropic`
    instance (specs/006-gemini-flash-migration research.md #5)."""
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # re-check: another task may have won the race
                _client = genai.Client(api_key=settings.gemini_api_key)
    return _client
