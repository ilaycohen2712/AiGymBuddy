import datetime as dt

import pytest

from app.services import daily_total


@pytest.mark.parametrize(
    "text",
    [
        "what's my total today?",
        "what's my total",
        "how many calories today",
        "how much have i eaten today",
        "so far today?",
        "today so far",
        "כמה אכלתי היום",
        "כמה קלוריות אכלתי",
        "סך הכל",
        "מה הסך הכל שלי",
    ],
)
def test_is_daily_total_request_recognizes_phrases(text):
    assert daily_total._is_daily_total_request(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "hi",
        "It's vegetable",
        "thanks!",
        "random chit chat",
        "כמה זה עולה",  # "how much does this cost" - unrelated Hebrew
    ],
)
def test_is_daily_total_request_rejects_unrelated_text(text):
    assert daily_total._is_daily_total_request(text) is False


@pytest.mark.asyncio
async def test_handle_daily_total_request_returns_none_without_touching_db_for_unmatched_text():
    # No monkeypatching of get_pool/queries at all — if this touched the DB
    # layer it would raise (no real DATABASE_URL configured for tests),
    # proving the short-circuit happens before any DB call.
    reply = await daily_total.handle_daily_total_request("user-1", "15551234567", "hello there")
    assert reply is None


@pytest.mark.asyncio
async def test_handle_daily_total_request_replies_with_range_from_stored_totals(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_user_time_zone(pool, user_id):
        return "UTC"

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 500.0, "protein_g": 30.0, "carbs_g": 60.0, "fat_g": 15.0}

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_user_time_zone", fake_get_user_time_zone)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)

    reply = await daily_total.handle_daily_total_request(
        "user-1", "15551234567", "what's my total?"
    )

    assert reply is not None
    assert "kcal" in reply
    assert "400" in reply  # 500 * 0.8
    assert "600" in reply  # 500 * 1.2


@pytest.mark.asyncio
async def test_handle_daily_total_request_zero_meals_gets_friendly_reply(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_user_time_zone(pool, user_id):
        return "UTC"

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_user_time_zone", fake_get_user_time_zone)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)

    reply = await daily_total.handle_daily_total_request("user-1", "15551234567", "my total?")

    assert reply is not None
    assert "kcal" not in reply
    assert "0-0" not in reply


def test_format_daily_total_reply_zero_case():
    reply = daily_total.format_daily_total_reply(
        {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    )
    assert "haven't logged" in reply.lower() or "nothing" in reply.lower()


def test_format_daily_total_reply_range_case():
    reply = daily_total.format_daily_total_reply(
        {"calories": 1000.0, "protein_g": 50.0, "carbs_g": 100.0, "fat_g": 30.0}
    )
    assert "800-1200" in reply
    assert "50" in reply
    assert "100" in reply
    assert "30" in reply


@pytest.mark.asyncio
async def test_total_request_resolves_today_using_users_own_time_zone(monkeypatch):
    """spec 002-daily-total-tracking, User Story 3: a request made just
    after a user's local midnight must resolve "today" as the NEW day, even
    though it's still the same UTC calendar day it was a moment before.
    Etc/GMT-3 (a fixed UTC+3 offset, no DST) keeps this deterministic."""
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_user_time_zone(pool, user_id):
        return "Etc/GMT-3"

    captured_dates = []

    async def fake_get_daily_total(pool, user_id, date):
        captured_dates.append(date)
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_user_time_zone", fake_get_user_time_zone)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)

    # 20:59 UTC on the 16th = 23:59 local (UTC+3) on the 16th — still the old day.
    before_midnight = dt.datetime(2026, 7, 16, 20, 59, tzinfo=dt.UTC)
    await daily_total.handle_daily_total_request(
        "user-1", "15551234567", "my total?", now=before_midnight
    )
    assert captured_dates[-1] == dt.date(2026, 7, 16)

    # 21:30 UTC on the 16th = 00:30 local (UTC+3) on the 17th — new day already.
    after_midnight = dt.datetime(2026, 7, 16, 21, 30, tzinfo=dt.UTC)
    await daily_total.handle_daily_total_request(
        "user-1", "15551234567", "my total?", now=after_midnight
    )
    assert captured_dates[-1] == dt.date(2026, 7, 17)


@pytest.mark.asyncio
async def test_two_users_in_different_time_zones_reset_independently(monkeypatch):
    """spec 002-daily-total-tracking, User Story 3, Acceptance Scenario 3:
    it becoming midnight for one user must not affect what "today" resolves
    to for another user in a different time zone, at the same real instant."""
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    time_zones = {"user-jerusalem": "Etc/GMT-3", "user-la": "Etc/GMT+8"}

    async def fake_get_user_time_zone(pool, user_id):
        return time_zones[user_id]

    captured = {}

    async def fake_get_daily_total(pool, user_id, date):
        captured[user_id] = date
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_user_time_zone", fake_get_user_time_zone)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)

    # 21:30 UTC: just after midnight in Etc/GMT-3 (00:30 on the 17th), but
    # still mid-afternoon the day before in Etc/GMT+8 (13:30 on the 16th).
    moment = dt.datetime(2026, 7, 16, 21, 30, tzinfo=dt.UTC)
    await daily_total.handle_daily_total_request(
        "user-jerusalem", "15551234567", "my total?", now=moment
    )
    await daily_total.handle_daily_total_request("user-la", "15559876543", "my total?", now=moment)

    assert captured["user-jerusalem"] == dt.date(2026, 7, 17)
    assert captured["user-la"] == dt.date(2026, 7, 16)


@pytest.mark.asyncio
async def test_meal_logged_just_before_local_midnight_stays_in_that_days_bucket():
    """spec 002-daily-total-tracking, User Story 3, Acceptance Scenario 2 /
    Edge Cases: a meal logged in the final minutes before a user's local
    midnight is attributed to the day in progress, not the day about to
    start."""
    from app.services import meal_logging
    from tests.fakes import InMemoryMealRepository

    repo = InMemoryMealRepository()
    user_id = "user-1"
    repo.time_zones[user_id] = "Etc/GMT-3"

    def _vision_result(calories: float) -> dict:
        return {
            "foods": [
                {
                    "name": "late snack",
                    "portion_grams": 100,
                    "calories": calories,
                    "protein_g": 5,
                    "carbs_g": 10,
                    "fat_g": 2,
                }
            ],
            "total_calories": calories,
            "confidence": 0.8,
            "clarifying_question": None,
        }

    # 20:59 UTC = 23:59 local (Etc/GMT-3) — still the 16th locally.
    before_midnight = dt.datetime(2026, 7, 16, 20, 59, tzinfo=dt.UTC)
    await meal_logging.log_meal_photo(
        user_id, "media-1", _vision_result(200), repo, now=before_midnight
    )

    assert (user_id, dt.date(2026, 7, 16)) in repo.daily_totals
    assert (user_id, dt.date(2026, 7, 17)) not in repo.daily_totals
