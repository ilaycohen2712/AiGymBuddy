import asyncio
import base64
import json
from pathlib import Path
from typing import Protocol

import anthropic

from app.config import settings

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "calorie_vision.md"


class VisionModelClient(Protocol):
    async def analyze(
        self,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
        clarification: str | None = None,
    ) -> dict: ...


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


class ClaudeVisionClient:
    """A single named Claude model, callable through the shared
    VisionModelClient contract (contracts/vision_model_client.md). Every
    registry entry is one of these, differing only by `model` — the prompt,
    schema validation, and error behavior are identical across candidates so
    a comparison run measures the model, not the plumbing around it."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._client: anthropic.AsyncAnthropic | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            async with self._client_lock:
                if self._client is None:  # re-check: another task may have won the race
                    self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def analyze(
        self,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
        clarification: str | None = None,
    ) -> dict:
        client = await self._get_client()
        image_b64 = base64.standard_b64encode(image_bytes).decode()

        prompt_text = "Analyze this food photo."
        if clarification:
            prompt_text = (
                "Analyze this food photo. You previously asked a clarifying question "
                f"about it; here is the user's answer: {clarification}"
            )

        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_load_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )

        text = "".join(block.text for block in response.content if block.type == "text")
        result = _extract_json_block(text)
        return _validate_schema(result)


MODEL_REGISTRY: dict[str, VisionModelClient] = {
    "claude-sonnet-5": ClaudeVisionClient("claude-sonnet-5"),
    "claude-opus-4-8": ClaudeVisionClient("claude-opus-4-8"),
}
