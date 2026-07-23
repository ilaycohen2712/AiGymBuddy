from app.config import settings
from app.services.vision_models import MODEL_REGISTRY


async def analyze_photo(
    image_bytes: bytes, media_type: str = "image/jpeg", clarification: str | None = None
) -> dict:
    """Send a food photo to the currently designated live model
    (`settings.live_vision_model_id`, resolved via `MODEL_REGISTRY` — see
    app/services/vision_models.py and contracts/vision_model_client.md) and
    return a result validated against the calorie-estimation schema
    (Constitution IV). Raises ValueError or json.JSONDecodeError on a
    non-conforming response — callers must handle this and fall back to a
    graceful user-facing reply rather than crash.

    Re-reads `settings.live_vision_model_id` on every call rather than
    caching the resolved client, so a deliberate live-model switch
    (research.md decision #1, FR-007) takes effect immediately without
    requiring this module to be reloaded.

    `clarification`: when this photo previously triggered a clarifying
    question, pass the user's text reply here so the model can complete a
    full analysis instead of asking again (prompt rule 10)."""
    client = MODEL_REGISTRY[settings.live_vision_model_id]
    return await client.analyze(image_bytes, media_type, clarification)
