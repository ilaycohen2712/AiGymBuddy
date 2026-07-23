# Calorie accuracy fixtures

Per the constitution (Principle I), every change to `app/prompts/calorie_vision.md`
must be regression-tested against labeled ground truth. This directory holds that
ground truth.

## Adding a fixture

1. Drop the photo in this directory (e.g. `grilled_chicken_salad.jpg`).
2. Add an entry to `manifest.json`:
   ```json
   {"image": "grilled_chicken_salad.jpg", "expected_calories": 450}
   ```
3. Run `pytest tests/test_calorie_accuracy.py` — it calls the real vision pipeline
   (requires `ANTHROPIC_API_KEY`) and fails the suite if mean absolute error
   across all fixtures regresses beyond 5%.

`manifest.json` starts empty — the test skips itself until real labeled photos are
added, since none exist in this repository yet.

## Macro ground truth (for model comparison)

The vision-model comparison tool (`scripts/compare_vision_models.py`, see
`specs/003-vision-model-comparison/`) scores calorie **and macro** accuracy.
Add `expected_protein_g`, `expected_carbs_g`, and `expected_fat_g` alongside
`expected_calories` to also get macro-specific accuracy scores for a photo —
each is optional and independent: a fixture with only `expected_calories`
still scores calories normally and is simply excluded from macro scoring.

```json
{
  "image": "grilled_chicken_salad.jpg",
  "expected_calories": 450,
  "expected_protein_g": 35,
  "expected_carbs_g": 20,
  "expected_fat_g": 22
}
```
