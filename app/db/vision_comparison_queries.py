from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ModelResult:
    id: str
    comparison_run_id: str
    model_id: str
    fixture_image: str
    status: str  # "ok" | "failed"
    foods: list[dict] | None = None
    total_calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    confidence: float | None = None
    error_message: str | None = None


@dataclass
class AccuracyScore:
    comparison_run_id: str
    model_id: str
    metric: str  # "calories" | "protein" | "carbs" | "fat"
    mean_absolute_error_pct: float
    sample_count: int


class ComparisonRepository(Protocol):
    """Storage boundary for comparison runs. AsyncpgComparisonRepository is the
    real, Postgres-backed implementation; tests use an in-memory fake
    (tests/fakes.py), per data-model.md's comparison_runs/model_results/
    accuracy_scores tables."""

    async def create_comparison_run(self) -> str: ...

    async def record_model_result(
        self,
        run_id: str,
        model_id: str,
        fixture_image: str,
        status: str,
        *,
        foods: list[dict] | None = None,
        total_calories: float | None = None,
        protein_g: float | None = None,
        carbs_g: float | None = None,
        fat_g: float | None = None,
        confidence: float | None = None,
        error_message: str | None = None,
    ) -> ModelResult: ...

    async def complete_comparison_run(self, run_id: str) -> None: ...

    async def get_model_results(self, run_id: str) -> list[ModelResult]: ...

    async def record_accuracy_scores(self, scores: list[AccuracyScore]) -> None: ...

    async def get_accuracy_scores(self, run_id: str) -> list[AccuracyScore]: ...


def _row_to_model_result(row) -> ModelResult:
    foods = row["foods"]
    return ModelResult(
        id=str(row["id"]),
        comparison_run_id=str(row["comparison_run_id"]),
        model_id=row["model_id"],
        fixture_image=row["fixture_image"],
        status=row["status"],
        foods=(json.loads(foods) if isinstance(foods, str) else foods),
        total_calories=(
            float(row["total_calories"]) if row["total_calories"] is not None else None
        ),
        protein_g=(float(row["protein_g"]) if row["protein_g"] is not None else None),
        carbs_g=(float(row["carbs_g"]) if row["carbs_g"] is not None else None),
        fat_g=(float(row["fat_g"]) if row["fat_g"] is not None else None),
        confidence=(float(row["confidence"]) if row["confidence"] is not None else None),
        error_message=row["error_message"],
    )


class AsyncpgComparisonRepository:
    """Postgres-backed implementation against comparison_runs/model_results/
    accuracy_scores (0003_vision_model_comparison.sql)."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def create_comparison_run(self) -> str:
        row = await self._pool.fetchrow(
            "INSERT INTO comparison_runs DEFAULT VALUES RETURNING id"
        )
        return str(row["id"])

    async def record_model_result(
        self,
        run_id: str,
        model_id: str,
        fixture_image: str,
        status: str,
        *,
        foods: list[dict] | None = None,
        total_calories: float | None = None,
        protein_g: float | None = None,
        carbs_g: float | None = None,
        fat_g: float | None = None,
        confidence: float | None = None,
        error_message: str | None = None,
    ) -> ModelResult:
        row = await self._pool.fetchrow(
            "INSERT INTO model_results (comparison_run_id, model_id, fixture_image, status, "
            "foods, total_calories, protein_g, carbs_g, fat_g, confidence, error_message) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *",
            uuid.UUID(run_id),
            model_id,
            fixture_image,
            status,
            json.dumps(foods) if foods is not None else None,
            total_calories,
            protein_g,
            carbs_g,
            fat_g,
            confidence,
            error_message,
        )
        return _row_to_model_result(row)

    async def complete_comparison_run(self, run_id: str) -> None:
        await self._pool.execute(
            "UPDATE comparison_runs SET status = 'completed', completed_at = now() WHERE id = $1",
            uuid.UUID(run_id),
        )

    async def get_model_results(self, run_id: str) -> list[ModelResult]:
        rows = await self._pool.fetch(
            "SELECT * FROM model_results WHERE comparison_run_id = $1", uuid.UUID(run_id)
        )
        return [_row_to_model_result(row) for row in rows]

    async def record_accuracy_scores(self, scores: list[AccuracyScore]) -> None:
        for score in scores:
            await self._pool.execute(
                "INSERT INTO accuracy_scores (comparison_run_id, model_id, metric, "
                "mean_absolute_error_pct, sample_count) VALUES ($1, $2, $3, $4, $5)",
                uuid.UUID(score.comparison_run_id),
                score.model_id,
                score.metric,
                score.mean_absolute_error_pct,
                score.sample_count,
            )

    async def get_accuracy_scores(self, run_id: str) -> list[AccuracyScore]:
        rows = await self._pool.fetch(
            "SELECT * FROM accuracy_scores WHERE comparison_run_id = $1", uuid.UUID(run_id)
        )
        return [
            AccuracyScore(
                comparison_run_id=str(row["comparison_run_id"]),
                model_id=row["model_id"],
                metric=row["metric"],
                mean_absolute_error_pct=float(row["mean_absolute_error_pct"]),
                sample_count=row["sample_count"],
            )
            for row in rows
        ]
