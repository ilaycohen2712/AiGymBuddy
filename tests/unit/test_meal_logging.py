import datetime as dt

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
            self,
            user_id,
            foods,
            total_calories,
            confidence,
            now,
            model_id=None,
            *,
            media_id=None,
            text_entry=None,
        ):
            return queries.MealRecord(
                id="meal-1",
                user_id=user_id,
                logged_at=now,
                photo_media_ids=[media_id] if media_id else [],
                text_entries=[text_entry] if text_entry else [],
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

    async def fake_set_pending_clarification(
        pool, user_id, media_type, question, *, media_id=None, text_body=None
    ):
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
            self,
            user_id,
            foods,
            total_calories,
            confidence,
            now,
            model_id=None,
            *,
            media_id=None,
            text_entry=None,
        ):
            return queries.MealRecord(
                id="meal-clarified",
                user_id=user_id,
                logged_at=now,
                photo_media_ids=[media_id] if media_id else [],
                text_entries=[text_entry] if text_entry else [],
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
async def test_text_clarification_reply_completes_the_analysis(monkeypatch):
    """specs/005-text-meal-logging, T016: the same completion path handles a
    text-originated pending clarification — no photo to re-download, so the
    original text_body is re-analyzed together with the user's answer, and
    logged with a combined text_entry (one round trip, same cap as photo)."""
    from app.db import pool as pool_module
    from app.services import text_analysis

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_get_pending_clarification(pool, user_id):
        return {
            "media_id": None,
            "media_type": "text",
            "text_body": "chicken and rice",
            "question": "About how much chicken and rice was that?",
        }

    cleared = {"called": False}

    async def fake_clear_pending_clarification(pool, user_id):
        cleared["called"] = True

    captured = {}

    async def fake_analyze_text(text, clarification=None):
        captured["text"] = text
        captured["clarification"] = clarification
        return {
            "foods": [
                {"name": "chicken", "portion_grams": 150, "calories": 250,
                 "protein_g": 46, "carbs_g": 0, "fat_g": 5},
                {"name": "rice", "portion_grams": 200, "calories": 260,
                 "protein_g": 5, "carbs_g": 56, "fat_g": 0},
            ],
            "total_calories": 510,
            "confidence": 0.85,
            "clarifying_question": None,
            "is_food_description": True,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(queries, "get_pending_clarification", fake_get_pending_clarification)
    monkeypatch.setattr(queries, "clear_pending_clarification", fake_clear_pending_clarification)
    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)

    reply = await meal_logging.handle_clarification_reply(
        "user-1", "15551234567", "150g chicken, 200g rice"
    )

    assert captured["text"] == "chicken and rice"
    assert captured["clarification"] == "150g chicken, 200g rice"
    assert cleared["called"] is True
    assert "kcal" in reply
    assert len(repo.meals) == 1
    meal = next(iter(repo.meals.values()))
    assert meal.photo_media_ids == []
    assert meal.text_entries == ["chicken and rice (clarified: 150g chicken, 200g rice)"]
    assert meal.total_calories == 510


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
async def test_clarification_reply_defers_on_safety_signal_without_touching_pending(monkeypatch):
    """Regression test (found live via coach-simulator, specs/005-text-meal-
    logging review): a safety-relevant reply to a pending clarification must
    defer to chat_fallback's safety escalation, not be swallowed by
    NOT_FOOD_REPLY or a meal-logged reply. The pending clarification itself
    must be left untouched (get_pending_clarification/clear_pending_clarification
    must never even be called), so the user can still answer it later."""
    from app.db import pool as pool_module

    called = {"get_pending": False}

    async def fake_get_pool():
        return object()

    async def fake_get_pending_clarification(pool, user_id):
        called["get_pending"] = True
        return {"media_id": "media-1", "media_type": "image/jpeg", "question": "How much?"}

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_clarification", fake_get_pending_clarification)

    reply = await meal_logging.handle_clarification_reply(
        "user-1", "15551234567", "honestly I haven't eaten in days"
    )

    assert reply is None
    assert called["get_pending"] is False


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


def test_format_range_reply_breaks_down_each_ingredient():
    """Requested (2026-07-24) after the user compared a bot reply against an
    external nutrition reference that showed a per-ingredient breakdown
    (feta cheese / tomatoes / olive oil, each with its own contribution)
    rather than one opaque total. The narrower ±10% range (also requested,
    same conversation) replaces the original ±20%."""
    meal = queries.MealRecord(
        id="meal-1",
        user_id="user-1",
        logged_at=None,
        photo_media_ids=["media-1"],
        foods=[
            {"name": "feta cheese", "portion_grams": 100, "calories": 220,
             "protein_g": 14, "carbs_g": 4, "fat_g": 18},
            {"name": "cherry tomatoes", "portion_grams": 150, "calories": 30,
             "protein_g": 1, "carbs_g": 6, "fat_g": 0},
            {"name": "olive oil", "portion_grams": 14, "calories": 120,
             "protein_g": 0, "carbs_g": 0, "fat_g": 14},
        ],
        total_calories=370,
    )

    reply = meal_logging.format_range_reply(meal)

    assert reply == (
        "Feta cheese: ~198-242 kcal\n"
        "Cherry tomatoes: ~27-33 kcal\n"
        "Olive oil: ~108-132 kcal\n"
        "Total: ~333-407 kcal (protein ~15g, carbs ~10g, fat ~32g)."
    )


def test_format_range_reply_single_food_collapses_to_one_line():
    """coach-simulator finding: showing the item and the Total on separate
    lines with the identical number reads as mechanical repetition for a
    single-food photo — collapse to one line instead."""
    meal = queries.MealRecord(
        id="meal-1",
        user_id="user-1",
        logged_at=None,
        photo_media_ids=["media-1"],
        foods=[{"name": "grilled chicken breast", "portion_grams": 150, "calories": 250,
                "protein_g": 40, "carbs_g": 0, "fat_g": 12}],
        total_calories=250,
    )

    reply = meal_logging.format_range_reply(meal)

    assert reply == "Grilled chicken breast: ~225-275 kcal (protein ~40g, carbs ~0g, fat ~12g)."


def test_format_item_and_meal_reply_single_item_collapses_added_line():
    """Same collapsing logic as format_range_reply, applied to the
    appended-photo case: a single-item photo (e.g. a zero-calorie drink)
    gets one "X: ~Y kcal added." line, not a redundant item-line + Added-line
    pair showing the same number twice."""
    meal = queries.MealRecord(
        id="meal-1",
        user_id="user-1",
        logged_at=None,
        photo_media_ids=["media-1", "media-2"],
        foods=[
            {"name": "salad", "portion_grams": 200, "calories": 350, "protein_g": 18,
             "carbs_g": 11, "fat_g": 30},
        ],
        total_calories=350,
    )
    item_result = {
        "total_calories": 0,
        "foods": [{"name": "diet soda", "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}],
    }

    reply = meal_logging.format_item_and_meal_reply(item_result, meal)

    assert reply == (
        "Diet soda: 0 kcal added.\n"
        "Meal total: ~315-385 kcal (protein ~18g, carbs ~11g, fat ~30g)."
    )


def test_format_item_and_meal_reply_multi_item_photo_keeps_full_breakdown():
    """When an appended photo itself has 2+ distinct foods, the per-item
    breakdown is genuinely informative (not redundant with the Added line),
    so it's kept in full — only the single-item case collapses."""
    meal = queries.MealRecord(
        id="meal-1",
        user_id="user-1",
        logged_at=None,
        photo_media_ids=["media-1", "media-2"],
        foods=[
            {"name": "rice", "calories": 100, "protein_g": 5, "carbs_g": 60, "fat_g": 1,
             "portion_grams": 200},
            {"name": "bread", "calories": 200, "protein_g": 6, "carbs_g": 35, "fat_g": 2,
             "portion_grams": 60},
        ],
        total_calories=300,
    )
    item_result = {
        "total_calories": 200,
        "foods": [
            {"name": "bread", "calories": 150, "protein_g": 5, "carbs_g": 30, "fat_g": 1,
             "portion_grams": 50},
            {"name": "butter", "calories": 50, "protein_g": 0, "carbs_g": 0, "fat_g": 6,
             "portion_grams": 7},
        ],
    }

    reply = meal_logging.format_item_and_meal_reply(item_result, meal)

    assert reply == (
        "Bread: ~135-165 kcal\n"
        "Butter: ~45-55 kcal\n"
        "Added: ~180-220 kcal\n"
        "Meal total: ~270-330 kcal (protein ~11g, carbs ~95g, fat ~3g)."
    )


@pytest.mark.asyncio
async def test_second_photo_in_a_meal_gets_item_and_running_total_inline(monkeypatch):
    """Requested after live testing: sending a second photo into an already-
    open meal (e.g. a zero-calorie drink added to a logged salad) previously
    replied with only the updated meal total, giving no acknowledgment of
    the just-sent photo itself. Now: the first photo of a meal still gets
    the plain range reply; every additional photo gets both its own
    contribution and the updated running total, inline in one message."""
    from app.db import pool as pool_module
    from app.services import vision
    from app.whatsapp import media as media_client

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_download_media(media_id):
        return b"fake-bytes", "image/jpeg"

    responses = iter(
        [
            {
                "foods": [{"name": "salad", "portion_grams": 200, "calories": 380,
                           "protein_g": 18, "carbs_g": 11, "fat_g": 30}],
                "total_calories": 380,
                "confidence": 0.8,
                "clarifying_question": None,
            },
            {
                "foods": [{"name": "diet soda", "portion_grams": 330, "calories": 0,
                           "protein_g": 0, "carbs_g": 0, "fat_g": 0}],
                "total_calories": 0,
                "confidence": 0.9,
                "clarifying_question": None,
            },
        ]
    )

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg", clarification=None):
        return next(responses)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    first_reply = await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-1")
    second_reply = await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-2")

    assert first_reply == "Salad: ~342-418 kcal (protein ~18g, carbs ~11g, fat ~30g)."
    assert second_reply == (
        "Diet soda: 0 kcal added.\n"
        "Meal total: ~342-418 kcal (protein ~18g, carbs ~11g, fat ~30g)."
    )


@pytest.mark.asyncio
async def test_repo_create_meal_accepts_text_entry_with_no_media_id():
    """Regression test for specs/005-text-meal-logging: a meal can now
    originate from a typed description instead of a photo — create_meal must
    persist that with an empty photo_media_ids and a populated text_entries,
    not require a media_id."""
    repo = InMemoryMealRepository()
    now = dt.datetime(2026, 7, 25, 12, 0, tzinfo=dt.UTC)

    meal = await repo.create_meal(
        "user-1",
        [{"name": "rice", "portion_grams": 100, "calories": 130,
          "protein_g": 3, "carbs_g": 28, "fat_g": 0}],
        130,
        0.9,
        now,
        text_entry="100 grams rice",
    )

    assert meal.photo_media_ids == []
    assert meal.text_entries == ["100 grams rice"]


@pytest.mark.asyncio
async def test_repo_append_to_meal_mixes_photo_and_text_contributions():
    """A meal started by a photo can be appended to by a text description
    (and vice versa) — both arrays accumulate independently, in order."""
    repo = InMemoryMealRepository()
    now = dt.datetime(2026, 7, 25, 12, 0, tzinfo=dt.UTC)

    meal = await repo.create_meal(
        "user-1", [{"name": "chicken", "calories": 200}], 200, 0.9, now, media_id="media-1"
    )
    meal = await repo.append_to_meal(
        meal, [{"name": "rice", "calories": 130}], 130, 0.9, text_entry="100 grams rice"
    )

    assert meal.photo_media_ids == ["media-1"]
    assert meal.text_entries == ["100 grams rice"]
    assert meal.total_calories == 330
