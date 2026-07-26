import pytest

from app.services import eod_report


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, reply_text: str) -> None:
        self._reply_text = reply_text

    async def generate_content(self, **kwargs):
        return _FakeResponse(self._reply_text)


class _FakeAio:
    def __init__(self, reply_text: str) -> None:
        self.models = _FakeModels(reply_text)


class _FakeClient:
    def __init__(self, reply_text: str) -> None:
        self.aio = _FakeAio(reply_text)


@pytest.mark.asyncio
async def test_generate_feedback_returns_validated_schema(monkeypatch):
    async def fake_get_client():
        return _FakeClient('{"feedback_text": "Nice work today!", "tone": "encouraging"}')

    monkeypatch.setattr(eod_report.gemini_client, "get_client", fake_get_client)

    result = await eod_report.generate_feedback(
        {"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0}, 2000
    )

    assert result == {"feedback_text": "Nice work today!", "tone": "encouraging"}


@pytest.mark.asyncio
async def test_generate_feedback_raises_on_invalid_tone(monkeypatch):
    async def fake_get_client():
        return _FakeClient('{"feedback_text": "ok", "tone": "critical"}')

    monkeypatch.setattr(eod_report.gemini_client, "get_client", fake_get_client)

    with pytest.raises(ValueError):
        await eod_report.generate_feedback(
            {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}, 2000
        )


@pytest.mark.asyncio
async def test_generate_feedback_truncates_overlong_text(monkeypatch):
    long_text = "x" * 700

    async def fake_get_client():
        return _FakeClient(f'{{"feedback_text": "{long_text}", "tone": "neutral"}}')

    monkeypatch.setattr(eod_report.gemini_client, "get_client", fake_get_client)

    result = await eod_report.generate_feedback(
        {"calories": 3000.0, "protein_g": 100.0, "carbs_g": 300.0, "fat_g": 100.0}, 2000
    )

    assert len(result["feedback_text"]) == eod_report.FEEDBACK_MAX_CHARS


def test_format_report_message_reuses_daily_total_formatting():
    totals = {"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0}

    message = eod_report.format_report_message(totals, "Great consistency today!")

    assert "1620" in message  # 1800 * 0.9
    assert "1980" in message  # 1800 * 1.1
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

    async def fake_has_daily_report_for_date(pool, user_id, date):
        return False

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    async def fake_get_daily_calorie_target(pool, user_id):
        return None

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "has_daily_report_for_date", fake_has_daily_report_for_date)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(queries, "get_daily_calorie_target", fake_get_daily_calorie_target)

    with pytest.raises(ValueError):
        await eod_report.build_report("user-1", "15551234567", dt.date(2026, 7, 25))


@pytest.mark.asyncio
async def test_build_report_composes_a_draft_without_recording_it(monkeypatch):
    """build_report must not write to daily_reports itself — reviewer-flagged
    bug found live: the previous version recorded the report as sent before
    the WhatsApp send was ever attempted, so a delivery failure permanently
    lost that day's report. Only record_report_sent (below), called by the
    scheduler after a successful send, may persist it."""
    import datetime as dt

    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_has_daily_report_for_date(pool, user_id, date):
        return False

    async def fake_get_daily_total(pool, user_id, date):
        return {"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0}

    async def fake_get_daily_calorie_target(pool, user_id):
        return 2000

    async def fake_generate_feedback(totals, target):
        return {"feedback_text": "Solid day, keep it up!", "tone": "encouraging"}

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("build_report must not write to daily_reports")

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "has_daily_report_for_date", fake_has_daily_report_for_date)
    monkeypatch.setattr(queries, "get_daily_total", fake_get_daily_total)
    monkeypatch.setattr(queries, "get_daily_calorie_target", fake_get_daily_calorie_target)
    monkeypatch.setattr(eod_report, "generate_feedback", fake_generate_feedback)
    monkeypatch.setattr(queries, "insert_daily_report", fail_if_called)

    today = dt.date(2026, 7, 25)
    draft = await eod_report.build_report("user-1", "15551234567", today)

    assert draft is not None
    assert "Solid day, keep it up!" in draft.message
    assert draft.feedback_text == "Solid day, keep it up!"
    assert draft.totals["calories"] == 1800.0


@pytest.mark.asyncio
async def test_build_report_returns_none_when_already_recorded_without_calling_the_llm(
    monkeypatch,
):
    """The already-recorded check must happen before the (billed)
    generate_feedback call, not after — a near-simultaneous scheduler run
    (or a repeat poll within the same report hour) shouldn't pay for a
    second LLM call just to discard the result."""
    import datetime as dt

    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_has_daily_report_for_date(pool, user_id, date):
        return True

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("must not call the LLM for an already-recorded day")

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "has_daily_report_for_date", fake_has_daily_report_for_date)
    monkeypatch.setattr(queries, "get_daily_total", fail_if_called)
    monkeypatch.setattr(eod_report, "generate_feedback", fail_if_called)

    draft = await eod_report.build_report("user-1", "15551234567", dt.date(2026, 7, 25))

    assert draft is None


@pytest.mark.asyncio
async def test_record_report_sent_persists_the_draft(monkeypatch):
    import datetime as dt

    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    recorded = {}

    async def fake_insert_daily_report(pool, user_id, date, **kwargs):
        recorded["args"] = (user_id, date, kwargs)
        return True

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "insert_daily_report", fake_insert_daily_report)

    today = dt.date(2026, 7, 25)
    draft = eod_report.ReportDraft(
        message="Today's total: ...\nGreat job!",
        totals={"calories": 1800.0, "protein_g": 100.0, "carbs_g": 200.0, "fat_g": 60.0},
        feedback_text="Great job!",
    )

    await eod_report.record_report_sent("user-1", today, draft)

    assert recorded["args"][0] == "user-1"
    assert recorded["args"][1] == today
    assert recorded["args"][2]["feedback_text"] == "Great job!"
    assert recorded["args"][2]["calories_total"] == 1800.0
