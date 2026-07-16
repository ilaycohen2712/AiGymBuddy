import asyncio
import base64
import json
from pathlib import Path

import anthropic

from app.config import settings

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "calorie_vision.md"
MODEL = "claude-sonnet-5"

_client: anthropic.AsyncAnthropic | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # re-check: another task may have won the race
                _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _load_prompt() -> str:
    return PROMPT_PATH.read_text()


def _extract_json_block(text: str) -> dict:
    """Strip a ```json ... ``` fence if present. Only strips a leading/trailing
    triple-backtick fence, not arbitrary backticks, so malformed fencing fails
    loudly (via json.JSONDecodeError) rather than silently mangling content."""
    text = text.strip()
    if text.startswith("```"):
        text = text[3:]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def _validate_schema(result: dict) -> dict:
    required = {"foods", "total_calories", "confidence", "clarifying_question"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Vision result missing required fields: {missing}")
    food_required = {"name", "portion_grams", "calories", "protein_g", "carbs_g", "fat_g"}
    for food in result["foods"]:
        food_missing = food_required - food.keys()
        if food_missing:
            raise ValueError(f"Food item missing required fields: {food_missing}")
    return result


async def analyze_photo(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Send a food photo to Claude using the versioned calorie_vision prompt
    (app/prompts/calorie_vision.md) and return a result validated against the
    calorie-estimation schema (Constitution IV). Raises ValueError or
    json.JSONDecodeError on a non-conforming response — callers must handle
    this and fall back to a graceful user-facing reply rather than crash."""
    client = await _get_client()
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_load_prompt(),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                    },
                    {"type": "text", "text": "Analyze this food photo."},
                ],
            }
        ],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    result = _extract_json_block(text)
    return _validate_schema(result)
