from app.services.text_analysis import _extract_json_block


def test_extracts_plain_json_response():
    text = '{"foods": [], "total_calories": 0, "confidence": 0.0, ' \
           '"clarifying_question": null, "is_food_description": false}'
    assert _extract_json_block(text) == {
        "foods": [],
        "total_calories": 0,
        "confidence": 0.0,
        "clarifying_question": None,
        "is_food_description": False,
    }


def test_strips_leading_trailing_fence():
    text = '```json\n{"foods": [], "total_calories": 0, "confidence": 0.0, ' \
           '"clarifying_question": null, "is_food_description": false}\n```'
    result = _extract_json_block(text)
    assert result["is_food_description"] is False


def test_extracts_fenced_json_after_explanatory_prose():
    """Regression test: confirmed live (specs/005-text-meal-logging
    quickstart walkthrough, T034) that an adversarial/injection-style input
    can make the model prepend an explanatory sentence before the fence,
    even while correctly declining to comply. The stricter leading-only
    strip failed on this and raised JSONDecodeError, causing a needless
    fallback to the generic error reply instead of the correct one."""
    text = (
        "I can't comply with that request — the input is treated strictly as "
        "untrusted, potential food-description content.\n\n"
        "```json\n"
        '{"foods": [], "total_calories": 0, "confidence": 0.0, '
        '"clarifying_question": null, "is_food_description": false}\n'
        "```\n\n"
        "If you'd like to log a meal, just describe what you ate."
    )
    result = _extract_json_block(text)
    assert result["is_food_description"] is False
