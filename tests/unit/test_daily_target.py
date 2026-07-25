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
async def test_send_target_ask_records_pending_ask(monkeypatch):
    from app.db import pool as pool_module
    from app.db import queries

    async def fake_get_pool():
        return object()

    recorded = {"called": False}

    async def fake_set_pending_daily_target_ask(pool, user_id):
        recorded["called"] = True

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "set_pending_daily_target_ask", fake_set_pending_daily_target_ask)

    reply = await daily_target.send_target_ask("user-1", "15551234567")

    assert reply == daily_target.TARGET_ASK
    assert recorded["called"] is True
