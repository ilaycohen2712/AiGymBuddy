import asyncio
from typing import Protocol

import anthropic
from google.genai import types

from app.config import settings
from app.services import gemini_client


class TextModelClient(Protocol):
    async def generate(
        self, system_instruction: str, user_content: str, max_tokens: int
    ) -> str: ...


class ClaudeTextClient:
    """A single named Claude model, callable through the shared
    TextModelClient contract — the text-only counterpart to
    app/services/vision_models.py's ClaudeVisionClient. Every registry entry
    is one of these or a GeminiTextClient, differing only by `model` — the
    caller (text_analysis.py / eod_report.py / timezone.py) owns its own
    prompt, JSON/plain-text extraction, and schema validation, so swapping
    the model here never changes call-site behavior."""

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

    async def generate(self, system_instruction: str, user_content: str, max_tokens: int) -> str:
        client = await self._get_client()
        response = await client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_instruction,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class GeminiTextClient:
    """The Gemini counterpart to ClaudeTextClient — see its docstring for
    the shared contract this implements."""

    def __init__(self, model: str) -> None:
        self._model = model

    async def generate(self, system_instruction: str, user_content: str, max_tokens: int) -> str:
        client = await gemini_client.get_client()
        response = await client.aio.models.generate_content(
            model=self._model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_tokens,
                # Confirmed live (specs/006-gemini-flash-migration): this
                # model's default "thinking" pass consumes part of
                # max_output_tokens before producing its actual answer, the
                # same class of problem ClaudeVisionClient works around by
                # budgeting extra tokens (see its docstring) — except here a
                # small, deliberately tight budget (64-256 tokens for a
                # single-line JSON/plain-text answer) left no room left for
                # the answer once thinking ate into it, truncating the JSON
                # mid-string. These call sites need no reasoning — schema-
                # constrained, single-turn classification/extraction — so
                # disable it outright rather than inflating every budget.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = response.text
        if not text:
            finish_reason = response.candidates[0].finish_reason if response.candidates else None
            raise ValueError(
                f"Text model returned no answer text (finish_reason={finish_reason!r})"
            )
        return text


MODEL_REGISTRY: dict[str, TextModelClient] = {
    "claude-sonnet-5": ClaudeTextClient("claude-sonnet-5"),
    "claude-haiku-4-5": ClaudeTextClient("claude-haiku-4-5"),
    "gemini-flash-latest": GeminiTextClient("gemini-flash-latest"),
}
