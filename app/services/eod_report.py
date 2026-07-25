from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import anthropic

from app.config import settings
from app.services.daily_total import format_daily_total_reply

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "eod_feedback.md"
_FEEDBACK_MODEL = "claude-haiku-4-5"
# The sent message is the totals line (format_daily_total_reply, typically
# under 100 chars) plus this feedback text — capped below coach-persona's
# "~600 chars" voice guideline, not at it, so the combined message still
# fits that guideline rather than only the feedback half of it.
FEEDBACK_MAX_CHARS = 500

_client: anthropic.AsyncAnthropic | None = None
_client_lock = asyncio.Lock()


def _load_prompt() -> str:
    return PROMPT_PATH.read_text()


async def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # re-check: another task may have won the race
                _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _extract_json_block(text: str) -> dict:
    """Strip a ```json ... ``` fence if present, same convention as
    vision_models._extract_json_block."""
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


def _validate_feedback(result: dict) -> dict:
    """Schema-validate the eod_feedback prompt's output before use
    (Constitution IV) — {"feedback_text": "", "tone": "encouraging|neutral"}.
    A too-long feedback_text is truncated rather than rejected outright: the
    report must still send exactly once today (FR-006) even if the model
    slightly overruns the coach-persona length guideline."""
    required = {"feedback_text", "tone"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"eod_feedback result missing required fields: {missing}")
    if not isinstance(result["feedback_text"], str):
        raise ValueError(
            f"eod_feedback result has non-string feedback_text: {result['feedback_text']!r}"
        )
    if result["tone"] not in ("encouraging", "neutral"):
        raise ValueError(f"eod_feedback result has invalid tone: {result['tone']!r}")
    if len(result["feedback_text"]) > FEEDBACK_MAX_CHARS:
        result["feedback_text"] = result["feedback_text"][:FEEDBACK_MAX_CHARS]
    return result


async def generate_feedback(totals: dict, target: int) -> dict:
    """Calls the versioned eod_feedback prompt (FR-016) with today's totals
    and the user's daily calorie target, and returns a schema-validated
    result. Raises ValueError/json.JSONDecodeError on a non-conforming
    response — callers must handle this and fall back gracefully rather than
    let one bad report crash the scheduler's whole run for every other
    user."""
    client = await _get_client()
    zero_meal_day = totals["calories"] <= 0
    user_content = (
        f"Total calories eaten today: {totals['calories']:.0f}\n"
        f"Protein: {totals['protein_g']:.0f}g\n"
        f"Carbs: {totals['carbs_g']:.0f}g\n"
        f"Fat: {totals['fat_g']:.0f}g\n"
        f"Daily calorie target: {target}\n"
        f"No meals logged today: {zero_meal_day}"
    )
    response = await client.messages.create(
        model=_FEEDBACK_MODEL,
        max_tokens=256,
        system=_load_prompt(),
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return _validate_feedback(_extract_json_block(text))


def format_report_message(totals: dict, feedback_text: str) -> str:
    """Reuses daily_total.format_daily_total_reply for the totals line — same
    range convention, same zero-meal-day phrasing (FR-012) — so this report
    never invents a second way of presenting the same numbers."""
    return f"{format_daily_total_reply(totals)}\n{feedback_text}"


@dataclass
class ReportDraft:
    message: str
    totals: dict
    feedback_text: str


async def build_report(user_id: str, wa_phone: str, date: dt.date) -> ReportDraft | None:
    """Composes one end-of-day report for `date` (the user's local calendar
    day, resolved by the caller — app/scheduler/eod_trigger.py) per
    contracts/eod-report.md. Returns None if a report for this
    (user_id, date) is already recorded — the caller must not send anything
    in that case (idempotent per FR-006/SC-003).

    Deliberately does NOT persist anything itself: the caller must call
    record_report_sent(...) only *after* actually delivering the message.
    Reviewer-flagged bug found live: the original version inserted the
    daily_reports row before the WhatsApp send was even attempted, so a
    delivery failure (e.g. the 24h window expired with no fallback template
    configured) permanently lost that day's report — the row already said
    "sent" and nothing ever retried it."""
    from app.db import queries
    from app.db.pool import get_pool

    pool = await get_pool()
    if await queries.has_daily_report_for_date(pool, user_id, date):
        logger.info(
            "Daily report for %s already recorded for %s, not building a duplicate",
            _mask(wa_phone),
            date,
        )
        return None

    totals = await queries.get_daily_total(pool, user_id, date)
    target = await queries.get_daily_calorie_target(pool, user_id)
    if target is None:
        raise ValueError("build_report called without a daily_calorie_target set")

    feedback = await generate_feedback(totals, target)
    message = format_report_message(totals, feedback["feedback_text"])
    return ReportDraft(message=message, totals=totals, feedback_text=feedback["feedback_text"])


async def record_report_sent(user_id: str, date: dt.date, draft: ReportDraft) -> None:
    """Persist that today's report was actually delivered (call only after a
    successful send, never before) — the daily_reports UNIQUE(user_id, date)
    constraint still makes this safe even if a near-simultaneous scheduler
    run already recorded the same day (FR-006/SC-003)."""
    from app.db import queries
    from app.db.pool import get_pool

    pool = await get_pool()
    await queries.insert_daily_report(
        pool,
        user_id,
        date,
        calories_total=draft.totals["calories"],
        protein_g=draft.totals["protein_g"],
        carbs_g=draft.totals["carbs_g"],
        fat_g=draft.totals["fat_g"],
        feedback_text=draft.feedback_text,
    )


def _mask(phone: str) -> str:
    """Mask a phone number for logs, keeping only the last 4 digits (Security requirement)."""
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"
