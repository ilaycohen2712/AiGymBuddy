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

## Photos from live testing (2026-07-25)

These images (exported from WhatsApp chat history) are in this directory now.
Only one has a manifest entry — the rest need real ground truth (a nutrition
label, recipe-based calc, or scale) before they're useful for the MAE
regression test; a guessed number would just test self-consistency, not
accuracy.

- **`pastrami_sandwich_rye.jpg`** — in `manifest.json`. The case that
  motivated rules 12 and 13 in `calorie_vision.md` (v4/v5): the bot
  originally guessed ~648-792 kcal for this photo. `expected_calories: 480`
  is a reconstructed estimate, not a scale measurement — 2 slices rye ~220
  kcal + 120g cured beef pastrami at ~140-150 kcal/100g (~170-180 kcal,
  120g being the amount the user confirmed live when the bot asked) + spread
  ~80 kcal ≈ ~470-480 kcal. Good enough to catch a gross regression, not
  precise enough to be the only fixture relied on.
- `salad_cherry_tomato_feta.jpg` — cherry tomatoes + feta, olive oil
- `salad_tomato_iceberg_feta.jpg` — chopped tomato + iceberg lettuce + feta
- `penne_pasta_tomato_sauce.jpg` — penne with tomato sauce + grated parmesan
- `fried_eggs_shakshuka_avocado.jpg` — 4 fried eggs + shakshuka-style sauce + avocado
- `ground_beef_potatoes_eggplant.jpg` — ground beef + roasted potatoes + eggplant
- `braised_meat_potatoes_cucumber.jpg` — braised meat + roasted potatoes + cucumber + a baked starch item
- `sliced_steak_small_portion.jpg` / `sliced_steak_large_platter.jpg` — two separate steak servings, different sizes
- `cheese_pizza_whole.jpg` — whole cheese pizza, 8 slices
- `sushi_rolls_noodles.jpg` — sushi rolls + a side of noodles
- `two_burgers_fries.jpg` — two burgers (one with a fried egg) + fries
