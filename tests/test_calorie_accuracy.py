"""Accuracy regression suite (Constitution I): every prompt change to
app/prompts/calorie_vision.md must be checked against labeled fixtures here.
MAE regression beyond 5% blocks merge.
"""

import json
import os
from pathlib import Path

import pytest

from app.services import vision

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "food_photos"
MANIFEST = FIXTURES_DIR / "manifest.json"
MAX_MEAN_ABSOLUTE_ERROR_PCT = 5.0


def _load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text())


@pytest.mark.skipif(
    not _load_manifest(),
    reason="No labeled fixtures yet — see tests/fixtures/food_photos/README.md",
)
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Requires a real ANTHROPIC_API_KEY to call the vision pipeline",
)
@pytest.mark.asyncio
async def test_calorie_estimate_mean_absolute_error_within_threshold():
    manifest = _load_manifest()
    errors_pct = []

    for entry in manifest:
        image_bytes = (FIXTURES_DIR / entry["image"]).read_bytes()
        result = await vision.analyze_photo(image_bytes)
        expected = entry["expected_calories"]
        actual = result["total_calories"]
        errors_pct.append(abs(actual - expected) / expected * 100)

    mean_absolute_error_pct = sum(errors_pct) / len(errors_pct)
    assert mean_absolute_error_pct <= MAX_MEAN_ABSOLUTE_ERROR_PCT, (
        f"Calorie estimate MAE {mean_absolute_error_pct:.1f}% exceeds the "
        f"{MAX_MEAN_ABSOLUTE_ERROR_PCT}% regression gate"
    )
