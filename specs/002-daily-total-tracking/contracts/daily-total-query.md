# Contract: On-demand daily total query (WhatsApp text)

## Trigger

`POST /webhook` — inbound message type `text`, whose body matches a recognized total-request phrase (Hebrew or English), and the user has no pending clarifying question outstanding (that flow still takes priority, unchanged).

## Preconditions

- `X-Hub-Signature-256` verified (unchanged, existing behavior).
- Message not already processed (existing `wa_message_id` dedupe check).
- No pending photo clarification for this user.

## Behavior

1. Resolve the user's current calendar date using their stored `users.time_zone`.
2. Look up `daily_totals` for `(user_id, that date)`.
3. If no row exists (zero meals logged that day): reply with a short, friendly "nothing logged yet today" message — not an error, not a `0-0 kcal` literal range (FR-002, User Story 1 Acceptance Scenario 2).
4. If a row exists: reply with the calorie and macro totals as a ±20% range, in the same format/voice as an individual meal reply (FR-006) — e.g. "So far today: about X-Y kcal (protein ~Ag, carbs ~Bg, fat ~Cg)."
5. Record the inbound message (existing dedupe/record convention) once the reply is sent.

## Postconditions

- The reply always reflects every meal logged so far in the current local day, regardless of what time the request arrives (SC-001).
- Reading the total never mutates it — this is a pure read, no write to `daily_totals` happens here (writes only happen at meal-log time, per data-model.md).
