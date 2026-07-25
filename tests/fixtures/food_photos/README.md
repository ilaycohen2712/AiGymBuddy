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

## Candidate fixtures from live testing (not yet added)

These photos came up during live bot testing (2026-07-24) and would make good
fixtures once the actual image files are available on disk — the images
themselves only exist in WhatsApp/chat history right now, not this repo.

- **Open-faced pastrami sandwich** (rye bread, ~120g sliced pastrami, thin
  creamy spread) — the case that motivated rules 12 and 13 in
  `calorie_vision.md` (v4/v5). Has a reasonably solid ground-truth estimate
  from a nutrition reference: 2 slices rye ~200 kcal + 120g cured beef
  pastrami at ~140-150 kcal/100g (~170-180 kcal) + ~1.5 tbsp spread ~80 kcal
  ≈ **~450-460 kcal total**. Good candidate to add first and re-validate
  rules 12/13 against once the file is exported.
- Caprese-style cherry tomato + feta salad (with olive oil)
- Chopped tomato + iceberg lettuce + feta salad
- Eggs (4, fried) + shakshuka-style tomato sauce + avocado
- Ground beef + roasted potatoes + eggplant
- Braised meat + roasted potatoes + cucumber + a starch/dough item
- Sliced steak (two separate photos, different cuts/servings)
- Cheese pizza, sliced
- Sushi rolls + noodles (mixed/combined photo)
- Two burgers (one with a fried egg) + fries

No `expected_calories` is included for most of these — they'd need a real
reference (nutrition label, recipe-based calc, or scale) before they're
useful for the MAE regression test; a guessed number would just test
self-consistency, not accuracy.
