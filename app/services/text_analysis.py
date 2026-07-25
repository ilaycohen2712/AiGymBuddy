import asyncio
import json
import re
from pathlib import Path

import anthropic

from app.config import settings

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "calorie_text.md"

_client: anthropic.AsyncAnthropic | None = None
_client_lock = asyncio.Lock()

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _load_prompt() -> str:
    return PROMPT_PATH.read_text()


def _extract_json_block(text: str) -> dict:
    """Find the JSON object in `text`. Unlike
    app/services/vision_models.py's `_extract_json_block` (which only
    strips a leading/trailing fence, since calorie_vision.md's system
    prompt reliably produces JSON-only output), this searches for a fenced
    block anywhere in the response first — confirmed live (specs/005-text-
    meal-logging quickstart walkthrough) that an adversarial/injection-style
    input can make the model prepend an explanatory sentence before the
    fence even while still correctly declining to comply and returning the
    right `is_food_description: false` JSON, which the stricter
    leading-only strip failed to extract, needlessly falling back to a
    generic error reply instead of the correct one. Falls back to the
    stricter leading/trailing strip for a plain JSON-only response."""
    text = text.strip()
    fenced = _FENCED_JSON_RE.search(text)
    if fenced:
        return json.loads(fenced.group(1))
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
    required = {
        "foods",
        "total_calories",
        "confidence",
        "clarifying_question",
        "is_food_description",
    }
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Text analysis result missing required fields: {missing}")
    food_required = {"name", "portion_grams", "calories", "protein_g", "carbs_g", "fat_g"}
    for food in result["foods"]:
        food_missing = food_required - food.keys()
        if food_missing:
            raise ValueError(f"Food item missing required fields: {food_missing}")
    return result


async def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # re-check: another task may have won the race
                _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def analyze_text(text: str, clarification: str | None = None) -> dict:
    """Send a user's free-form text message to the currently designated live
    model (`settings.live_vision_model_id` — reused here rather than adding a
    separate text-model setting, since this bot's estimation tasks share one
    live model) and return a result validated against the calorie_text.md
    schema (Constitution IV). Raises ValueError or json.JSONDecodeError on a
    non-conforming response — callers must handle this and fall back to a
    graceful user-facing reply rather than crash, same contract as
    app/services/vision.py::analyze_photo.

    `text` is passed as the entire user-turn content — calorie_text.md rule
    1 is the defense against it being treated as anything other than
    potential food-description data (contracts/calorie-text-prompt.md).

    `clarification`: when `text` previously triggered a clarifying question,
    pass the user's answer here so the model can complete a full analysis
    of the *original* text instead of asking again (prompt rule 9), mirroring
    app/services/vision.py::analyze_photo's `clarification` parameter."""
    client = await _get_client()

    user_content = text
    if clarification:
        user_content = (
            f"{text}\n\nYou previously asked a clarifying question about this; "
            f"here is the user's answer: {clarification}"
        )

    response = await client.messages.create(
        model=settings.live_vision_model_id,
        max_tokens=1024,
        system=_load_prompt(),
        messages=[{"role": "user", "content": user_content}],
    )

    response_text = "".join(block.text for block in response.content if block.type == "text")
    result = _extract_json_block(response_text)
    return _validate_schema(result)
