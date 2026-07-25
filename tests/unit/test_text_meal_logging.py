import pytest

from app.db import queries
from app.services import text_meal_logging
from tests.fakes import InMemoryMealRepository


@pytest.mark.asyncio
async def test_clear_food_description_logs_meal_and_replies_with_range(monkeypatch):
    """User Story 1, scenario 1: a text description with stated quantities
    for every item is estimated, logged as a new meal, and replied to with
    a calorie-range reply — same shape as a photo-based reply."""
    from app.db import pool as pool_module
    from app.services import text_analysis

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_analyze_text(text, clarification=None):
        return {
            "foods": [
                {"name": "rice", "portion_grams": 100, "calories": 130,
                 "protein_g": 3, "carbs_g": 28, "fat_g": 0},
                {"name": "chicken breast", "portion_grams": 120, "calories": 200,
                 "protein_g": 37, "carbs_g": 0, "fat_g": 4},
            ],
            "total_calories": 330,
            "confidence": 0.9,
            "clarifying_question": None,
            "is_food_description": True,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)

    reply = await text_meal_logging.handle_text_meal_description(
        "user-1", "15551234567", "100 grams rice, 120 grams chicken breast"
    )

    assert reply is not None
    assert "kcal" in reply
    assert "Rice" in reply and "Chicken breast" in reply
    assert len(repo.meals) == 1
    meal = next(iter(repo.meals.values()))
    assert meal.text_entries == ["100 grams rice, 120 grams chicken breast"]
    assert meal.photo_media_ids == []
    assert meal.total_calories == 330


@pytest.mark.asyncio
async def test_non_food_text_returns_none_to_defer(monkeypatch):
    """is_food_description: false must defer to the next dispatch layer
    (contracts/text-dispatch-precedence.md) — never a reply from this
    module, and no meal logged."""
    from app.db import pool as pool_module
    from app.services import text_analysis

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_analyze_text(text, clarification=None):
        return {
            "foods": [],
            "total_calories": 0,
            "confidence": 0.0,
            "clarifying_question": None,
            "is_food_description": False,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)

    reply = await text_meal_logging.handle_text_meal_description(
        "user-1", "15551234567", "how's it going"
    )

    assert reply is None
    assert repo.meals == {}


@pytest.mark.asyncio
async def test_text_appends_to_already_open_meal(monkeypatch):
    """User Story 1, scenario 2: a text description sent while a meal is
    still open (photo- or text-originated) appends to it, using the same
    grouping window as photo-to-photo, rather than starting a new meal."""
    import datetime as dt

    from app.db import pool as pool_module
    from app.services import text_analysis

    repo = InMemoryMealRepository()
    now = dt.datetime(2026, 7, 25, 12, 0, tzinfo=dt.UTC)
    await repo.create_meal(
        "user-1",
        [{"name": "salad", "calories": 300, "protein_g": 10, "carbs_g": 20, "fat_g": 15}],
        300,
        0.9,
        now,
        media_id="media-1",
    )

    async def fake_get_pool():
        return object()

    async def fake_analyze_text(text, clarification=None):
        return {
            "foods": [{"name": "diet coke", "portion_grams": 330, "calories": 0,
                       "protein_g": 0, "carbs_g": 0, "fat_g": 0}],
            "total_calories": 0,
            "confidence": 0.9,
            "clarifying_question": None,
            "is_food_description": True,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)

    reply = await text_meal_logging.handle_text_meal_description(
        "user-1", "15551234567", "a diet coke"
    )

    assert len(repo.meals) == 1
    meal = next(iter(repo.meals.values()))
    assert meal.photo_media_ids == ["media-1"]
    assert meal.text_entries == ["a diet coke"]
    assert meal.total_calories == 300
    assert "Meal total" in reply


@pytest.mark.asyncio
async def test_hebrew_text_input_is_logged_the_same_way(monkeypatch):
    """FR-006: Hebrew text input is estimated and logged the same as the
    English equivalent — the dispatch logic doesn't branch on language."""
    from app.db import pool as pool_module
    from app.services import text_analysis

    repo = InMemoryMealRepository()

    async def fake_get_pool():
        return object()

    async def fake_analyze_text(text, clarification=None):
        return {
            "foods": [
                {"name": "אורז", "portion_grams": 150, "calories": 195,
                 "protein_g": 4, "carbs_g": 42, "fat_g": 0},
                {"name": "חזה עוף", "portion_grams": 100, "calories": 165,
                 "protein_g": 31, "carbs_g": 0, "fat_g": 4},
            ],
            "total_calories": 360,
            "confidence": 0.9,
            "clarifying_question": None,
            "is_food_description": True,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)

    reply = await text_meal_logging.handle_text_meal_description(
        "user-1", "15551234567", "150 גרם אורז ו-100 גרם חזה עוף"
    )

    assert reply is not None
    assert len(repo.meals) == 1
    meal = next(iter(repo.meals.values()))
    assert meal.total_calories == 360


@pytest.mark.asyncio
async def test_missing_quantity_sets_clarifying_question_and_does_not_log(monkeypatch):
    """FR-012: a food description with a materially missing quantity asks a
    clarifying question instead of guessing, and does not log a meal."""
    from app.db import pool as pool_module
    from app.services import text_analysis

    repo = InMemoryMealRepository()
    pending_calls = {}

    async def fake_get_pool():
        return object()

    async def fake_analyze_text(text, clarification=None):
        return {
            "foods": [],
            "total_calories": 0,
            "confidence": 0.3,
            "clarifying_question": "About how much chicken and rice was that?",
            "is_food_description": True,
        }

    async def fake_set_pending_clarification(
        pool, user_id, media_type, question, *, media_id=None, text_body=None
    ):
        pending_calls["args"] = (user_id, media_type, question, media_id, text_body)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: repo)
    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)
    monkeypatch.setattr(queries, "set_pending_clarification", fake_set_pending_clarification)

    reply = await text_meal_logging.handle_text_meal_description(
        "user-1", "15551234567", "chicken and rice"
    )

    assert reply == "About how much chicken and rice was that?"
    assert repo.meals == {}
    assert pending_calls["args"] == (
        "user-1",
        "text",
        "About how much chicken and rice was that?",
        None,
        "chicken and rice",
    )


@pytest.mark.asyncio
async def test_safety_signal_defers_without_calling_analyze_text(monkeypatch):
    """FR-008/research.md #2: a safety-relevant message must never reach the
    estimation model at all — checked first, and deferred (None) on a hit."""
    from app.services import text_analysis

    called = {"analyze_text": False}

    async def fake_analyze_text(text, clarification=None):
        called["analyze_text"] = True
        return {
            "foods": [], "total_calories": 0, "confidence": 0.0,
            "clarifying_question": None, "is_food_description": False,
        }

    monkeypatch.setattr(text_analysis, "analyze_text", fake_analyze_text)

    reply = await text_meal_logging.handle_text_meal_description(
        "user-1", "15551234567", "I haven't eaten in days"
    )

    assert reply is None
    assert called["analyze_text"] is False
