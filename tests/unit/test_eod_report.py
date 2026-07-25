import pytest

from app.services import eod_report


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, reply_text: str) -> None:
        self._reply_text = reply_text

    async def create(self, **kwargs):
        return _FakeResponse(self._reply_text)


class _FakeClient:
    def __init__(self, reply_text: str) -> None:
        self.messages = _FakeMessages(reply_text)


@pytest.mark.asyncio
async def test_generate_feedback_returns_validated_schema(monkeypatch):
    async def fake_get_client():
        return _FakeClient('{"feedback_text": "Nice work today!", "tone": "encouraging"}')

    monkeypatch.setattr(eod_report, "_get_client", fake_get_client)

    result = await eod_report.generate_feedback(
        {"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0}, 2000
    )

    assert result == {"feedback_text": "Nice work today!", "tone": "encouraging"}


@pytest.mark.asyncio
async def test_generate_feedback_raises_on_invalid_tone(monkeypatch):
    async def fake_get_client():
        return _FakeClient('{"feedback_text": "ok", "tone": "critical"}')

    monkeypatch.setattr(eod_report, "_get_client", fake_get_client)

    with pytest.raises(ValueError):
        await eod_report.generate_feedback(
            {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}, 2000
        )


@pytest.mark.asyncio
async def test_generate_feedback_truncates_overlong_text(monkeypatch):
    long_text = "x" * 700

    async def fake_get_client():
        return _FakeClient(f'{{"feedback_text": "{long_text}", "tone": "neutral"}}')

    monkeypatch.setattr(eod_report, "_get_client", fake_get_client)

    result = await eod_report.generate_feedback(
        {"calories": 3000.0, "protein_g": 100.0, "carbs_g": 300.0, "fat_g": 100.0}, 2000
    )

    assert len(result["feedback_text"]) == eod_report.FEEDBACK_MAX_CHARS


def test_format_report_message_reuses_daily_total_formatting():
    totals = {"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0}

    message = eod_report.format_report_message(totals, "Great consistency today!")

    assert "1440" in message  # 1800 * 0.8
    assert "2160" in message  # 1800 * 1.2
    assert message.endswith("Great consistency today!")


def test_format_report_message_zero_meal_day_uses_friendly_totals_line():
    totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    message = eod_report.format_report_message(totals, "Tomorrow's a fresh start!")

    assert "haven't logged any meals yet today" in message
    assert message.endswith("Tomorrow's a fresh start!")


@pytest.mark.asyncio
async def test_send_report_raises_without_a_target(monkeypatch):
    import datetime as dt

    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    async def fake_get_daily_calorie_target(pool, user_id):
        return None

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(queries, "get_daily_calorie_target", fake_get_daily_calorie_target)

    with pytest.raises(ValueError):
        await eod_report.send_report("user-1", "15551234567", dt.date(2026, 7, 25))


@pytest.mark.asyncio
async def test_send_report_composes_and_records_report(monkeypatch):
    import datetime as dt

    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0}

    async def fake_get_daily_calorie_target(pool, user_id):
        return 2000

    async def fake_generate_feedback(totals, target):
        return {"feedback_text": "Solid day, keep it up!", "tone": "encouraging"}

    recorded = {}

    async def fake_insert_daily_report(pool, user_id, date, **kwargs):
        recorded["args"] = (user_id, date, kwargs)
        return True

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(queries, "get_daily_calorie_target", fake_get_daily_calorie_target)
    monkeypatch.setattr(eod_report, "generate_feedback", fake_generate_feedback)
    monkeypatch.setattr(queries, "insert_daily_report", fake_insert_daily_report)

    today = dt.date(2026, 7, 25)
    message = await eod_report.send_report("user-1", "15551234567", today)

    assert message is not None
    assert "Solid day, keep it up!" in message
    assert recorded["args"][0] == "user-1"
    assert recorded["args"][1] == today
    assert recorded["args"][2]["feedback_text"] == "Solid day, keep it up!"


@pytest.mark.asyncio
async def test_send_report_returns_none_when_already_recorded(monkeypatch):
    import datetime as dt

    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 500.0, "protein_g": 10.0, "carbs_g": 50.0, "fat_g": 10.0}

    async def fake_get_daily_calorie_target(pool, user_id):
        return 2000

    async def fake_generate_feedback(totals, target):
        return {"feedback_text": "Nice start!", "tone": "encouraging"}

    async def fake_insert_daily_report(pool, user_id, date, **kwargs):
        return False  # a near-simultaneous run already inserted this row

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(queries, "get_daily_calorie_target", fake_get_daily_calorie_target)
    monkeypatch.setattr(eod_report, "generate_feedback", fake_generate_feedback)
    monkeypatch.setattr(queries, "insert_daily_report", fake_insert_daily_report)

    message = await eod_report.send_report("user-1", "15551234567", dt.date(2026, 7, 25))

    assert message is None
