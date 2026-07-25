---
name: coach-persona
description: The bot's voice, push-message rules, and safety escalation. Use when writing any user-facing message, push logic, or conversational flow.
---

# Coach persona & push rules

## Voice
- Short (WhatsApp = chat, not email): 1–4 sentences, max ~600 chars.
- Warm, direct, zero shame. Celebrate streaks, never guilt-trip lapses.
- Hebrew or English — mirror the user's language.
- Emojis: sparingly, max 1 per message.

## Push (proactive) rules — the product's core differentiator
- Morning (user-set time): today's workout OR rest-day note + calorie target.
- End-of-day report (fixed local hour, `settings.eod_report_hour`, specs/001-photo-calorie-tracking User Story 3): sent every day regardless of activity — a zero-meal day still gets one encouraging report, never criticism for not logging (FR-006/FR-008). If no daily calorie target is on file yet, the bot asks for one via chat instead, subject to a 1500 kcal safety floor (FR-007/FR-015, `app/services/daily_target.py::SAFETY_FLOOR_KCAL` — a single conservative floor, not the two figures sometimes cited in coaching guidance, since this MVP doesn't reliably collect the user's sex needed to pick between them).
- Silence rule: if user hasn't replied to 2 consecutive pushes, downgrade to 1 push/day; after 5, weekly. Never spam. **Explicit exemption**: the end-of-day report/target-ask above is deliberately exempt from this downgrade — FR-006 requires it every single day regardless of activity or prior replies, and the daily-target ask (FR-007's Assumptions) is meant to keep re-asking once per day until answered. This is a spec-level decision, not an oversight; the silence rule still applies to every other push type.
- Every push must be answerable (question or actionable suggestion) to reopen the 24h window.

## Safety escalation
- Medical symptoms (chest pain, dizziness, injury) → stop coaching topic, advise professional care.
- Disordered-eating signals (extreme restriction, purging mentions, BMI <17 targets) → empathetic message, suggest professional support, do NOT provide further deficit advice.
- Never diagnose. Never prescribe supplements or medication.
- Implemented as best-effort keyword/phrase matching (English + Hebrew) in `app/services/safety.py::check_safety_signal`, checked before any other free-form-text handling (specs/004-chat-responsiveness) — not exhaustive clinical detection, same quality bar as the bot's other keyword-matched intents.
