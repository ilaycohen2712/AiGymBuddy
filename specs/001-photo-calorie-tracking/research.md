# Phase 0 Research: Photo Calorie Tracking MVP

## 1. Calorie/macro ranges vs. the existing vision pipeline schema

**Decision**: Keep the existing `calorie_vision` output schema unchanged (single point estimate + `confidence`, per `.claude/skills/calorie-estimation/SKILL.md`). Compute the displayed range at presentation time as ±20% of the point estimate.

**Rationale**: The skill already mandates presenting results as a range and never storing false precision; deriving the range from one stored number keeps the schema and DB simple and avoids two numbers that could drift out of sync.

**Alternatives considered**: Storing explicit `calorie_min`/`calorie_max` in the schema — rejected as redundant state for a value that's a deterministic function of the point estimate.

## 2. Combining multiple photos into one meal entry

**Decision**: Application-level grouping — when a new food photo arrives, check whether the user has an existing meal row logged within the last 10 minutes; if so, append the new photo's foods to that meal's `foods` jsonb and recompute totals; otherwise create a new meal row. No new "session" table.

**Rationale**: Matches the spec's Assumption of a short, fixed grouping window with no explicit "done" signal; keeps the schema minimal.

**Alternatives considered**: An explicit meal-session table with start/end timestamps (rejected — unneeded complexity for MVP); requiring an explicit "done with this meal" user message (rejected — adds friction, not requested).

## 3. Source of truth for the daily calorie target

**Decision**: Add `daily_calorie_target` (integer, nullable) to `users` as the durable source of truth, collected once via chat (FR-007) and subject to the 1200/1500 kcal safety floor (FR-015). `daily_totals.calorie_target` (already in the existing schema) is populated by copying this value at day-rollover, preserving a historical record of the target that applied on each given day.

**Rationale**: `daily_totals` is a per-day table and isn't a reliable place to *ask once and reuse* a value; `users` is. Copying into `daily_totals` at rollover keeps the existing per-day column meaningful for historical reports.

**Alternatives considered**: Reading the "most recent" `daily_totals.calorie_target` row as the effective target — rejected as ambiguous/fragile before any `daily_totals` row exists for a new day or a brand-new user.

## 4. Macro totals on `daily_totals`

**Decision**: Extend `daily_totals` with `carbs_g` and `fat_g` columns (mirroring the existing `protein_g` column) via migration, maintained by the same upsert/trigger pattern already used for `protein_g` and `calories_consumed`.

**Rationale**: FR-006 requires the end-of-day report to include full macro totals, not protein alone.

**Alternatives considered**: Deriving macro totals on-the-fly by summing `meals.foods` jsonb per report — rejected as slower and inconsistent with the existing maintained-aggregate pattern for `protein_g`.

## 5. Idempotency and audit for the once-daily report

**Decision**: New `daily_reports` table (`user_id`, `date`, `calories_total`, `protein_g`, `carbs_g`, `fat_g`, `feedback_text`, `sent_at`), unique on `(user_id, date)`.

**Rationale**: A unique constraint gives an atomic, DB-enforced guarantee of "at most one report per day" (FR-006, SC-003) and provides an audit trail for reviewing feedback-message safety (SC-008) without overloading the generic `messages` table.

**Alternatives considered**: Querying `messages` for a `kind='eod_report'` row sent that day — rejected as a weaker uniqueness guarantee (race-prone) and harder to query/test.

## 6. Feedback-message generation

**Decision**: New versioned prompt `app/prompts/eod_feedback.md`, following the `calorie_vision.md` convention (Constitution IV: prompts are files, never inline strings). Output schema: `{"feedback_text": "", "tone": "encouraging|neutral"}`, validated before sending; `feedback_text` capped at 600 chars per the coach-persona voice rule, and explicitly instructed to never include medical advice or crash-diet pressure regardless of how far over/under target the user is (FR-016, SC-008).

**Rationale**: Matches existing prompt-versioning and schema-validation discipline (Constitution I & IV); keeps the safety constraint testable and reviewable.

## 7. Push-cadence conflict with `coach-persona/SKILL.md`

**Decision**: For this feature, follow the spec's FR-008 (report sent every day regardless of activity) as authoritative, since it was a deliberate clarification during specification. Flag the resulting drift in `coach-persona/SKILL.md`'s evening check-in bullet as a required documentation follow-up, and require the `coach-simulator` agent to validate the new cadence before release (per this project's own workflow rule for push-logic changes).

**Rationale**: The spec clarification explicitly weighed "every day" vs. "only on active days" and chose the former; treating it as authoritative avoids silently reverting a deliberate product decision, while the required follow-ups keep the docs and safety testing honest.

## 8. Subscription/premium gating

**Decision**: Photo calorie tracking is a core (non-premium-gated) feature — confirmed with the stakeholder during `/speckit.analyze`. No subscription-status check is required before the photo-reply flow.

**Rationale**: Avoids scope creep into Stripe/subscription logic not requested; recorded as an explicit Assumption in spec.md rather than an open question, since it's now a confirmed product decision, not a placeholder.

## 9. Scheduling the once-daily report

**Decision**: Use an external scheduled trigger (cron-style, e.g. Railway/Render scheduled job or an existing scheduler already used by the morning push) hitting an internal `app/scheduler/eod_trigger.py` endpoint periodically (e.g. every 5–15 minutes); the handler filters to users whose local time has just crossed their fixed report time and who don't yet have a `daily_reports` row for today.

**Rationale**: FastAPI has no built-in cron; an external trigger survives process restarts more reliably than an in-process scheduler (e.g. APScheduler) on ephemeral Railway/Render deploys. The `daily_reports` unique constraint (#5) makes the handler safely re-invokable/idempotent.

**Alternatives considered**: In-process APScheduler — rejected as primary mechanism due to reliability concerns across restarts/deploys, though it remains a viable fallback if an external scheduler isn't already in place for the existing morning push.
