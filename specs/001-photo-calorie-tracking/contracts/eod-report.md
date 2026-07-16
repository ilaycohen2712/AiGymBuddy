# Contract: End-of-day report

## Trigger
`app/scheduler/eod_trigger.py`, invoked periodically by an external scheduler (research.md #9). For each user whose local time has just crossed their fixed report time and who has no `daily_reports` row for today:

## Preconditions
- `users.daily_calorie_target` is set (else run the `daily-target-collection.md` flow instead, see that contract).

## Behavior
1. Read the user's `daily_totals` row for today (defaults to zero totals if no meals logged — FR-008).
2. Call the `eod_feedback` prompt (versioned at `app/prompts/eod_feedback.md`) with: total calories, total protein/carbs/fat, and `daily_calorie_target`.

   **Output schema** (validated before use, per Constitution IV):
   ```json
   {"feedback_text": "", "tone": "encouraging|neutral"}
   ```
   - `feedback_text`: ≤600 chars, coach-persona voice, no medical advice or crash-diet pressure regardless of how far over/under target the user is (FR-016, SC-008). On a zero-meal day, `tone` must be `"encouraging"` and `feedback_text` must not criticize the lack of logging (FR-008).
3. Compose and send the report message: total calories eaten, total protein/carbs/fat, and `feedback_text`. Phrased to be answerable (Constitution II).
4. Insert a row into `daily_reports` (user_id, date, snapshot totals, feedback_text, sent_at). The `UNIQUE (user_id, date)` constraint makes step 3–4 safe to retry if the scheduler fires more than once for the same user/day — a duplicate insert fails and the handler treats that as "already sent, skip."

## Postconditions
- At most one `daily_reports` row per `(user_id, date)` (SC-003).
- 100% of `feedback_text` values contain no medical advice/crash-diet language (SC-008) — verified via the `coach-simulator` agent and prompt-level instruction, not a mechanical runtime check.
