# Quickstart: Validating Daily Calorie & Macro Total Tracking

## Prerequisites

- Migration `0003_daily_totals_and_timezone.sql` applied (adds `daily_totals.carbs_g`/`fat_g` and `users.time_zone`).
- `phonenumbers` and `timezonefinder` installed (new dependencies — see plan.md).
- `ANTHROPIC_API_KEY` set (reused, no new secret) — used for the text place-mention extraction call.
- A test WhatsApp account with no meals logged yet today.

## Scenario 1 — Ask for the total with meals already logged (User Story 1/2)

1. Send two food photos as separate meals (or one, then a second more than 10 minutes later so they don't combine).
2. Send a total-request message (e.g. "what's my total today?" / Hebrew equivalent).
3. **Expect**: a reply within the bot's normal response time, stating a ±20% calorie range and macro ranges summing both meals — see `contracts/daily-total-query.md`.
4. Query `daily_totals` for `(user_id, today)` directly — confirm `calories_consumed`/`protein_g`/`carbs_g`/`fat_g` match the sum of both meals' `foods`.

## Scenario 2 — Ask for the total with zero meals logged (SC-004)

1. Using a fresh test user who hasn't logged anything today, send a total-request message.
2. **Expect**: a friendly "nothing logged yet today" reply — not an error, not a literal "0-0 kcal".

## Scenario 3 — A combined (grouped) meal counts once (User Story 2, Acceptance Scenario 3)

1. Send two photos of the same meal within the existing 10-minute grouping window (they combine into one `meals` row, per `001-photo-calorie-tracking`).
2. Ask for the total.
3. **Expect**: the reply reflects the combined meal once, not twice.

## Scenario 4 — Reset at local midnight (User Story 3)

1. Log a meal "yesterday" relative to the test user's stored `time_zone` (adjust `meals.logged_at` / `daily_totals.date` directly in test data — waiting for real midnight isn't practical for manual QA).
2. Ask for today's total.
3. **Expect**: the reply reflects only today's meals (zero, if none logged today), not yesterday's — automated tests should cover this directly rather than relying on wall-clock waiting.

## Scenario 5 — WhatsApp location share updates time zone (User Story 4, Acceptance Scenario 1)

1. From the test WhatsApp account, use "Share Location" to send a location in a different time zone than the account's current one.
2. **Expect**: a short confirmation reply — see `contracts/timezone-update.md`, Trigger A.
3. Query `users.time_zone` — confirm it now matches the shared location's zone.
4. Ask for the total again — confirm the reset boundary now follows the new zone (e.g. by checking which `date` bucket a subsequently-logged meal lands in).

## Scenario 6 — Text place-mention updates time zone (User Story 4, Acceptance Scenario 2)

1. Send a plain text message mentioning a place, e.g. "just landed in Tokyo".
2. **Expect**: no dedicated confirmation reply (silent update, per `contracts/timezone-update.md`, Trigger B) — but `users.time_zone` in the database now reflects Tokyo's zone.

## Scenario 7 — Ambiguous place mention leaves time zone unchanged (User Story 4, Acceptance Scenario 4)

1. Send a text message with an ambiguous or unrecognized place reference.
2. **Expect**: `users.time_zone` is unchanged from before the message — confirm by querying the DB, since there's no user-facing signal either way.

## Regression checks to run alongside these scenarios

- Existing `tests/contract/test_webhook_image.py` and `tests/unit/test_meal_logging.py` scenarios must still pass unmodified (pending-clarification flow, image handling) — this feature only adds behavior, per FR-002.
- `reviewer` agent — run before merging, since this touches the webhook and persisted user data (new message type, new columns).
