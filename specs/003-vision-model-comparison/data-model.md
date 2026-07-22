# Phase 1 Data Model: Vision Model Abstraction & Comparison

All new tables are added via `app/db/migrations/0003_vision_model_comparison.sql`,
following the conventions in `.claude/skills/db-schema/SKILL.md` (timestamptz
UTC, jsonb for LLM output, no PII). This migration also alters the existing
`meals` table.

## model_candidates

The registry of analysis models known to the system (spec: **Model
Candidate**). A row must exist here before it can appear in `meals.model_id`
or `model_results.model_id`.

| Column | Type | Notes |
|---|---|---|
| id | text PK | Stable identifier matching a `MODEL_REGISTRY` key, e.g. `"claude-sonnet-5"` |
| display_name | text NOT NULL | Human-readable label for comparison output |
| created_at | timestamptz NOT NULL DEFAULT now() | |

**Validation**: `id` must exist in `vision_models.MODEL_REGISTRY` at
application startup — enforced in code (registry/DB drift check), not a DB
constraint, since the registry is the source of truth.

## comparison_runs

One research execution of one or more candidates against a set of photos
(spec: **Comparison Run**).

| Column | Type | Notes |
|---|---|---|
| id | uuid PK DEFAULT gen_random_uuid() | |
| started_at | timestamptz NOT NULL DEFAULT now() | |
| completed_at | timestamptz NULL | NULL while running or if interrupted |
| status | text NOT NULL CHECK (status IN ('running','completed')) DEFAULT 'running' | Only set to `completed` after every (candidate × photo) pair has an outcome |
| triggered_by | text NULL | Free-text identifier of the team member/script invocation, for review only — not an auth mechanism |

**State transition**: `running -> completed`, one-way, set only when the
orchestration script finishes iterating all candidates × all fixture photos.
No other transition exists (an interrupted run simply stays `running`
forever, per research.md decision #3 — it is a durable, correct historical
record of "this run never finished," not an error state to clean up).

## model_results

One candidate model's outcome for one fixture photo within a run (spec:
**Model Result**). Written incrementally, one row per (run, model, photo),
as soon as that combination is attempted.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK DEFAULT gen_random_uuid() | |
| comparison_run_id | uuid NOT NULL REFERENCES comparison_runs(id) | |
| model_id | text NOT NULL REFERENCES model_candidates(id) | |
| fixture_image | text NOT NULL | Manifest `image` filename — join key back to `tests/fixtures/food_photos/manifest.json` |
| status | text NOT NULL CHECK (status IN ('ok','failed')) | `failed` = non-schema-conforming or errored response |
| foods | jsonb NULL | Present only when `status='ok'`; same shape as the calorie-estimation schema's `foods` array |
| total_calories | numeric NULL | Present only when `status='ok'` |
| protein_g | numeric NULL | Sum across `foods`; present only when `status='ok'` |
| carbs_g | numeric NULL | Sum across `foods`; present only when `status='ok'` |
| fat_g | numeric NULL | Sum across `foods`; present only when `status='ok'` |
| confidence | numeric NULL | From the model's own response |
| error_message | text NULL | Present only when `status='failed'` — schema-validation error or exception text, for review (FR-005) |
| created_at | timestamptz NOT NULL DEFAULT now() | |

**Uniqueness**: `UNIQUE (comparison_run_id, model_id, fixture_image)` — one
outcome per combination per run; re-running overwrites nothing, a fresh
`comparison_runs` row is created for each execution.

**Validation**: A row with `status='ok'` MUST have `foods`, `total_calories`,
and `confidence` populated (schema discipline, Constitution IV — this is the
DB-level mirror of the code-level schema validation already applied before
any row is written, same validator as the live path).

## accuracy_scores

Aggregate accuracy for one candidate, for one nutrient, within one run (spec:
**Accuracy Score**). Computed once, after all `model_results` for a run are
in.

| Column | Type | Notes |
|---|---|---|
| comparison_run_id | uuid NOT NULL REFERENCES comparison_runs(id) | |
| model_id | text NOT NULL REFERENCES model_candidates(id) | |
| metric | text NOT NULL CHECK (metric IN ('calories','protein','carbs','fat')) | |
| mean_absolute_error_pct | numeric NOT NULL | Same MAE-percent method as `tests/test_calorie_accuracy.py` |
| sample_count | integer NOT NULL | Number of photos included in this score (excludes failed results and photos missing ground truth for this metric — FR-005) |
| PRIMARY KEY (comparison_run_id, model_id, metric) | | |

## meals (altered)

Adds live-traffic attribution (FR-008/FR-009).

| Column | Type | Notes |
|---|---|---|
| model_id | text NULL REFERENCES model_candidates(id) | Which model produced this row's `foods`/`total_calories`; NULL for rows written before this migration |

No other column changes — `format_range_reply` and the rest of
`app/services/meal_logging.py` are unaffected (research.md decision #2).

## Relationships

```text
model_candidates ──< meals.model_id
model_candidates ──< model_results.model_id
model_candidates ──< accuracy_scores.model_id
comparison_runs  ──< model_results.comparison_run_id
comparison_runs  ──< accuracy_scores.comparison_run_id
```

## Non-DB entity: VisionModelClient registry

`MODEL_REGISTRY: dict[str, VisionModelClient]` in
`app/services/vision_models.py` is in-process, not persisted — it's the code
that `model_candidates.id` values must match. Adding a new candidate model is
a two-step change: register it in code, then insert its `model_candidates`
row (or seed it via the same migration that introduces it, if known upfront).
