import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.scheduler import eod_trigger


def _user(
    *,
    user_id: str = "user-1",
    wa_phone: str = "15551234567",
    time_zone: str = "UTC",
    daily_calorie_target: int | None = 2000,
) -> dict:
    return {
        "id": uuid.UUID(int=1) if user_id == "user-1" else uuid.uuid4(),
        "wa_phone": wa_phone,
        "time_zone": time_zone,
        "daily_calorie_target": daily_calorie_target,
    }


@pytest.mark.asyncio
async def test_run_eod_trigger_skips_users_outside_report_hour(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    monkeypatch.setattr(settings, "eod_report_hour", 21)

    async def fake_get_pool():
        return object()

    async def fake_get_users_for_eod_check(pool):
        return [_user(time_zone="UTC")]

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_users_for_eod_check", fake_get_users_for_eod_check)

    now = dt.datetime(2026, 7, 25, 10, 0, tzinfo=dt.UTC)  # 10:00 UTC, not 21:00
    handled = await eod_trigger.run_eod_trigger(now)

    assert handled == 0


@pytest.mark.asyncio
async def test_run_eod_trigger_sends_target_ask_when_no_target_set(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries
    from app.services import daily_target
    from app.whatsapp import templates

    monkeypatch.setattr(settings, "eod_report_hour", 21)

    async def fake_get_pool():
        return object()

    async def fake_get_users_for_eod_check(pool):
        return [_user(time_zone="UTC", daily_calorie_target=None)]

    async def fake_get_pending_daily_target_ask(pool, user_id):
        return None

    asked = {"called": False}

    async def fake_send_target_ask(user_id, wa_phone):
        asked["called"] = True
        return daily_target.TARGET_ASK

    sent = {}

    async def fake_send_proactive_message(to, body):
        sent["args"] = (to, body)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_users_for_eod_check", fake_get_users_for_eod_check)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)
    monkeypatch.setattr(daily_target, "send_target_ask", fake_send_target_ask)
    monkeypatch.setattr(templates, "send_proactive_message", fake_send_proactive_message)

    now = dt.datetime(2026, 7, 25, 21, 5, tzinfo=dt.UTC)
    handled = await eod_trigger.run_eod_trigger(now)

    assert handled == 1
    assert asked["called"] is True
    assert sent["args"] == ("15551234567", daily_target.TARGET_ASK)


@pytest.mark.asyncio
async def test_run_eod_trigger_does_not_re_ask_within_the_same_local_day(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries
    from app.services import daily_target

    monkeypatch.setattr(settings, "eod_report_hour", 21)

    async def fake_get_pool():
        return object()

    async def fake_get_users_for_eod_check(pool):
        return [_user(time_zone="UTC", daily_calorie_target=None)]

    async def fake_get_pending_daily_target_ask(pool, user_id):
        # Already asked earlier today, same UTC calendar day as `now` below.
        return dt.datetime(2026, 7, 25, 9, 0, tzinfo=dt.UTC)

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("must not re-ask within the same local day")

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_users_for_eod_check", fake_get_users_for_eod_check)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)
    monkeypatch.setattr(daily_target, "send_target_ask", fail_if_called)

    now = dt.datetime(2026, 7, 25, 21, 5, tzinfo=dt.UTC)
    handled = await eod_trigger.run_eod_trigger(now)

    assert handled == 0


@pytest.mark.asyncio
async def test_run_eod_trigger_sends_report_when_target_is_set(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries
    from app.services import eod_report
    from app.whatsapp import templates

    monkeypatch.setattr(settings, "eod_report_hour", 21)

    async def fake_get_pool():
        return object()

    async def fake_get_users_for_eod_check(pool):
        return [_user(time_zone="UTC", daily_calorie_target=2000)]

    async def fake_has_daily_report_for_date(pool, user_id, date):
        return False

    async def fake_send_report(user_id, wa_phone, date):
        return "Today's total: ...\nGreat job today!"

    sent = {}

    async def fake_send_proactive_message(to, body):
        sent["args"] = (to, body)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_users_for_eod_check", fake_get_users_for_eod_check)
    monkeypatch.setattr(queries, "has_daily_report_for_date", fake_has_daily_report_for_date)
    monkeypatch.setattr(eod_report, "send_report", fake_send_report)
    monkeypatch.setattr(templates, "send_proactive_message", fake_send_proactive_message)

    now = dt.datetime(2026, 7, 25, 21, 5, tzinfo=dt.UTC)
    handled = await eod_trigger.run_eod_trigger(now)

    assert handled == 1
    assert sent["args"][0] == "15551234567"


@pytest.mark.asyncio
async def test_run_eod_trigger_skips_when_report_already_sent(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    monkeypatch.setattr(settings, "eod_report_hour", 21)

    async def fake_get_pool():
        return object()

    async def fake_get_users_for_eod_check(pool):
        return [_user(time_zone="UTC", daily_calorie_target=2000)]

    async def fake_has_daily_report_for_date(pool, user_id, date):
        return True

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("must not generate a second report for the same day")

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_users_for_eod_check", fake_get_users_for_eod_check)
    monkeypatch.setattr(queries, "has_daily_report_for_date", fake_has_daily_report_for_date)

    from app.services import eod_report

    monkeypatch.setattr(eod_report, "send_report", fail_if_called)

    now = dt.datetime(2026, 7, 25, 21, 5, tzinfo=dt.UTC)
    handled = await eod_trigger.run_eod_trigger(now)

    assert handled == 0


@pytest.mark.asyncio
async def test_run_eod_trigger_continues_after_one_users_failure(monkeypatch):
    """One user's failure (e.g. a bad LLM response) must not stop the whole
    run — every other user still gets handled in the same invocation."""
    from app.db import pool as pool_module
    from app.db import queries
    from app.services import eod_report
    from app.whatsapp import templates

    monkeypatch.setattr(settings, "eod_report_hour", 21)

    async def fake_get_pool():
        return object()

    failing_user = _user(user_id="user-1", wa_phone="15551111111", time_zone="UTC")
    ok_user = _user(user_id="user-2", wa_phone="15552222222", time_zone="UTC")

    async def fake_get_users_for_eod_check(pool):
        return [failing_user, ok_user]

    async def fake_has_daily_report_for_date(pool, user_id, date):
        return False

    async def fake_send_report(user_id, wa_phone, date):
        if wa_phone == "15551111111":
            raise ValueError("boom")
        return "report text"

    sent = []

    async def fake_send_proactive_message(to, body):
        sent.append(to)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_users_for_eod_check", fake_get_users_for_eod_check)
    monkeypatch.setattr(queries, "has_daily_report_for_date", fake_has_daily_report_for_date)
    monkeypatch.setattr(eod_report, "send_report", fake_send_report)
    monkeypatch.setattr(templates, "send_proactive_message", fake_send_proactive_message)

    now = dt.datetime(2026, 7, 25, 21, 5, tzinfo=dt.UTC)
    handled = await eod_trigger.run_eod_trigger(now)

    assert handled == 1
    assert sent == ["15552222222"]


def test_trigger_endpoint_rejects_without_configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_secret", "")
    client = TestClient(app)

    resp = client.post("/internal/eod-trigger", headers={"X-Scheduler-Secret": "anything"})

    assert resp.status_code == 403


def test_trigger_endpoint_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_secret", "correct-secret")
    client = TestClient(app)

    resp = client.post("/internal/eod-trigger", headers={"X-Scheduler-Secret": "wrong"})

    assert resp.status_code == 403


def test_trigger_endpoint_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_secret", "correct-secret")

    async def fake_run_eod_trigger(now=None):
        return 3

    monkeypatch.setattr(eod_trigger, "run_eod_trigger", fake_run_eod_trigger)

    client = TestClient(app)
    resp = client.post(
        "/internal/eod-trigger", headers={"X-Scheduler-Secret": "correct-secret"}
    )

    assert resp.status_code == 200
    assert resp.json() == {"handled": 3}
