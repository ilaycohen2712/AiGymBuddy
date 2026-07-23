from __future__ import annotations

import json
from pathlib import Path

from app.db.vision_comparison_queries import AccuracyScore, ComparisonRepository, ModelResult
from app.services.vision_models import MODEL_REGISTRY

DEFAULT_FIXTURES_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "food_photos"

# metric name -> (manifest ground-truth key, ModelResult attribute)
METRICS: dict[str, tuple[str, str]] = {
    "calories": ("expected_calories", "total_calories"),
    "protein": ("expected_protein_g", "protein_g"),
    "carbs": ("expected_carbs_g", "carbs_g"),
    "fat": ("expected_fat_g", "fat_g"),
}

RANGE_FACTOR = 0.2  # ±20%, same method as meal_logging.format_range_reply


def _range(value: float) -> tuple[float, float]:
    """Same ±20% method meal_logging.format_range_reply uses for calories,
    applied here to calories and macros alike (research.md decision #6)."""
    return value * (1 - RANGE_FACTOR), value * (1 + RANGE_FACTOR)


def _sum_macro(foods: list[dict], key: str) -> float:
    return sum(food.get(key, 0) for food in foods)


def load_manifest(fixtures_dir: Path) -> list[dict]:
    manifest_path = fixtures_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    return json.loads(manifest_path.read_text())


async def run_comparison(
    repo: ComparisonRepository,
    model_ids: list[str],
    fixtures_dir: Path = DEFAULT_FIXTURES_DIR,
) -> str:
    """Run every model_id against every fixture manifest entry, persisting
    each (model, photo) outcome immediately — not buffered — so an
    interrupted run still leaves a durable, queryable partial record
    (research.md decision #3). One model's failure on one photo never stops
    the rest (FR-006, Edge Cases). Returns the comparison_runs id."""
    if len(model_ids) < 2:
        raise ValueError("A comparison run requires at least 2 model_ids (FR-001)")
    unknown = [model_id for model_id in model_ids if model_id not in MODEL_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown model_id(s): {unknown}")

    manifest = load_manifest(fixtures_dir)
    run_id = await repo.create_comparison_run()

    for entry in manifest:
        image_bytes = (fixtures_dir / entry["image"]).read_bytes()
        for model_id in model_ids:
            client = MODEL_REGISTRY[model_id]
            try:
                result = await client.analyze(image_bytes)
            except (ValueError, json.JSONDecodeError) as exc:
                await repo.record_model_result(
                    run_id, model_id, entry["image"], "failed", error_message=str(exc)
                )
                continue
            foods = result["foods"]
            await repo.record_model_result(
                run_id,
                model_id,
                entry["image"],
                "ok",
                foods=foods,
                total_calories=result["total_calories"],
                protein_g=_sum_macro(foods, "protein_g"),
                carbs_g=_sum_macro(foods, "carbs_g"),
                fat_g=_sum_macro(foods, "fat_g"),
                confidence=result.get("confidence"),
            )

    model_results = await repo.get_model_results(run_id)
    scores = score_accuracy(run_id, model_results, manifest)
    if scores:
        await repo.record_accuracy_scores(scores)
    await repo.complete_comparison_run(run_id)
    return run_id


def score_accuracy(
    run_id: str, model_results: list[ModelResult], manifest: list[dict]
) -> list[AccuracyScore]:
    """MAE% per (model_id, metric) — same method as
    tests/test_calorie_accuracy.py's regression gate (research.md decision
    #4). Excludes failed model_results and photos missing that metric's
    ground truth (FR-005); ground-truth fields are read with .get() since
    expected_protein_g/expected_carbs_g/expected_fat_g are optional on a
    manifest entry (only expected_calories is guaranteed)."""
    ground_truth_by_image = {entry["image"]: entry for entry in manifest}

    errors_by_model_metric: dict[tuple[str, str], list[float]] = {}
    for result in model_results:
        if result.status != "ok":
            continue
        entry = ground_truth_by_image.get(result.fixture_image)
        if entry is None:
            continue
        for metric, (expected_key, actual_attr) in METRICS.items():
            expected = entry.get(expected_key)
            actual = getattr(result, actual_attr)
            if expected is None or expected == 0 or actual is None:
                continue
            error_pct = abs(actual - expected) / expected * 100
            errors_by_model_metric.setdefault((result.model_id, metric), []).append(error_pct)

    return [
        AccuracyScore(
            comparison_run_id=run_id,
            model_id=model_id,
            metric=metric,
            mean_absolute_error_pct=sum(errors) / len(errors),
            sample_count=len(errors),
        )
        for (model_id, metric), errors in errors_by_model_metric.items()
    ]
