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
async def test_grouping_window_is_anchored_to_first_photo_not_sliding():
    """Regression test for a bug found via live multi-photo testing: a
    sliding window (refreshing on every append) let a meal stay open
    indefinitely as long as *some* photo arrived within 10 min of the
    *previous* one, silently merging unrelated meals across a long test
    session. The window must be anchored to the first photo instead: a photo
    9 min after the first joins, but one 11 min after the first does NOT,
    even though it's only 2 min after the second photo."""
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
        user_id, "media-3", _vision_result("salad", 100), repo, now=t0 + dt.timedelta(minutes=11)
    )

    assert first.id == second.id
    assert second.photo_media_ids == ["media-1", "media-2"]
    assert second.total_calories == 550

    assert third.id != first.id
    assert third.photo_media_ids == ["media-3"]
    assert third.total_calories == 100


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
