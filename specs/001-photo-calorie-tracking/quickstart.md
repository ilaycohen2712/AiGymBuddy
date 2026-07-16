# Quickstart: Validating Photo Calorie Tracking MVP

## Prerequisites
- Local env vars set for: Meta WhatsApp App Secret/token, Claude API key, Postgres (Supabase) connection string — per existing project setup, none new for this feature besides the migrations below.
- Migrations applied (see `data-model.md`): `users.daily_calorie_target`, `meals.photo_media_ids`, `daily_totals.carbs_g`/`fat_g`, new `daily_reports` table.
- A test user seeded in `users` with a real or sandboxed `wa_phone`, and **no** `daily_calorie_target` set (to exercise the collection flow first).

## Scenario 1 — Log a meal from a photo (User Story 1, P1)
1. Send a food photo from the test WhatsApp account to the bot.
2. **Expect**: a reply within ~60s containing a calorie range and macro range (protein/carbs/fat) — see `contracts/webhook-image-message.md`.
3. Send a second photo of a different dish within 10 minutes.
4. **Expect**: the reply now reflects a *combined* single meal entry (one `meals` row with both photos in `photo_media_ids`), not two separate entries.
5. Query `meals` for the user — confirm exactly one row for both photos, with combined `total_calories` and macros.

## Scenario 2 — Running daily total (User Story 2, P2)
1. After Scenario 1, query `daily_totals` for the user/today.
2. **Expect**: `calories_consumed`, `protein_g`, `carbs_g`, `fat_g` equal the sum of all meals logged so far today (SC-005).
3. Log one more meal photo; re-query; confirm the total increased accordingly.

## Scenario 3 — Daily target collection + safety floor (supports User Story 3)
1. Manually invoke `app/scheduler/eod_trigger.py` for the test user (or wait for its scheduled run) while `daily_calorie_target` is still null.
2. **Expect**: the bot asks for a daily calorie target instead of sending a report — see `contracts/daily-target-collection.md`.
3. Reply with a value below the floor (e.g., "900").
4. **Expect**: rejection message explaining the floor, value NOT stored.
5. Reply with a valid value (e.g., "2000").
6. **Expect**: confirmation message; `users.daily_calorie_target` now set to 2000.

## Scenario 4 — End-of-day report (User Story 3, P3)
1. With `daily_calorie_target` set and at least one meal logged today, invoke the scheduler trigger again for this user.
2. **Expect**: exactly one message containing total calories, total protein/carbs/fat, and a feedback message referencing the target — see `contracts/eod-report.md`.
3. Query `daily_reports` — confirm exactly one row for `(user_id, today)`.
4. Invoke the trigger again for the same user/day.
5. **Expect**: no second message sent (idempotent — unique constraint prevents a duplicate `daily_reports` row).
6. Repeat for a second test user who logged **no** meals today.
7. **Expect**: report still sent, showing zero totals and encouraging (not critical) feedback (FR-008).

## Regression checks to run alongside these scenarios
- `tests/test_calorie_accuracy.py` against `tests/fixtures/food_photos/` — must not regress >5% MAE (Constitution I).
- `coach-simulator` agent — run before treating the new daily-report cadence as release-ready (see plan.md's Constitution Check note on Principle II).
