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
