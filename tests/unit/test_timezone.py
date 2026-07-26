import pytest

from app.services import timezone as timezone_module


class _FakeTextClient:
    """A TextModelClient test double (app/services/text_models.py) — always
    replies with `reply_text`, regardless of prompt/content passed in."""

    def __init__(self, reply_text: str) -> None:
        self._reply_text = reply_text

    async def generate(self, system_instruction: str, user_content: str, max_tokens: int) -> str:
        return self._reply_text


@pytest.mark.asyncio
async def test_extract_timezone_from_text_returns_zone_for_recognizable_place(monkeypatch):
    fake_client = _FakeTextClient("Asia/Tokyo")
    monkeypatch.setitem(
        timezone_module.MODEL_REGISTRY, timezone_module._EXTRACTION_MODEL, fake_client
    )

    result = await timezone_module.extract_timezone_from_text("just landed in Tokyo!")

    assert result == "Asia/Tokyo"


@pytest.mark.asyncio
async def test_extract_timezone_from_text_returns_none_for_explicit_none(monkeypatch):
    fake_client = _FakeTextClient("NONE")
    monkeypatch.setitem(
        timezone_module.MODEL_REGISTRY, timezone_module._EXTRACTION_MODEL, fake_client
    )

    result = await timezone_module.extract_timezone_from_text("thanks for the tip!")

    assert result is None


@pytest.mark.asyncio
async def test_extract_timezone_from_text_returns_none_for_invalid_zone_name(monkeypatch):
    """Schema discipline (Constitution IV): even if the model answers with
    something that isn't NONE, it must be a real IANA zone or it's treated
    as unrecognized — never persisted as-is."""

    fake_client = _FakeTextClient("Not/A/Real/Zone")
    monkeypatch.setitem(
        timezone_module.MODEL_REGISTRY, timezone_module._EXTRACTION_MODEL, fake_client
    )

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
