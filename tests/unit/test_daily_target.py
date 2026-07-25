import datetime as dt

import pytest

from app.services import daily_target


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2000", 2000),
        ("2,000 kcal", 2000),
        ("around 2000", 2000),
        ("I'd say 1800", 1800),
        ("no numbers here", None),
        ("", None),
    ],
)
def test_parse_calorie_target(text, expected):
    assert daily_target._parse_calorie_target(text) == expected


@pytest.mark.asyncio
async def test_handle_daily_target_reply_returns_none_without_pending_ask(monkeypatch):
    # No monkeypatching of get_pool/queries.set_* at all — if this touched
    # storage it would raise (no real DATABASE_URL configured for tests),
    # proving the short-circuit happens before any write.
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_pending_daily_target_ask(pool, user_id):
        return None

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)

    reply = await daily_target.handle_daily_target_reply("user-1", "15551234567", "hello there")

    assert reply is None


@pytest.mark.parametrize(
    "text",
    [
        "I've barely eaten anything the last three days",
        "my knee has been killing me since yesterday's squats",
        "chest pain and I can't breathe",
    ],
)
@pytest.mark.asyncio
async def test_handle_daily_target_reply_yields_to_safety_signal_even_with_pending_ask(
    monkeypatch, text
):
    """Regression test (reviewer + coach-simulator both found this live): a
    pending daily-target ask has no expiry and no cap on retries, unlike
    meal_logging's one-round-trip clarification flow — so unconditionally
    intercepting every reply here would swallow a genuine safety disclosure
    indefinitely, never letting chat_fallback's safety check ever run. A
    safety-signal match must return None (unhandled) without even touching
    the pending-ask storage, regardless of whether an ask is outstanding."""
    from app.db import pool as pool_module
    from app.db import queries

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("must not touch pending-ask storage for a safety-signal message")

    monkeypatch.setattr(pool_module, "get_pool", fail_if_called)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fail_if_called)

    reply = await daily_target.handle_daily_target_reply("user-1", "15551234567", text)

    assert reply is None


@pytest.mark.asyncio
async def test_handle_daily_target_reply_rejects_below_floor(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_pending_daily_target_ask(pool, user_id):
        return dt.datetime.now(dt.UTC)

    stored = {"called": False}

    async def fake_set_daily_calorie_target(pool, user_id, target):
        stored["called"] = True

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)
    monkeypatch.setattr(queries, "set_daily_calorie_target", fake_set_daily_calorie_target)

    reply = await daily_target.handle_daily_target_reply("user-1", "15551234567", "1000")

    assert "1500" in reply
    assert stored["called"] is False


@pytest.mark.asyncio
async def test_handle_daily_target_reply_rejects_implausibly_high_target(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_pending_daily_target_ask(pool, user_id):
        return dt.datetime.now(dt.UTC)

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("must not store an implausible target")

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)
    monkeypatch.setattr(queries, "set_daily_calorie_target", fail_if_called)

    reply = await daily_target.handle_daily_target_reply("user-1", "15551234567", "99999999")

    assert reply == daily_target._IMPLAUSIBLE_REPLY


@pytest.mark.asyncio
async def test_handle_daily_target_reply_re_asks_on_unparseable_text(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_pending_daily_target_ask(pool, user_id):
        return dt.datetime.now(dt.UTC)

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)

    reply = await daily_target.handle_daily_target_reply("user-1", "15551234567", "no idea")

    assert reply == daily_target._UNPARSEABLE_REPLY


@pytest.mark.asyncio
async def test_handle_daily_target_reply_stores_valid_target_and_clears_pending(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    async def fake_get_pending_daily_target_ask(pool, user_id):
        return dt.datetime.now(dt.UTC)

    stored = {}

    async def fake_set_daily_calorie_target(pool, user_id, target):
        stored["args"] = (user_id, target)

    cleared = {"called": False}

    async def fake_clear_pending_daily_target_ask(pool, user_id):
        cleared["called"] = True

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "get_pending_daily_target_ask", fake_get_pending_daily_target_ask)
    monkeypatch.setattr(queries, "set_daily_calorie_target", fake_set_daily_calorie_target)
    monkeypatch.setattr(
        queries, "clear_pending_daily_target_ask", fake_clear_pending_daily_target_ask
    )

    reply = await daily_target.handle_daily_target_reply("user-1", "15551234567", "2000 kcal")

    assert stored["args"] == ("user-1", 2000)
    assert cleared["called"] is True
    assert "2000" in reply


@pytest.mark.asyncio
async def test_build_target_ask_does_not_touch_storage():
    # No monkeypatching at all — if this touched the DB it would raise (no
    # real DATABASE_URL configured for tests), proving build_target_ask is
    # pure composition; only mark_target_ask_sent (below) may persist, and
    # only after an actual send succeeds (reviewer-flagged: the previous
    # version recorded the ask as sent before it was ever delivered).
    reply = await daily_target.build_target_ask()

    assert reply == daily_target.TARGET_ASK


@pytest.mark.asyncio
async def test_mark_target_ask_sent_records_pending_ask(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    recorded = {"called": False}

    async def fake_set_pending_daily_target_ask(pool, user_id):
        recorded["called"] = True

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "set_pending_daily_target_ask", fake_set_pending_daily_target_ask)

    await daily_target.mark_target_ask_sent("user-1", "15551234567")

    assert recorded["called"] is True
