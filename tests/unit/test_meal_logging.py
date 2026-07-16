import pytest

from app.db import queries
from app.services import meal_logging


@pytest.mark.asyncio
async def test_handle_incoming_photo_passes_downloaded_media_type_to_vision(monkeypatch):
    """Regression test: the mime_type returned by download_media must reach
    analyze_photo rather than silently falling back to vision.py's
    image/jpeg default — WhatsApp photos aren't guaranteed to be JPEG."""
    from app.db import pool as pool_module
    from app.services import vision
    from app.whatsapp import media as media_client

    class FakeRepo:
        async def find_open_meal(self, *args, **kwargs):
            return None

        async def create_meal(self, user_id, media_id, foods, total_calories, confidence, now):
            return queries.MealRecord(
                id="meal-1",
                user_id=user_id,
                logged_at=now,
                photo_media_ids=[media_id],
                foods=foods,
                total_calories=total_calories,
                confidence=confidence,
            )

    async def fake_get_pool():
        return object()

    async def fake_download_media(media_id):
        return b"fake-png-bytes", "image/png"

    captured = {}

    async def fake_analyze_photo(image_bytes, media_type="image/jpeg"):
        captured["image_bytes"] = image_bytes
        captured["media_type"] = media_type
        return {
            "foods": [
                {
                    "name": "rice",
                    "portion_grams": 200,
                    "calories": 300,
                    "protein_g": 5,
                    "carbs_g": 60,
                    "fat_g": 1,
                }
            ],
            "total_calories": 300,
            "confidence": 0.9,
            "clarifying_question": None,
        }

    monkeypatch.setattr(pool_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(queries, "AsyncpgMealRepository", lambda pool: FakeRepo())
    monkeypatch.setattr(media_client, "download_media", fake_download_media)
    monkeypatch.setattr(vision, "analyze_photo", fake_analyze_photo)

    await meal_logging.handle_incoming_photo("user-1", "15551234567", "media-99")

    assert captured["image_bytes"] == b"fake-png-bytes"
    assert captured["media_type"] == "image/png"
