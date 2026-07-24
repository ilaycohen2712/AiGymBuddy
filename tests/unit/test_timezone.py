import pytest

from app.services import timezone as timezone_module


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
async def test_extract_timezone_from_text_returns_zone_for_recognizable_place(monkeypatch):
    async def fake_get_client():
        return _FakeClient("Asia/Tokyo")

    monkeypatch.setattr(timezone_module, "_get_client", fake_get_client)

    result = await timezone_module.extract_timezone_from_text("just landed in Tokyo!")

    assert result == "Asia/Tokyo"


@pytest.mark.asyncio
async def test_extract_timezone_from_text_returns_none_for_explicit_none(monkeypatch):
    async def fake_get_client():
        return _FakeClient("NONE")

    monkeypatch.setattr(timezone_module, "_get_client", fake_get_client)

    result = await timezone_module.extract_timezone_from_text("thanks for the tip!")

    assert result is None


@pytest.mark.asyncio
async def test_extract_timezone_from_text_returns_none_for_invalid_zone_name(monkeypatch):
    """Schema discipline (Constitution IV): even if the model answers with
    something that isn't NONE, it must be a real IANA zone or it's treated
    as unrecognized — never persisted as-is."""

    async def fake_get_client():
        return _FakeClient("Not/A/Real/Zone")

    monkeypatch.setattr(timezone_module, "_get_client", fake_get_client)

    result = await timezone_module.extract_timezone_from_text("some ambiguous message")

    assert result is None


def test_timezone_from_location_returns_zone_for_real_coordinates():
    # Tel Aviv
    result = timezone_module.timezone_from_location(32.0853, 34.7818)
    assert result == "Asia/Jerusalem"


def test_timezone_from_location_returns_ocean_zone_for_deep_ocean_coordinates():
    # Deep ocean still resolves to a legitimate nautical Etc/GMT+N zone.
    result = timezone_module.timezone_from_location(0.0, -160.0)
    assert result == "Etc/GMT+11"


def test_timezone_from_location_returns_none_for_out_of_range_coordinates():
    # A malformed WhatsApp location payload (invalid latitude) must not raise.
    result = timezone_module.timezone_from_location(200.0, 34.7818)
    assert result is None
