import asyncio
import base64
import json
from pathlib import Path
from typing import Protocol

import anthropic
from google.genai import types

from app.config import settings
from app.services import gemini_client

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
            # This model emits an unrequested "thinking" content block ahead
            # of its actual answer, and that reasoning competes with the
            # answer for the same max_tokens budget. Its size varies
            # unpredictably call-to-call (no temperature is pinned) —
            # confirmed live: the identical photo, called twice at
            # max_tokens=1024, once left room for a full JSON answer and
            # once consumed the *entire* budget on thinking alone, returning
            # zero answer text (stop_reason="max_tokens") and guaranteeing a
            # JSONDecodeError downstream. 4096 kept total usage well within
            # budget across every fixture photo tested, including a complex
            # multi-item one that had triggered the failure at 1024 — but
            # doesn't structurally rule out an even more complex photo
            # someday needing more (see the stop_reason check below, which
            # turns that case into a clear error instead of a cryptic one).
            max_tokens=4096,
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
        if not text:
            raise ValueError(
                f"Vision model returned no answer text (stop_reason={response.stop_reason!r}) "
                "— likely the max_tokens budget was exhausted by the model's own reasoning "
                "before it produced an answer"
            )
        result = _extract_json_block(text)
        return _validate_schema(result)


class GeminiVisionClient:
    """A single named Gemini model, callable through the shared
    VisionModelClient contract — the Gemini counterpart to
    ClaudeVisionClient (specs/006-gemini-flash-migration research.md #4).
    Reuses the same prompt file, JSON extraction, and schema validation so a
    comparison run measures the model, not the plumbing around it."""

    def __init__(self, model: str) -> None:
        self._model = model

    async def analyze(
        self,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
        clarification: str | None = None,
    ) -> dict:
        client = await gemini_client.get_client()

        prompt_text = "Analyze this food photo."
        if clarification:
            prompt_text = (
                "Analyze this food photo. You previously asked a clarifying question "
                f"about it; here is the user's answer: {clarification}"
            )

        response = await client.aio.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                prompt_text,
            ],
            config=types.GenerateContentConfig(
                system_instruction=_load_prompt(),
                max_output_tokens=4096,
            ),
        )

        text = response.text
        if not text:
            raise ValueError(
                "Vision model returned no answer text "
                f"(finish_reason={response.candidates[0].finish_reason!r}) — likely the "
                "max_output_tokens budget was exhausted before it produced an answer"
            )
        result = _extract_json_block(text)
        return _validate_schema(result)


MODEL_REGISTRY: dict[str, VisionModelClient] = {
    "claude-sonnet-5": ClaudeVisionClient("claude-sonnet-5"),
    "claude-opus-4-8": ClaudeVisionClient("claude-opus-4-8"),
    "gemini-flash-latest": GeminiVisionClient("gemini-flash-latest"),
}
