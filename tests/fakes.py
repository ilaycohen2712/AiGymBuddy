"""In-memory test doubles, used instead of a live Postgres instance."""

from __future__ import annotations

import datetime as dt
import uuid

from app.db.queries import MealRecord, _combine_confidence


class InMemoryMealRepository:
    def __init__(self) -> None:
        self.meals: dict[str, MealRecord] = {}

    async def find_open_meal(
        self, user_id: str, now: dt.datetime, window: dt.timedelta
    ) -> MealRecord | None:
        candidates = [
            m
            for m in self.meals.values()
            if m.user_id == user_id and now - m.logged_at <= window
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.logged_at)

    async def create_meal(
        self,
        user_id: str,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
        now: dt.datetime,
    ) -> MealRecord:
        meal = MealRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            logged_at=now,
            photo_media_ids=[media_id],
            foods=list(foods),
            total_calories=total_calories,
            confidence=confidence,
        )
        self.meals[meal.id] = meal
        return meal

    async def append_to_meal(
        self,
        meal: MealRecord,
        media_id: str,
        foods: list[dict],
        total_calories: float,
        confidence: float | None,
    ) -> MealRecord:
        # logged_at is deliberately left unchanged — the window is anchored to
        # the first photo, not sliding. See queries.py's AsyncpgMealRepository
        # for the full rationale.
        meal.photo_media_ids.append(media_id)
        meal.foods.extend(foods)
        meal.total_calories += total_calories
        meal.confidence = _combine_confidence(meal.confidence, confidence)
        self.meals[meal.id] = meal
        return meal


class InMemoryMessageStore:
    """Fakes app.db.queries.is_message_processed / record_message for tests."""

    def __init__(self) -> None:
        self.processed: set[str] = set()

    async def is_message_processed(self, pool, wa_message_id: str) -> bool:
        return wa_message_id in self.processed

    async def record_message(
        self, pool, user_id, wa_message_id, direction, kind, body=None
    ) -> None:
        self.processed.add(wa_message_id)
