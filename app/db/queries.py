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
    ) -> MealRecord: ...

    async def append_to_meal(
        self,
        meal: MealRecord,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
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
    ) -> MealRecord:
        row = await self._pool.fetchrow(
            "INSERT INTO meals (user_id, logged_at, photo_media_id, photo_media_ids, foods, "
            "total_calories, confidence) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            uuid.UUID(user_id),
            now,
            media_id,
            [media_id],
            json.dumps(foods),
            total_calories,
            confidence,
        )
        return _row_to_record(row)

    async def append_to_meal(
        self,
        meal: MealRecord,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
    ) -> MealRecord:
        combined_media = [*meal.photo_media_ids, media_id]
        combined_foods = [*meal.foods, *foods]
        combined_total = meal.total_calories + total_calories
        row = await self._pool.fetchrow(
            "UPDATE meals SET photo_media_ids = $1, foods = $2, total_calories = $3 "
            "WHERE id = $4 RETURNING *",
            combined_media,
            json.dumps(combined_foods),
            combined_total,
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
