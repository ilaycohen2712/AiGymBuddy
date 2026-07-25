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

The test skips itself (via `pytest.mark.skipif`) if `manifest.json` is empty or
`ANTHROPIC_API_KEY` isn't set — as of 2026-07-25, `manifest.json` has 12 labeled
entries (see below), so only the missing API key gates it in an environment
without one configured.

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

These images (exported from WhatsApp chat history) are in this directory.
All 12 now have `manifest.json` entries. None are scale measurements —
each is a reconstructed estimate (component-by-component: identify each
food, estimate its portion from the photo, apply a standard nutrition-
density figure per 100g, sum) using the same methodology as the original
`pastrami_sandwich_rye.jpg` entry below. Good enough to catch a gross
regression (the 5% MAE gate), not precise enough to be the only fixture
relied on, and two entries below are flagged lower-confidence due to an
ambiguous component or a multi-dish photo.

- **`pastrami_sandwich_rye.jpg`** — 480 kcal. The case that motivated rules
  12 and 13 in `calorie_vision.md` (v4/v5): the bot originally guessed
  ~648-792 kcal for this photo. 2 slices rye ~220 kcal + 120g cured beef
  pastrami at ~140-150 kcal/100g (~170-180 kcal, 120g being the amount the
  user confirmed live when the bot asked) + spread ~80 kcal ≈ ~470-480 kcal.
- **`salad_cherry_tomato_feta.jpg`** — 300 kcal. ~200g cherry tomatoes
  (~36 kcal) + ~70g feta (~185 kcal) + ~10g olive oil dressing (~88 kcal).
- **`salad_tomato_iceberg_feta.jpg`** — 200 kcal. ~150g chopped tomato
  (~27 kcal) + ~50g shredded iceberg (~7 kcal) + ~35g feta (~92 kcal) +
  ~8g olive oil (~71 kcal) — visibly less feta and dressing than the
  cherry-tomato salad above.
- **`penne_pasta_tomato_sauce.jpg`** — 410 kcal. ~180g cooked penne
  (~236 kcal) + ~80g light tomato sauce with some oil (~44 kcal) + a
  generous ~20g grated parmesan on top (~86 kcal).
- **`fried_eggs_shakshuka_avocado.jpg`** — 490 kcal. 4 fried eggs with oil
  (~320 kcal) + ~100g shakshuka-style tomato-pepper sauce (~50 kcal) +
  half an avocado, ~75g (~120 kcal).
- **`ground_beef_potatoes_eggplant.jpg`** — 700 kcal. ~170g browned ground
  beef (~425 kcal) + ~150g oil-roasted potato chunks (~195 kcal) + ~80g
  oil-roasted eggplant (~70 kcal, eggplant absorbs oil when roasted).
- **`braised_meat_potatoes_cucumber.jpg`** — 800 kcal, **lower confidence**:
  ~200g braised beef (~500 kcal) + ~150g roasted potato wedges (~195 kcal)
  + ~100g cucumber (~15 kcal, negligible) + a ~100g flat white item with
  roasted cherry tomatoes and paprika whose identity is genuinely ambiguous
  from the photo (fish fillet vs. a cauliflower steak — assumed a light
  protein/fish-like item, ~90 kcal, but this component could swing the
  total meaningfully either way).
- **`sliced_steak_small_portion.jpg`** — 410 kcal. ~160g sliced cooked
  steak (flank/skirt-style, some fat cap) at ~250 kcal/100g, no visible
  starch or sauce.
- **`sliced_steak_large_platter.jpg`** — 1080 kcal. Same cut/doneness as
  the small portion above, but roughly 2.5-3x the quantity spread across
  a full cutting board — ~420g sliced cooked steak.
- **`cheese_pizza_whole.jpg`** — 2100 kcal for the whole pizza (8 slices).
  A ~12" pie, thick-ish crust, visibly heavy/browned cheese (broiled or
  extra cheese) — estimated above a typical ~230 kcal/slice cheese pizza,
  toward ~260 kcal/slice given the visible cheese density.
- **`sushi_rolls_noodles.jpg`** — 770 kcal, **lower confidence**: two
  separate dishes in one photo. ~200g takeout lo-mein-style noodles with
  meat/veg and sauce (~300 kcal) + ~6 avocado/salmon-and-tuna maki pieces
  with rice (~110g rice, ~230 kcal) + a dollop (~30g) of spicy mayo
  (~90 kcal, though the mayo alone could be smaller or larger than
  estimated). `total_calories` here is meant to cover everything visible
  in the single photo, matching how a real user's one photo of two dishes
  would be scored.
- **`two_burgers_fries.jpg`** — 1650 kcal. Two ~150g cooked beef patties on
  brioche-style buns (one plain with lettuce/tomato/onion ~475 kcal, one
  with an added fried egg ~585 kcal) + a generous bowl of french fries,
  ~160g (~500 kcal).
