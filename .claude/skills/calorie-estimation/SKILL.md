---
name: calorie-estimation
description: The vision pipeline that turns a food photo into calories/macros. Use when writing or changing the photo-analysis prompt, schema, or accuracy tests.
---

# Calorie estimation from photos

## Output schema (never change without migrating consumers)
```json
{"foods":[{"name":"","portion_grams":0,"calories":0,"protein_g":0,"carbs_g":0,"fat_g":0}],
 "total_calories":0,"confidence":0.0,"clarifying_question":null}
```

## Prompt rules
- Prompts live in `app/prompts/calorie_vision.md` — versioned file, never inline strings.
- Instruct the model: identify each distinct food, estimate portion by visual reference (plate ≈ 27cm, fork, hand), state assumptions.
- `clarifying_question` is populated (ONE question max, capped at one round trip) only when gated by rules 6 and 12 of the prompt — not on a raw confidence threshold:
  - Rule 6: something essential is genuinely **not visible at all** (sandwich filling, opaque cup contents, a key ingredient's presence/absence with no visual evidence).
  - Rule 12 (v4): a significant item's **portion size or identity is visible but ambiguous** in a way that would swing the total estimate ~15%+ (e.g. an unclear stack/layering of deli meat where the *shape* hides quantity, or a dominant tahini-vs-mayonnaise spread). Explicitly excludes ordinary single-cut proteins (steak, chicken breast, fillet) — those still get estimated via rule 2's visual-reference method, never a question, even though a photo can't give an exact weight. coach-simulator flagged that without this carve-out, the rule would plausibly fire on most dinner-plate photos.
  - Otherwise (rule 5): make the best confident guess and proceed — do NOT ask about cosmetic/low-impact uncertainty (e.g. feta vs. mozzarella).

## Known failure modes
- Mixed dishes (stews, curries): estimate by volume, bias to median recipes.
- Hidden fats (oil, butter, dressings): add 10–15% calories for restaurant-looking plates and say so.
- Beverages in shot: ask, don't assume.
- Dense/stacked items (deli meat, thin-sliced anything): portion-size ambiguity is a known accuracy weak spot — see rule 12.
- Visually-dense-looking foods getting an inflated calories/100g figure, anchored on visual density rather than the food's actual nutritional profile — confirmed live even after rule 12 fixed the portion-size guess itself (a pastrami sandwich still came in ~35-65% over standard reference values for its density). Rule 13 (v5) grounds `calories` in a realistic per-100g density range for the identified food instead of a visual impression.
- The opposite bias is just as real and specifically flagged by `prompt-tester` during v5's review: don't let "ground it in real density" collapse into "assume lean by default" — many calorie-dense foods/preparations (rendered fat in slow-cooked/smoked meat, processed meats like salami, higher-fat ground meat, cheese, nuts, avocado, baked goods) show no visible fat signature at all. Rule 13 explicitly calls this out and leans toward the middle of a food's realistic range, not its leanest variant, absent evidence either way.

## Accuracy discipline
- Every prompt change must run `tests/test_calorie_accuracy.py` against `tests/fixtures/food_photos/` (labeled ground truth). Regression >5% MAE = reject the change. Fixture set is currently empty (`manifest.json` is `[]`) — add labeled photos there to make this test meaningful again.
- Always present results to users as a range (±10%), never a false-precision single number.
