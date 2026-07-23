"""In-memory test doubles, used instead of a live Postgres instance."""

from __future__ import annotations

import datetime as dt
import uuid

from app.db.queries import MealRecord, _combine_confidence
from app.db.vision_comparison_queries import AccuracyScore, ModelResult


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
        model_id: str | None = None,
    ) -> MealRecord:
        meal = MealRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            logged_at=now,
            photo_media_ids=[media_id],
            foods=list(foods),
            total_calories=total_calories,
            confidence=confidence,
            model_id=model_id,
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
        model_id: str | None = None,
    ) -> MealRecord:
        # logged_at is deliberately left unchanged — the window is anchored to
        # the first photo, not sliding. See queries.py's AsyncpgMealRepository
        # for the full rationale.
        meal.photo_media_ids.append(media_id)
        meal.foods.extend(foods)
        meal.total_calories += total_calories
        meal.confidence = _combine_confidence(meal.confidence, confidence)
        meal.model_id = model_id
        self.meals[meal.id] = meal
        return meal


class InMemoryComparisonRepository:
    def __init__(self) -> None:
        self.runs: dict[str, str] = {}  # run_id -> status
        self.results: list[ModelResult] = []
        self.scores: list[AccuracyScore] = []

    async def create_comparison_run(self) -> str:
        run_id = str(uuid.uuid4())
        self.runs[run_id] = "running"
        return run_id

    async def record_model_result(
        self,
        run_id: str,
        model_id: str,
        fixture_image: str,
        status: str,
        *,
        foods=None,
        total_calories=None,
        protein_g=None,
        carbs_g=None,
        fat_g=None,
        confidence=None,
        error_message=None,
    ) -> ModelResult:
        result = ModelResult(
            id=str(uuid.uuid4()),
            comparison_run_id=run_id,
            model_id=model_id,
            fixture_image=fixture_image,
            status=status,
            foods=list(foods) if foods is not None else None,
            total_calories=total_calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            confidence=confidence,
            error_message=error_message,
        )
        self.results.append(result)
        return result

    async def complete_comparison_run(self, run_id: str) -> None:
        self.runs[run_id] = "completed"

    async def get_model_results(self, run_id: str) -> list[ModelResult]:
        return [r for r in self.results if r.comparison_run_id == run_id]

    async def record_accuracy_scores(self, scores: list[AccuracyScore]) -> None:
        self.scores.extend(scores)

    async def get_accuracy_scores(self, run_id: str) -> list[AccuracyScore]:
        return [s for s in self.scores if s.comparison_run_id == run_id]


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
