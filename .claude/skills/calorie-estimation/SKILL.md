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
- If `confidence < 0.6`, populate `clarifying_question` (ONE question max, e.g. "Is that dressing on the salad?") — the bot asks it instead of guessing.

## Known failure modes
- Mixed dishes (stews, curries): estimate by volume, bias to median recipes.
- Hidden fats (oil, butter, dressings): add 10–15% calories for restaurant-looking plates and say so.
- Beverages in shot: ask, don't assume.

## Accuracy discipline
- Every prompt change must run `tests/test_calorie_accuracy.py` against `tests/fixtures/food_photos/` (labeled ground truth). Regression >5% MAE = reject the change.
- Always present results to users as a range (±20%), never a false-precision single number.
