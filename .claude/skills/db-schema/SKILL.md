---
name: db-schema
description: Canonical database schema and conventions. Use whenever adding tables, columns, or queries so every feature uses the same schema.
---

# Database schema (Postgres)

## Tables
- **users**: id (uuid pk), wa_phone (unique), name, language, goal, experience, days_per_week, equipment, height_cm, weight_kg, birth_year, sex, activity_factor, allergies text[], dietary_flags text[], push_morning_time, subscription_status, created_at.
- **meals**: id, user_id fk, logged_at, photo_media_id, foods jsonb (calorie-estimation schema), total_calories, confidence, model_id fk → model_candidates (nullable; which vision model produced this row, FR-008).
- **daily_totals**: user_id, date, calories_consumed, calorie_target, protein_g (pk: user_id+date) — maintained by trigger/upsert on meals.
- **plans**: id, user_id, type (workout|menu), content jsonb, active bool, created_at.
- **messages**: id, user_id, direction (in|out), wa_message_id (dedupe), body, kind (text|image|template), created_at.
- **model_candidates**: id (text pk, matches a `MODEL_REGISTRY` key), display_name, created_at — the registry of vision models known to the system (specs/003-vision-model-comparison).
- **comparison_runs**: id, started_at, completed_at, status (running|completed), triggered_by — one research execution of candidate models against fixture photos.
- **model_results**: id, comparison_run_id fk, model_id fk, fixture_image, status (ok|failed), foods jsonb, total_calories, protein_g, carbs_g, fat_g, confidence, error_message, created_at — one candidate's outcome for one fixture photo (unique per run/model/photo).
- **accuracy_scores**: comparison_run_id fk, model_id fk, metric (calories|protein|carbs|fat), mean_absolute_error_pct, sample_count (pk: comparison_run_id+model_id+metric) — aggregate accuracy per candidate per nutrient.

## Conventions
- All timestamps UTC (timestamptz); user's display timezone stored on users.
- jsonb for LLM outputs — always validated against the pipeline schema before insert.
- Migrations via files in app/db/migrations/ — never ALTER manually.
- No PII in logs; phone numbers masked except last 4 digits.
