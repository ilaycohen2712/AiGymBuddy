import datetime as dt

import pytest

from app.services import meal_logging
from tests.fakes import InMemoryMealRepository


def _vision_result(name: str, calories: float, confidence: float = 0.8) -> dict:
    return {
        "foods": [
            {
                "name": name,
                "portion_grams": 200,
                "calories": calories,
                "protein_g": 10,
                "carbs_g": 20,
                "fat_g": 5,
            }
        ],
        "total_calories": calories,
        "confidence": confidence,
        "clarifying_question": None,
    }


@pytest.mark.asyncio
async def test_two_photos_within_window_combine_into_one_meal():
    repo = InMemoryMealRepository()
    user_id = "user-1"
    t0 = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.UTC)

    first = await meal_logging.log_meal_photo(
        user_id, "media-1", _vision_result("rice", 300), repo, now=t0
    )
    second = await meal_logging.log_meal_photo(
        user_id, "media-2", _vision_result("chicken", 250), repo, now=t0 + dt.timedelta(minutes=5)
    )

    assert first.id == second.id
    assert second.photo_media_ids == ["media-1", "media-2"]
    assert second.total_calories == 550
    assert len(second.foods) == 2


@pytest.mark.asyncio
async def test_photo_outside_window_starts_new_meal():
    repo = InMemoryMealRepository()
    user_id = "user-1"
    t0 = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.UTC)

    first = await meal_logging.log_meal_photo(
        user_id, "media-1", _vision_result("rice", 300), repo, now=t0
    )
    second = await meal_logging.log_meal_photo(
        user_id, "media-2", _vision_result("salad", 150), repo, now=t0 + dt.timedelta(minutes=30)
    )

    assert first.id != second.id
    assert second.photo_media_ids == ["media-2"]
    assert second.total_calories == 150


@pytest.mark.asyncio
async def test_different_users_never_share_a_meal():
    repo = InMemoryMealRepository()
    t0 = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.UTC)

    meal_a = await meal_logging.log_meal_photo(
        "user-a", "media-1", _vision_result("rice", 300), repo, now=t0
    )
    meal_b = await meal_logging.log_meal_photo(
        "user-b", "media-2", _vision_result("rice", 300), repo, now=t0 + dt.timedelta(minutes=1)
    )

    assert meal_a.id != meal_b.id


@pytest.mark.asyncio
async def test_grouping_window_slides_with_each_new_photo():
    """A third photo 9 minutes after the second (14 min after the first)
    still joins the same meal — the window refreshes on each photo rather
    than being anchored only to the first one."""
    repo = InMemoryMealRepository()
    user_id = "user-1"
    t0 = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.UTC)

    first = await meal_logging.log_meal_photo(
        user_id, "media-1", _vision_result("rice", 300), repo, now=t0
    )
    second = await meal_logging.log_meal_photo(
        user_id, "media-2", _vision_result("chicken", 250), repo, now=t0 + dt.timedelta(minutes=9)
    )
    third = await meal_logging.log_meal_photo(
        user_id, "media-3", _vision_result("salad", 100), repo, now=t0 + dt.timedelta(minutes=18)
    )

    assert first.id == second.id == third.id
    assert third.photo_media_ids == ["media-1", "media-2", "media-3"]
    assert third.total_calories == 650


@pytest.mark.asyncio
async def test_combined_meal_confidence_is_the_minimum_of_its_photos():
    repo = InMemoryMealRepository()
    user_id = "user-1"
    t0 = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.UTC)

    await meal_logging.log_meal_photo(
        user_id, "media-1", _vision_result("rice", 300, confidence=0.9), repo, now=t0
    )
    second = await meal_logging.log_meal_photo(
        user_id,
        "media-2",
        _vision_result("chicken", 250, confidence=0.4),
        repo,
        now=t0 + dt.timedelta(minutes=5),
    )

    assert second.confidence == 0.4
