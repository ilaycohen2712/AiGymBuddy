import pytest

from app.config import settings
from app.db import queries
from app.services import meal_logging
from tests.fakes import InMemoryMealRepository


@pytest.mark.asyncio
async def test_handle_incoming_photo_passes_downloaded_media_type_to_vision(monkeypatch):
    """Regression test: the mime_type returned by download_media must reach
    analyze_photo rather than silently falling back to vision.py's
    image/jpeg default — WhatsApp photos aren't guaranteed to be JPEG."""
    from app.db import pool as pool_module
    from app.services import vision
    from app.whatsapp import media as media_client

    class FakeRepo:
        async def find_open_meal(self, *args, **kwargs):
            return None

        async def create_meal(
            self, user_id, media_id, foods, total_calories, confidence, now, model_id=None
        ):
            return queries.MealRecord(
                id="meal-1",
                user_id=user_id,
                logged_at=now,
                photo_media_ids=[media_id],
                foods=foods,
                total_calories=total_calories,
                confidence=confidence,
                model_id=model_id,
            )

        async def get_time_zone(self, user_id):
            return "UTC"

        async def upsert_daily_total(self, *args, **kwargs):
            pass

    async def fake_get_pool():
        return object()

    async def fake_download_media(media_id):
        return b"fake-png-bytes", "image/png"

    captured = {}

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg"):
        captured["image_bytes"] = image_bytes
        captured["media_type"] = media_type
        return {
            "foods": [
                {
                    "name": "rice",
                    "portion_grams": 200,
                    "calories": 300,
                    "protein_g": 5,
                    "carbs_g": 60,
                    "fat_g": 1,
                }
            ],
            "total_calories": 300,
            "confidence": 0.9,
            "clarifying_question": None,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: FakeRepo())
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-99")

    assert captured["image_bytes"] == b"fake-png-bytes"
    assert captured["media_type"] == "image/png"


@pytest.mark.asyncio
async def test_clarifying_question_asks_instead_of_logging(monkeypatch):
    """Regression test found via live testing, then narrowed further (v2): a
    photo whose foods ARE all visible was still asking a clarifying question
    because the original gate was confidence<0.6 rather than the model's own
    clarifying_question field. Now gated purely on clarifying_question being
    set (reserved by calorie_vision.md v2 rule 6 for genuine occlusion) —
    when set, the pending question must be persisted and NOT logged as a
    meal, since the estimate is incomplete."""
    from app.db import pool as pool_module
    from app.services import vision
    from app.whatsapp import media as media_client

    class FailIfCalledRepo:
        async def find_open_meal(self, *args, **kwargs):
            raise AssertionError(
                "must not query for an open meal when a clarifying question is pending"
            )

        async def create_meal(self, *args, **kwargs):
            raise AssertionError("must not create a meal when a clarifying question is pending")

        async def append_to_meal(self, *args, **kwargs):
            raise AssertionError("must not append to a meal when a clarifying question is pending")

    async def fake_get_pool():
        return object()

    async def fake_download_media(media_id):
        return b"fake-bytes", "image/jpeg"

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg", clarification=None):
        # Realistic "genuine occlusion" case: the sandwich itself is visible
        # (foods is non-empty) but its filling is hidden, so a question is
        # asked rather than a wild guess at the filling.
        return {
            "foods": [
                {
                    "name": "sandwich (filling not visible)",
                    "portion_grams": 150,
                    "calories": 0,
                    "protein_g": 0,
                    "carbs_g": 0,
                    "fat_g": 0,
                }
            ],
            "total_calories": 0,
            "confidence": 0.4,
            "clarifying_question": "Is that filling meat or vegetable?",
        }

    pending_calls = {}

    async def fake_set_pending_clarification(pool, user_id, media_id, media_type, question):
        pending_calls["args"] = (user_id, media_id, media_type, question)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: FailIfCalledRepo())
    monkeypatch.setattr(queries, "set_pending_clarification", fake_set_pending_clarification)
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    reply = await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-99")

    assert reply == "Is that filling meat or vegetable?"
    assert pending_calls["args"] == (
        "user-1",
        "media-99",
        "image/jpeg",
        "Is that filling meat or vegetable?",
    )


@pytest.mark.asyncio
async def test_clarification_reply_completes_the_analysis(monkeypatch):
    """The other half of the loop: once a text reply answers a pending
    clarifying question, handle_clarification_reply must re-analyze the
    original photo with that answer and actually log a meal — this used to
    be a dead end with no code path to receive the answer at all."""
    from app.db import pool as pool_module
    from app.services import vision
    from app.whatsapp import media as media_client

    class FakeRepo:
        async def find_open_meal(self, *args, **kwargs):
            return None

        async def create_meal(
            self, user_id, media_id, foods, total_calories, confidence, now, model_id=None
        ):
            return queries.MealRecord(
                id="meal-clarified",
                user_id=user_id,
                logged_at=now,
                photo_media_ids=[media_id],
                foods=foods,
                total_calories=total_calories,
                confidence=confidence,
                model_id=model_id,
            )

        async def get_time_zone(self, user_id):
            return "UTC"

        async def upsert_daily_total(self, *args, **kwargs):
            pass

    async def fake_get_pool():
        return object()

    async def fake_get_pending_clarification(pool, user_id):
        return {"media_id": "media-99", "media_type": "image/jpeg", "question": "Meat or veg?"}

    cleared = {"called": False}

    async def fake_clear_pending_clarification(pool, user_id):
        cleared["called"] = True

    async def fake_download_media(media_id):
        return b"fake-bytes", "image/jpeg"

    captured = {}

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg", clarification=None):
        captured["clarification"] = clarification
        return {
            "foods": [
                {
                    "name": "vegetable stew",
                    "portion_grams": 250,
                    "calories": 220,
                    "protein_g": 6,
                    "carbs_g": 30,
                    "fat_g": 8,
                }
            ],
            "total_calories": 220,
            "confidence": 0.85,
            "clarifying_question": None,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: FakeRepo())
    monkeypatch.setattr(queries, "get_pending_clarification", fake_get_pending_clarification)
    monkeypatch.setattr(queries, "clear_pending_clarification", fake_clear_pending_clarification)
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    reply = await meal_logging.handle_clarification_reply("user-1", "15551234567", "It's vegetable")

    assert captured["clarification"] == "It's vegetable"
    assert cleared["called"] is True
    assert "kcal" in reply


@pytest.mark.asyncio
async def test_not_food_photo_never_updates_daily_total(monkeypatch):
    """spec 002-daily-total-tracking, FR-007: a photo not recognized as food
    must never contribute to daily_totals — it never reaches log_meal_photo
    at all, so there's nothing to increment."""
    from app.db import pool as pool_module
    from app.services import vision
    from app.whatsapp import media as media_client

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_download_media(media_id):
        return b"fake-bytes", "image/jpeg"

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg", clarification=None):
        return {"foods": [], "total_calories": 0, "confidence": None, "clarifying_question": None}

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    reply = await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-99")

    assert reply == meal_logging.NOT_FOOD_REPLY
    assert repo.daily_totals == {}


@pytest.mark.asyncio
async def test_clarification_reply_returns_none_when_nothing_pending(monkeypatch):
    from app.db import pool as pool_module

    async def fake_get_pool():
        return object()

    async def fake_get_pending_clarification(pool, user_id):
        return None

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_clarification", fake_get_pending_clarification)

    reply = await meal_logging.handle_clarification_reply("user-1", "15551234567", "random text")

    assert reply is None


@pytest.mark.asyncio
async def test_meal_is_attributed_to_the_live_model_and_unaffected_by_other_candidates(
    monkeypatch,
):
    """specs/003-vision-model-comparison User Story 3 / FR-008, FR-009: the
    created meal's model_id must equal settings.live_vision_model_id, and
    must be unaffected by other candidate models being registered (standing
    in for "a comparison run in progress" — the live path never reads
    anything about comparison state, only settings.live_vision_model_id, so
    isolation holds regardless of how many other candidates exist).

    This lives here rather than tests/contract/test_webhook_image.py because
    that suite mocks meal_logging.handle_incoming_photo entirely and never
    exercises a real repo.create_meal call — this is the only layer that can
    actually observe model_id attribution."""
    from app.db import pool as pool_module
    from app.services import vision, vision_models
    from app.whatsapp import media as media_client

    monkeypatch.setattr(settings, "live_vision_model_id", "claude-sonnet-5")
    monkeypatch.setitem(vision_models.MODEL_REGISTRY, "claude-opus-4-8", object())

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_download_media(media_id):
        return b"fake-bytes", "image/jpeg"

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg", clarification=None):
        return {
            "foods": [
                {
                    "name": "rice",
                    "portion_grams": 200,
                    "calories": 300,
                    "protein_g": 5,
                    "carbs_g": 60,
                    "fat_g": 1,
                }
            ],
            "total_calories": 300,
            "confidence": 0.9,
            "clarifying_question": None,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-99")

    [meal] = list(repo.meals.values())
    assert meal.model_id == "claude-sonnet-5"

    monkeypatch.setattr(settings, "live_vision_model_id", "claude-opus-4-8")
    await meal_logging.handle_incoming_photo("user-2", "15559876543", "media-100")

    meals_by_user = {m.user_id: m for m in repo.meals.values()}
    assert meals_by_user["user-2"].model_id == "claude-opus-4-8"
    assert meals_by_user["user-1"].model_id == "claude-sonnet-5"
