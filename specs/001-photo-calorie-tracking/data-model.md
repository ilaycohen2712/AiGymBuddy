# Data Model: Photo Calorie Tracking MVP

All tables per `.claude/skills/db-schema/SKILL.md` conventions: Postgres, UTC timestamps, jsonb validated before insert, migrations only (never manual `ALTER`), no PII in logs.

## Existing tables (referenced, not changed unless noted)

### `users` (extended)
| Column | Type | Notes |
|---|---|---|
| id | uuid pk | existing |
| wa_phone | text unique | existing |
| ...(existing columns unchanged)... | | |
| **daily_calorie_target** | integer, nullable | **NEW.** Durable per-user target (FR-007). Set via chat when missing; must be ≥ the safety floor (1200/1500 kcal, FR-015) or rejected at write time. |

### `meals` (extended)
| Column | Type | Notes |
|---|---|---|
| id | uuid pk | existing |
| user_id | fk → users | existing |
| logged_at | timestamptz | existing — used as the grouping-window anchor (research.md #2) |
| photo_media_id | text | existing — **NEW usage**: for a combined meal, this becomes the *first* photo's media id |
| **photo_media_ids** | text[] | **NEW.** Full list of media ids combined into this meal entry (supports FR-014's multi-photo combining; keeps `photo_media_id` for backward compatibility with single-photo meals) |
| foods | jsonb | existing — per calorie-estimation schema; combined meals append additional food items from later photos in the same window |
| total_calories | numeric | existing |
| confidence | numeric | existing |

### `daily_totals` (extended)
| Column | Type | Notes |
|---|---|---|
| user_id, date | pk | existing |
| calories_consumed | numeric | existing |
| calorie_target | integer | existing — populated from `users.daily_calorie_target` at day-rollover (research.md #3) |
| protein_g | numeric | existing |
| **carbs_g** | numeric | **NEW.** Running total, same upsert pattern as `protein_g` (research.md #4) |
| **fat_g** | numeric | **NEW.** Running total, same upsert pattern as `protein_g` |

## New table

### `daily_reports`
| Column | Type | Notes |
|---|---|---|
| id | uuid pk | |
| user_id | fk → users | |
| date | date | |
| calories_total | numeric | snapshot of `daily_totals.calories_consumed` at send time |
| protein_g | numeric | snapshot |
| carbs_g | numeric | snapshot |
| fat_g | numeric | snapshot |
| feedback_text | text | output of the `eod_feedback` prompt, ≤600 chars |
| sent_at | timestamptz | |

**Constraint**: `UNIQUE (user_id, date)` — enforces "at most one report per day" (FR-006, SC-003) at the database level.

## Validation rules (from Functional Requirements)

- `users.daily_calorie_target`: reject writes below 1200/1500 kcal (FR-015); reuse existing value if already set, never re-prompt (FR-007).
- `meals.foods` / vision-prompt output: validated against the existing `calorie_vision` schema before insert (Constitution IV); calorie/macro values only ever surfaced to users as ranges (FR-012).
- `daily_reports`: insert-time uniqueness on `(user_id, date)` is the enforcement mechanism for FR-006/FR-008 ("at most one report per day, sent regardless of activity").
- `eod_feedback` prompt output: validated against its schema (`{"feedback_text": "", "tone": "encouraging|neutral"}`) before use; `feedback_text` must not exceed 600 chars (coach-persona voice rule) and must not contain medical-advice or crash-diet language (FR-016, SC-008 — enforced via prompt instructions + the existing safety-escalation review process, not a mechanical check).

## State transitions

**Meal entry (per user, per grouping window)**:
`no meal` → *photo received* → `open meal (within window)` → *another photo within 10 min* → `open meal, foods appended` → *10 min elapse with no new photo* → `closed` (next photo starts a new meal)

**Daily target**:
`unset` → *user provides target* → `pending validation` → *below floor* → `rejected, re-prompt` | *at/above floor* → `set` (persists across days)

**End-of-day report**:
`not sent today` → *scheduler trigger at user's local report time, no existing `daily_reports` row for today* → `sent` (idempotent: subsequent trigger firings for the same day are no-ops due to the unique constraint)
