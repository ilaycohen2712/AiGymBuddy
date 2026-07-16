# Contract: Inbound food photo (WhatsApp webhook)

Per `.claude/skills/whatsapp-api/SKILL.md` — no changes to the webhook contract itself, this documents how an `image` message is routed for this feature.

## Trigger
`POST /webhook` — Meta WhatsApp Business Cloud API inbound event, message type `image`.

## Preconditions
- `X-Hub-Signature-256` verified (HMAC-SHA256 of raw body, App Secret) before any processing.
- Media fetched via media ID → `GET /{media-id}` → download URL (valid 5 min).

## Behavior (this feature)
1. Mark inbound message read; show typing indicator (analysis takes seconds).
2. Pass the downloaded image to the `calorie_vision` prompt pipeline (unchanged schema, see `data-model.md`).
3. If the response is not recognizable as food (per existing pipeline behavior): reply explaining the photo couldn't be identified; do not create/append a meal row (FR-010).
4. If recognizable:
   - If an open meal exists for this user within the 10-minute grouping window (`meals.logged_at` within 10 min of now, same user): append this photo's foods to that meal, add its media id to `photo_media_ids`, recompute `total_calories`/macros (FR-014).
   - Else: create a new `meals` row.
   - Reply once with the combined calorie/macro range for that meal (±20% of point estimate, per `research.md` #1) (FR-002, FR-003, FR-012).
5. Update `daily_totals` for the user's current calendar day (calories, protein, carbs, fat) (FR-004).

## Postconditions
- Reply sent within 60s p95 (SC-001).
- `daily_totals` reflects the sum of all of the day's meal entries at all times (SC-005).
