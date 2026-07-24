# Phase 1 Data Model: Chat Responsiveness

This feature adds **no new tables and no new columns**. It's routing/reply
behavior over data that already exists (or, per research.md #1, deliberately
does not yet exist for "calorie target"). The only schema change is widening
an existing constraint.

## messages (altered)

Per `.claude/skills/db-schema/SKILL.md`'s existing `messages` table
(`id, user_id, direction, wa_message_id, body, kind, created_at`), widen the
`kind` CHECK constraint (already widened once by 002's
`0005_widen_messages_kind_for_location.sql`) to add one more value:

| kind value | Meaning |
|---|---|
| `text` | existing |
| `image` | existing |
| `template` | existing |
| `location` | existing (002) |
| `other` | **NEW** — any inbound message type this feature acknowledges but has no dedicated handler for (voice, sticker, document, video, contacts, interactive, button, order, reaction, system, or any future WhatsApp type) |

Migration: `app/db/migrations/0006_widen_messages_kind_for_other.sql`,
following the same drop-and-recreate-constraint pattern as `0005`.

## Non-DB entities

These exist only in-process (Python), not as persisted rows — per
research.md #3, that's deliberate: nothing here is state, just a fixed
mapping from a recognized signal to a fixed reply string.

### Supported Question (spec Key Entity)

A registered `(matcher, handler)` pair in `app/services/chat_fallback.py`.
For this feature's initial scope (research.md #1), exactly one entry:

| matcher | handler | Data source |
|---|---|---|
| `daily_total._is_daily_total_request` | `daily_total.handle_daily_total_request` | `daily_totals` table (spec 002) |

Future entries (e.g. "daily calorie target", once spec 001's User Story 3
ships) are added the same way — no schema change needed here when that
happens.

### Safety Signal

Two fixed categories, each a phrase list (English + Hebrew) plus one fixed
reply string, per `coach-persona` skill's existing rules:

| Category | Trigger (examples) | Reply behavior |
|---|---|---|
| Medical | chest pain, dizziness, injury-related phrases | Stop the coaching topic, advise professional care |
| Disordered-eating | extreme restriction, purging mentions, very-low-BMI targets | Empathetic message, suggest professional support, no further deficit advice |

Checked before the supported-question matcher (research.md #4) — a safety
signal always wins over a coincidental keyword overlap with a supported
question.

## Relationships

```text
messages.kind — no FK, just a widened CHECK constraint (unchanged shape)
```

No relationship diagram beyond that — this feature's entities are pure
in-process dispatch logic, not persisted state.
