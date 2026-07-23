import pytest

from app.config import settings
from app.services import vision_comparison, vision_models
from tests.fakes import InMemoryComparisonRepository


class AlwaysSucceedsClient:
    async def analyze(self, image_bytes, media_type="image/jpeg", clarification=None):
        return {
            "foods": [
                {
                    "name": "meal",
                    "portion_grams": 200,
                    "calories": 400,
                    "protein_g": 20,
                    "carbs_g": 40,
                    "fat_g": 10,
                }
            ],
            "total_calories": 400,
            "confidence": 0.85,
            "clarifying_question": None,
        }


class AlwaysFailsClient:
    async def analyze(self, image_bytes, media_type="image/jpeg", clarification=None):
        raise ValueError("Vision result missing required fields: {'confidence'}")


@pytest.fixture
def fixtures_dir(tmp_path):
    (tmp_path / "salad.jpg").write_bytes(b"fake-1")
    (tmp_path / "burger.jpg").write_bytes(b"fake-2")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '[{"image": "salad.jpg", "expected_calories": 380, "expected_protein_g": 18, '
        '"expected_carbs_g": 38, "expected_fat_g": 9}, '
        '{"image": "burger.jpg", "expected_calories": 420}]'
    )
    return tmp_path


@pytest.mark.asyncio
async def test_comparison_run_isolates_failures_per_model_and_photo(monkeypatch, fixtures_dir):
    """User Story 1 acceptance scenario 2: one candidate model failing on a
    photo is recorded against that model/photo only — every other (model,
    photo) pair completes normally, and the run still reaches 'completed'
    (FR-006, SC-006, Edge Cases: interrupted/failed run handling)."""
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "good-model", AlwaysSucceedsClient())
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "bad-model", AlwaysFailsClient())
    repo = InMemoryComparisonRepository()

    run_id = await vision_comparison.run_comparison(repo, ["good-model", "bad-model"], fixtures_dir)

    results = await repo.get_model_results(run_id)
    assert len(results) == 4  # 2 models x 2 photos

    by_key = {(r.model_id, r.fixture_image): r for r in results}
    for image in ("salad.jpg", "burger.jpg"):
        good = by_key[("good-model", image)]
        assert good.status == "ok"
        assert good.total_calories == 400

        bad = by_key[("bad-model", image)]
        assert bad.status == "failed"
        assert bad.error_message

    assert repo.runs[run_id] == "completed"

    scores = await repo.get_accuracy_scores(run_id)
    good_calorie_score = next(
        s for s in scores if s.model_id == "good-model" and s.metric == "calories"
    )
    assert good_calorie_score.sample_count == 2
    # good-model's fixed 400 kcal vs ground truth 380 and 420 -> 5.26% and 4.76% MAE
    assert good_calorie_score.mean_absolute_error_pct == pytest.approx(5.02, abs=0.1)
    assert not any(s.model_id == "bad-model" for s in scores)


@pytest.mark.asyncio
async def test_comparison_run_never_touches_the_live_model_resolution(monkeypatch, fixtures_dir):
    """User Story 1 acceptance scenario 3 / FR-006: resolving the live client
    via MODEL_REGISTRY[settings.live_vision_model_id] must be unaffected by a
    comparison run, before, during, and after it — the comparison path never
    reads or writes settings.live_vision_model_id, so this holds by
    construction, verified here rather than deferred to User Story 3."""
    monkeypatch.setattr(settings, "live_vision_model_id", "good-model")
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "good-model", AlwaysSucceedsClient())
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "bad-model", AlwaysFailsClient())
    repo = InMemoryComparisonRepository()

    live_client_before = vision_models.MODEL_REGISTRY[settings.live_vision_model_id]

    await vision_comparison.run_comparison(repo, ["good-model", "bad-model"], fixtures_dir)

    live_client_after = vision_models.MODEL_REGISTRY[settings.live_vision_model_id]
    assert live_client_after is live_client_before
    assert settings.live_vision_model_id == "good-model"
