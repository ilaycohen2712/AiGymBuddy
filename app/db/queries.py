from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class MealRecord:
    id: str
    user_id: str
    logged_at: dt.datetime
    photo_media_ids: list[str] = field(default_factory=list)
    foods: list[dict] = field(default_factory=list)
    total_calories: float = 0.0
    confidence: float | None = None
    model_id: str | None = None


def _combine_confidence(a: float | None, b: float | None) -> float | None:
    """Combining two photos' confidence into one meal's confidence uses the
    minimum, not the latest value: the combined estimate is only as reliable
    as its least-confident component photo."""
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None


class MealRepository(Protocol):
    """Storage boundary for meal entries. AsyncpgMealRepository is the real,
    Postgres-backed implementation; tests use an in-memory fake (tests/fakes.py)
    implementing the same shape, per db-schema.md's meals table."""

    async def find_open_meal(
        self, user_id: str, now: dt.datetime, window: dt.timedelta
    ) -> MealRecord | None: ...

    async def create_meal(
        self,
        user_id: str,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
        now: dt.datetime,
        model_id: str | None = None,
    ) -> MealRecord: ...

    async def append_to_meal(
        self,
        meal: MealRecord,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
        model_id: str | None = None,
    ) -> MealRecord: ...


def _row_to_record(row) -> MealRecord:
    return MealRecord(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        logged_at=row["logged_at"],
        photo_media_ids=list(row["photo_media_ids"]),
        foods=json.loads(row["foods"]) if isinstance(row["foods"], str) else row["foods"],
        total_calories=float(row["total_calories"]),
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        model_id=row["model_id"],
    )


class AsyncpgMealRepository:
    """Postgres-backed implementation against the `meals` table (0001_init.sql)."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def find_open_meal(
        self, user_id: str, now: dt.datetime, window: dt.timedelta
    ) -> MealRecord | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM meals WHERE user_id = $1 AND logged_at > $2 "
            "ORDER BY logged_at DESC LIMIT 1",
            uuid.UUID(user_id),
            now - window,
        )
        return _row_to_record(row) if row else None

    async def create_meal(
        self,
        user_id: str,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
        now: dt.datetime,
        model_id: str | None = None,
    ) -> MealRecord:
        row = await self._pool.fetchrow(
            "INSERT INTO meals (user_id, logged_at, photo_media_id, photo_media_ids, foods, "
            "total_calories, confidence, model_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "RETURNING *",
            uuid.UUID(user_id),
            now,
            media_id,
            [media_id],
            json.dumps(foods),
            total_calories,
            confidence,
            model_id,
        )
        return _row_to_record(row)

    async def append_to_meal(
        self,
        meal: MealRecord,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
        model_id: str | None = None,
    ) -> MealRecord:
        # logged_at is deliberately NOT updated here: the grouping window is
        # anchored to the first photo (research.md #2 / FR-014), not sliding.
        # A sliding window (refreshing on every append) was tried and found live
        # to let a meal stay "open" indefinitely as long as *any* photo arrived
        # within 10 min of the *previous* one — during an active multi-photo
        # test session this silently merged unrelated meals across over an hour.
        # model_id: latest-write-wins, same as foods/total_calories being
        # combined — the meal row reflects whichever model most recently
        # contributed to it (FR-008).
        combined_media = [*meal.photo_media_ids, media_id]
        combined_foods = [*meal.foods, *foods]
        combined_total = meal.total_calories + total_calories
        combined_confidence = _combine_confidence(meal.confidence, confidence)
        row = await self._pool.fetchrow(
            "UPDATE meals SET photo_media_ids = $1, foods = $2, total_calories = $3, "
            "confidence = $4, model_id = $5 WHERE id = $6 RETURNING *",
            combined_media,
            json.dumps(combined_foods),
            combined_total,
            combined_confidence,
            model_id,
            uuid.UUID(meal.id),
        )
        return _row_to_record(row)


async def get_or_create_user_id(pool, wa_phone: str) -> str:
    row = await pool.fetchrow("SELECT id FROM users WHERE wa_phone = $1", wa_phone)
    if row:
        return str(row["id"])
    row = await pool.fetchrow(
        "INSERT INTO users (wa_phone) VALUES ($1) RETURNING id", wa_phone
    )
    return str(row["id"])


async def is_message_processed(pool, wa_message_id: str) -> bool:
    """Dedupe guard: Meta redelivers webhooks on timeout/non-2xx, so any
    message must be checked against `messages.wa_message_id` before
    (re)processing it (per whatsapp-api skill's dedupe convention)."""
    row = await pool.fetchrow(
        "SELECT 1 FROM messages WHERE wa_message_id = $1", wa_message_id
    )
    return row is not None


async def set_pending_clarification(
    pool, user_id: str, media_id: str, media_type: str, question: str
) -> None:
    """Remember the outstanding clarifying question (calorie_vision.md rule 6)
    so a text reply can resume this photo's analysis instead of it being a
    dead end. At most one pending clarification per user at a time."""
    await pool.execute(
        "INSERT INTO pending_clarifications (user_id, media_id, media_type, question) "
        "VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (user_id) DO UPDATE SET media_id = $2, media_type = $3, "
        "question = $4, asked_at = now()",
        uuid.UUID(user_id),
        media_id,
        media_type,
        question,
    )


async def get_pending_clarification(pool, user_id: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT media_id, media_type, question FROM pending_clarifications WHERE user_id = $1",
        uuid.UUID(user_id),
    )
    return dict(row) if row else None


async def clear_pending_clarification(pool, user_id: str) -> None:
    await pool.execute(
        "DELETE FROM pending_clarifications WHERE user_id = $1", uuid.UUID(user_id)
    )


async def record_message(
    pool, user_id: str, wa_message_id: str, direction: str, kind: str, body: str | None = None
) -> None:
    await pool.execute(
        "INSERT INTO messages (user_id, direction, wa_message_id, body, kind) "
        "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (wa_message_id) DO NOTHING",
        uuid.UUID(user_id),
        direction,
        wa_message_id,
        body,
        kind,
    )
