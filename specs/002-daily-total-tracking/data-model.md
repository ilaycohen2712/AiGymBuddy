# Phase 1 Data Model: Daily Calorie & Macro Total Tracking

All changes are additive — no existing column is altered or removed, via a new migration `app/db/migrations/0004_daily_totals_and_timezone.sql`.

## `daily_totals` (existing table, extended)

| Column | Type | Notes |
|---|---|---|
| user_id | uuid, FK → users | existing, part of PK |
| date | date | existing, part of PK — the calendar date **in the user's time zone at the moment the contributing meal was logged** (not UTC, not "today" recomputed later) |
| calories_consumed | numeric | existing — this feature is the first to actually write it (see below) |
| calorie_target | integer | existing, unrelated to this feature (set via `001-photo-calorie-tracking`'s daily-target-collection flow) |
| protein_g | numeric | existing — first actually written by this feature |
| carbs_g | numeric NOT NULL DEFAULT 0 | **NEW** |
| fat_g | numeric NOT NULL DEFAULT 0 | **NEW** |

**Maintenance**: Upserted additively (never overwritten) whenever a meal is created or appended to in `app/services/meal_logging.py`:
- `create_meal`: `INSERT ... ON CONFLICT (user_id, date) DO UPDATE SET calories_consumed = daily_totals.calories_consumed + EXCLUDED.calories_consumed, protein_g = ..., carbs_g = ..., fat_g = ...` — same `ON CONFLICT` upsert shape already used for `pending_clarifications` in this codebase.
- `append_to_meal` (a second photo combined into an already-open meal within the existing 10-minute grouping window): increments the same row by only the *new* photo's contribution (the delta), not the meal's whole recomputed total — the meal's `logged_at` doesn't change when appending (existing behavior), so it stays attributed to the same date bucket it started in.
- A photo that isn't recognized as food never reaches either path, so it's naturally excluded (FR-007) — no special-casing needed.

**Why "written once, at write time" instead of recomputed**: see research.md #1 — this is what makes FR-014 (no retroactive reattribution when a user's time zone later changes) hold without extra bookkeeping.

## `users` (existing table, extended)

| Column | Type | Notes |
|---|---|---|
| time_zone | text NOT NULL DEFAULT 'UTC' | **NEW**. An IANA time zone name (e.g. `Asia/Jerusalem`). Column-level default is a safety net only — the application always supplies a derived value explicitly at user-creation time (`get_or_create_user_id`), so it's never left at the bare default in practice, the same way `users.language`/`users.goal` etc. are meant to be filled in once onboarding reaches them. |

**Validation**: Any value written to `time_zone` — whether the phone-derived initial default, a `timezonefinder` result, or a Claude-extracted place name — MUST be a member of Python's `zoneinfo.available_timezones()` before being persisted. A value that fails this check is treated the same as "unrecognized" (FR-013): the column is left at its current value.

**Mutability**: Unlike most of `users`' other onboarding-oriented columns, `time_zone` is expected to change over a user's lifetime (User Story 4) — it is not a one-time setting.

## Key Entities (from spec.md, mapped to storage)

- **Daily Total** → the `(user_id, date)` row in `daily_totals` described above.
- **User time zone** → `users.time_zone` described above.

No new tables are introduced by this feature.
