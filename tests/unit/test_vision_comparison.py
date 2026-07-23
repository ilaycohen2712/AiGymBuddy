import pytest

from app.db.vision_comparison_queries import ModelResult
from app.services import vision_comparison, vision_models
from tests.fakes import InMemoryComparisonRepository


class FakeClient:
    """A VisionModelClient test double — always succeeds with `result`, or
    always raises `error` if given."""

    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls = 0

    async def analyze(self, image_bytes, media_type="image/jpeg", clarification=None):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def _vision_result(calories: float, protein: float, carbs: float, fat: float) -> dict:
    return {
        "foods": [
            {
                "name": "meal",
                "portion_grams": 200,
                "calories": calories,
                "protein_g": protein,
                "carbs_g": carbs,
                "fat_g": fat,
            }
        ],
        "total_calories": calories,
        "confidence": 0.8,
        "clarifying_question": None,
    }


@pytest.fixture
def fixtures_dir(tmp_path):
    photo = tmp_path / "meal.jpg"
    photo.write_bytes(b"fake-bytes")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '[{"image": "meal.jpg", "expected_calories": 400, "expected_protein_g": 20, '
        '"expected_carbs_g": 40, "expected_fat_g": 10}]'
    )
    return tmp_path


@pytest.mark.asyncio
async def test_run_comparison_rejects_unknown_model_id(fixtures_dir):
    repo = InMemoryComparisonRepository()

    with pytest.raises(ValueError, match="Unknown model_id"):
        await vision_comparison.run_comparison(
            repo, ["not-a-real-model", "claude-sonnet-5"], fixtures_dir
        )


@pytest.mark.asyncio
async def test_run_comparison_requires_at_least_two_models(fixtures_dir):
    repo = InMemoryComparisonRepository()

    with pytest.raises(ValueError, match="at least 2"):
        await vision_comparison.run_comparison(repo, ["claude-sonnet-5"], fixtures_dir)


@pytest.mark.asyncio
async def test_run_comparison_records_failure_without_raising(monkeypatch, fixtures_dir):
    """A model that raises ValueError (schema-invalid response, per
    vision_models._validate_schema) must be recorded as a failed
    model_results row, not propagate past run_comparison (FR-005)."""
    good = FakeClient(result=_vision_result(400, 20, 40, 10))
    bad = FakeClient(error=ValueError("Vision result missing required fields: {'confidence'}"))
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "good-model", good)
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "bad-model", bad)
    repo = InMemoryComparisonRepository()

    run_id = await vision_comparison.run_comparison(repo, ["good-model", "bad-model"], fixtures_dir)

    results = await repo.get_model_results(run_id)
    by_model = {r.model_id: r for r in results}
    assert by_model["good-model"].status == "ok"
    assert by_model["good-model"].total_calories == 400
    assert by_model["bad-model"].status == "failed"
    assert "missing required fields" in by_model["bad-model"].error_message
    assert repo.runs[run_id] == "completed"


@pytest.mark.asyncio
async def test_run_comparison_sums_macros_across_foods(monkeypatch, fixtures_dir):
    result = {
        "foods": [
            {
                "name": "rice",
                "portion_grams": 150,
                "calories": 200,
                "protein_g": 4,
                "carbs_g": 45,
                "fat_g": 1,
            },
            {
                "name": "chicken",
                "portion_grams": 100,
                "calories": 200,
                "protein_g": 25,
                "carbs_g": 0,
                "fat_g": 8,
            },
        ],
        "total_calories": 400,
        "confidence": 0.9,
        "clarifying_question": None,
    }
    client = FakeClient(result=result)
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "model-a", client)
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "model-b", client)
    repo = InMemoryComparisonRepository()

    run_id = await vision_comparison.run_comparison(repo, ["model-a", "model-b"], fixtures_dir)

    results = await repo.get_model_results(run_id)
    assert results[0].protein_g == 29
    assert results[0].carbs_g == 45
    assert results[0].fat_g == 9


def _result(model_id: str, status: str, **kwargs) -> ModelResult:
    return ModelResult(
        id="r1",
        comparison_run_id="run-1",
        model_id=model_id,
        fixture_image=kwargs.pop("fixture_image", "meal.jpg"),
        status=status,
        **kwargs,
    )


def test_score_accuracy_computes_mae_percent_per_metric():
    manifest = [{"image": "meal.jpg", "expected_calories": 400, "expected_protein_g": 20}]
    results = [_result("model-a", "ok", total_calories=440, protein_g=22)]

    scores = vision_comparison.score_accuracy("run-1", results, manifest)

    by_metric = {s.metric: s for s in scores}
    assert by_metric["calories"].mean_absolute_error_pct == pytest.approx(10.0)
    assert by_metric["calories"].sample_count == 1
    assert by_metric["protein"].mean_absolute_error_pct == pytest.approx(10.0)


def test_score_accuracy_excludes_failed_results():
    manifest = [{"image": "meal.jpg", "expected_calories": 400}]
    results = [_result("model-a", "failed", error_message="boom")]

    scores = vision_comparison.score_accuracy("run-1", results, manifest)

    assert scores == []


def test_score_accuracy_excludes_photos_missing_ground_truth_for_a_metric():
    """expected_protein_g/expected_carbs_g/expected_fat_g are optional per
    manifest.json's format — a photo with only expected_calories must still
    score calories while being excluded from the macro metrics entirely."""
    manifest = [{"image": "meal.jpg", "expected_calories": 400}]
    results = [_result("model-a", "ok", total_calories=400, protein_g=20, carbs_g=40, fat_g=10)]

    scores = vision_comparison.score_accuracy("run-1", results, manifest)

    metrics_scored = {s.metric for s in scores}
    assert metrics_scored == {"calories"}


def test_score_accuracy_aggregates_across_multiple_photos():
    manifest = [
        {"image": "a.jpg", "expected_calories": 400},
        {"image": "b.jpg", "expected_calories": 200},
    ]
    results = [
        _result("model-a", "ok", fixture_image="a.jpg", total_calories=440),
        _result("model-a", "ok", fixture_image="b.jpg", total_calories=180),
    ]

    scores = vision_comparison.score_accuracy("run-1", results, manifest)

    calories_score = next(s for s in scores if s.metric == "calories")
    assert calories_score.sample_count == 2
    assert calories_score.mean_absolute_error_pct == pytest.approx((10.0 + 10.0) / 2)
