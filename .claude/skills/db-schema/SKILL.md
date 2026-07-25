---
name: db-schema
description: Canonical database schema and conventions. Use whenever adding tables, columns, or queries so every feature uses the same schema.
---

# Database schema (Postgres)

## Tables
- **users**: id (uuid pk), wa_phone (unique), name, language, goal, experience, days_per_week, equipment, height_cm, weight_kg, birth_year, sex, activity_factor, allergies text[], dietary_flags text[], push_morning_time, subscription_status, time_zone (IANA name, e.g. `Asia/Jerusalem` — defaulted from wa_phone's country code, updated via WhatsApp location share or a text place-mention, specs/002-daily-total-tracking), daily_calorie_target (integer, nullable; collected via chat when missing, ≥ the 1500 kcal safety floor, reused across days — specs/001-photo-calorie-tracking User Story 3), created_at.
- **meals**: id, user_id fk, logged_at, photo_media_id (nullable — `NULL` when the meal's first contribution was a typed description rather than a photo, specs/005-text-meal-logging), photo_media_ids text[] (every photo contribution, in order; empty if none), text_entries text[] (every typed-description contribution's raw body, in order, parallel to photo_media_ids; empty if none — specs/005-text-meal-logging), foods jsonb (calorie-estimation schema), total_calories, confidence, model_id fk → model_candidates (nullable; which model — vision or text — produced this row, FR-008). A meal's total contribution count for reply-shaping is `len(photo_media_ids) + len(text_entries)`, not `photo_media_ids` alone.
- **pending_clarifications**: user_id (pk, fk → users), media_id (nullable), media_type, text_body (nullable — the original typed description when `media_type = 'text'`, specs/005-text-meal-logging), question, asked_at — tracks a single outstanding clarifying question per user (photo- or text-originated) so the next text reply resumes and completes that original analysis instead of being a dead end. Exactly one of media_id/text_body is set per row, discriminated by media_type.
- **daily_totals**: user_id, date, calories_consumed, calorie_target, protein_g, carbs_g, fat_g (pk: user_id+date) — maintained by additive upsert in app/services/meal_logging.py at meal-log time, bucketed by the user's local calendar date *at that moment* (never recomputed later, so a subsequent time-zone change can't retroactively reattribute a past meal — specs/002-daily-total-tracking).
- **pending_daily_target_asks**: user_id (pk, fk → users), asked_at — tracks that a user was asked for their daily calorie target today, so the next text reply is parsed as an attempted answer and the scheduler doesn't re-ask more than once per day (specs/001-photo-calorie-tracking User Story 3).
- **daily_reports**: id, user_id fk, date, calories_total, protein_g, carbs_g, fat_g (snapshot of daily_totals at send time), feedback_text, sent_at — `UNIQUE (user_id, date)` enforces at most one end-of-day report per user per day (specs/001-photo-calorie-tracking User Story 3, FR-006/SC-003).
- **plans**: id, user_id, type (workout|menu), content jsonb, active bool, created_at.
- **messages**: id, user_id, direction (in|out), wa_message_id (dedupe), body, kind (text|image|template|location|other — `other` covers any inbound message type with no dedicated handler, e.g. voice/sticker/document, specs/004-chat-responsiveness), created_at.
- **model_candidates**: id (text pk, matches a `MODEL_REGISTRY` key), display_name, created_at — the registry of vision models known to the system (specs/003-vision-model-comparison).
- **comparison_runs**: id, started_at, completed_at, status (running|completed), triggered_by — one research execution of candidate models against fixture photos.
- **model_results**: id, comparison_run_id fk, model_id fk, fixture_image, status (ok|failed), foods jsonb, total_calories, protein_g, carbs_g, fat_g, confidence, error_message, created_at — one candidate's outcome for one fixture photo (unique per run/model/photo).
- **accuracy_scores**: comparison_run_id fk, model_id fk, metric (calories|protein|carbs|fat), mean_absolute_error_pct, sample_count (pk: comparison_run_id+model_id+metric) — aggregate accuracy per candidate per nutrient.

## Conventions
- All timestamps UTC (timestamptz); user's display timezone stored on users.
- jsonb for LLM outputs — always validated against the pipeline schema before insert.
- Migrations via files in app/db/migrations/ — never ALTER manually.
- No PII in logs; phone numbers masked except last 4 digits.
