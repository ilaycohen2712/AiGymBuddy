"""CLI entrypoint for the vision-model research comparison — see
specs/003-vision-model-comparison/contracts/compare_vision_models_cli.md.

Usage:
    python -m scripts.compare_vision_models --models claude-sonnet-5,claude-opus-4-8
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.db.pool import get_pool
from app.db.vision_comparison_queries import AccuracyScore, AsyncpgComparisonRepository, ModelResult
from app.services.vision_comparison import (
    DEFAULT_FIXTURES_DIR,
    _range,
    load_manifest,
    run_comparison,
)
from app.services.vision_models import MODEL_REGISTRY


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run two or more candidate vision models against the labeled fixture set."
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated model_ids, e.g. claude-sonnet-5,claude-opus-4-8",
    )
    parser.add_argument("--fixtures-dir", default=str(DEFAULT_FIXTURES_DIR))
    return parser.parse_args(argv)


def _format_result_line(model_id: str, result: ModelResult | None) -> str:
    if result is None or result.status != "ok":
        error = result.error_message if result else "no result recorded"
        return f"  {model_id}: FAILED ({error})"
    cal_low, cal_high = _range(result.total_calories)
    pro_low, pro_high = _range(result.protein_g)
    carb_low, carb_high = _range(result.carbs_g)
    fat_low, fat_high = _range(result.fat_g)
    return (
        f"  {model_id}: {cal_low:.0f}-{cal_high:.0f} kcal "
        f"(protein {pro_low:.0f}-{pro_high:.0f}g, carbs {carb_low:.0f}-{carb_high:.0f}g, "
        f"fat {fat_low:.0f}-{fat_high:.0f}g)"
    )


def print_summary(
    model_ids: list[str],
    manifest: list[dict],
    model_results: list[ModelResult],
    accuracy_scores: list[AccuracyScore],
) -> None:
    """Grouped per-photo/per-model summary (FR-003), each model's calorie and
    macro range (FR-002) and status — never a model's clarifying_question or
    other free text (FR-010)."""
    results_by_image: dict[str, dict[str, ModelResult]] = {}
    for result in model_results:
        results_by_image.setdefault(result.fixture_image, {})[result.model_id] = result

    for entry in manifest:
        image = entry["image"]
        print(f"\n{image}")
        for model_id in model_ids:
            result = results_by_image.get(image, {}).get(model_id)
            print(_format_result_line(model_id, result))

    if not accuracy_scores:
        return
    print("\nAccuracy (mean absolute error %, lower is better):")
    scores_by_model: dict[str, dict[str, AccuracyScore]] = {}
    for score in accuracy_scores:
        scores_by_model.setdefault(score.model_id, {})[score.metric] = score
    for model_id in model_ids:
        metrics = scores_by_model.get(model_id)
        if not metrics:
            continue
        parts = [
            f"{metric}={score.mean_absolute_error_pct:.1f}% (n={score.sample_count})"
            for metric, score in metrics.items()
        ]
        print(f"  {model_id}: {', '.join(parts)}")


async def _run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    model_ids = [model_id.strip() for model_id in args.models.split(",") if model_id.strip()]
    fixtures_dir = Path(args.fixtures_dir)

    if len(model_ids) < 2:
        print("error: --models requires at least 2 comma-separated model ids", file=sys.stderr)
        return 1
    unknown = [model_id for model_id in model_ids if model_id not in MODEL_REGISTRY]
    if unknown:
        print(f"error: unknown model id(s): {', '.join(unknown)}", file=sys.stderr)
        return 1
    if not (fixtures_dir / "manifest.json").exists():
        print(f"error: no manifest.json found in {fixtures_dir}", file=sys.stderr)
        return 1

    pool = await get_pool()
    repo = AsyncpgComparisonRepository(pool)
    run_id = await run_comparison(repo, model_ids, fixtures_dir)

    manifest = load_manifest(fixtures_dir)
    model_results = await repo.get_model_results(run_id)
    accuracy_scores = await repo.get_accuracy_scores(run_id)
    print_summary(model_ids, manifest, model_results, accuracy_scores)
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
