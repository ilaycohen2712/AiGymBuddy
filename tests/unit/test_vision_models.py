from app.services import vision_models


def test_registry_preserves_claude_entries_and_adds_gemini_flash():
    """FR-008 (specs/006-gemini-flash-migration): the vision-model registry
    must be extended with a Gemini Flash entry, not have its existing Claude
    comparison candidates replaced or removed."""
    assert {"claude-sonnet-5", "claude-opus-4-8", "gemini-flash-latest"} <= (
        vision_models.MODEL_REGISTRY.keys()
    )
    assert isinstance(
        vision_models.MODEL_REGISTRY["gemini-flash-latest"], vision_models.GeminiVisionClient
    )
    assert isinstance(
        vision_models.MODEL_REGISTRY["claude-sonnet-5"], vision_models.ClaudeVisionClient
    )
