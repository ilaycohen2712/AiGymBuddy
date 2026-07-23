# Quickstart: Validating Vision Model Abstraction & Comparison

## Prerequisites

- Local Postgres reachable via `DATABASE_URL` (or the project's usual dev DB),
  migrated through `0003_vision_model_comparison.sql` (runs automatically via
  `run_migrations` on app startup — see `app/main.py`).
- `ANTHROPIC_API_KEY` set (comparison runs make real model calls, same as
  `tests/test_calorie_accuracy.py` today).
- At least 2 labeled fixtures in `tests/fixtures/food_photos/manifest.json`
  with `expected_calories` and, ideally, `expected_protein_g`/`expected_carbs_g`/
  `expected_fat_g` (see updated `tests/fixtures/food_photos/README.md`).
- At least 2 `model_id`s registered in `app/services/vision_models.py`'s
  `MODEL_REGISTRY` and mirrored in `model_candidates`.

## Scenario 1 — Compare two models (User Story 1)

```bash
python -m scripts.compare_vision_models --models claude-sonnet-5,claude-opus-4-8
```

**Expect**: stdout shows, per fixture photo, both models' calorie + macro
**ranges** (±20%, same method as the live bot's `format_range_reply`, per
research.md decision #6) grouped together; a `comparison_runs` row exists with
`status='completed'`; a `model_results` row exists for every
`(model, photo)` pair.

**Failure-isolation check**: temporarily point one registry entry at an
invalid model id, rerun, and confirm the *other* model's results for every
photo are still present and correct (FR-002 acceptance scenario 2) — the
run still reaches `status='completed'`.

## Scenario 2 — Accuracy scoring (User Story 2)

After Scenario 1 completes:

```sql
SELECT model_id, metric, mean_absolute_error_pct, sample_count
FROM accuracy_scores
WHERE comparison_run_id = '<run id from Scenario 1>'
ORDER BY model_id, metric;
```

**Expect**: one row per `(model, metric)` for `calories`, `protein`,
`carbs`, `fat` — `sample_count` excludes any fixture missing that nutrient's
ground truth and any failed `model_results` row (FR-004/FR-005).

## Scenario 3 — Live traffic is unaffected during/after a run (User Story 1 scenario 3, User Story 3)

1. Note the current `settings.live_vision_model_id`.
2. While a comparison run is in progress (or immediately after one
   completes without switching), send a live food photo through the normal
   webhook path (or run `tests/contract/test_webhook_image.py`).
3. **Expect**: the reply and the new `meals` row's `model_id` reflect the
   *original* live model — unchanged by the comparison run (FR-006, FR-009,
   SC-003).

## Scenario 4 — Switch the live model (User Story 3)

1. Change `live_vision_model_id` in the environment to a different,
   already-compared candidate; redeploy/restart.
2. Send a new live food photo.
3. **Expect**: the new `meals` row's `model_id` is the newly designated
   model; querying prior `meals` rows still shows the previous model_id
   (FR-008, SC-005) — nothing else about the reply, meal grouping, or daily
   totals differs (SC-004).

## Regression check

```bash
pytest tests/unit/test_vision_comparison.py tests/integration/test_vision_comparison_flow.py -v
pytest tests/test_calorie_accuracy.py -v   # existing single-model gate still passes
```
