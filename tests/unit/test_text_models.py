from app.services import text_models


def test_registry_has_both_claude_and_gemini_entries():
    """The text-model registry (app/services/text_models.py) exists so
    text_analysis.py / eod_report.py / timezone.py can swap providers by
    changing a model-id constant, without touching call-site code — mirrors
    app/services/vision_models.py's MODEL_REGISTRY pattern for vision."""
    assert {"claude-sonnet-5", "claude-haiku-4-5", "gemini-flash-latest"} <= (
        text_models.MODEL_REGISTRY.keys()
    )
    assert isinstance(
        text_models.MODEL_REGISTRY["gemini-flash-latest"], text_models.GeminiTextClient
    )
    assert isinstance(
        text_models.MODEL_REGISTRY["claude-sonnet-5"], text_models.ClaudeTextClient
    )
    assert isinstance(
        text_models.MODEL_REGISTRY["claude-haiku-4-5"], text_models.ClaudeTextClient
    )
