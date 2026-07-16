# Contract: Daily calorie target collection

## Trigger
The first time an end-of-day report would fire for a user (`app/scheduler/eod_trigger.py`) and `users.daily_calorie_target` is null.

## Flow
1. Instead of sending the end-of-day report, send a chat message asking the user for their daily calorie target. Message must be answerable (keeps 24h window open) and follow coach-persona voice (≤600 chars, warm, ≤1 emoji).
2. On the user's reply, parse the numeric target.
   - If **below the safety floor** (1200/1500 kcal per coaching guidance): reject, explain briefly why, and re-ask (FR-015). Do not store the value.
   - If **at/above the floor**: store in `users.daily_calorie_target` (FR-007). Confirm briefly.
3. Once set, the end-of-day report resumes on the next scheduled trigger; the value is never asked for again (reused across days).
4. If the user never responds, no end-of-day report is sent for that user until a valid target is provided (per spec Assumptions) — the scheduler's next run simply re-attempts the ask, subject to the project's existing silence-rule downgrade (coach-persona: after 2 unanswered pushes, downgrade frequency; after 5, weekly).

## Output contract
No structured schema — this is a plain conversational exchange, not an LLM-graded output. The numeric parse (accepting things like "2000", "2,000 kcal", "around 2000") is a simple extraction, not a generative step.
