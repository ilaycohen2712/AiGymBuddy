# Implementation Plan: Photo Calorie Tracking MVP

**Branch**: `001-photo-calorie-tracking` | **Date**: 2026-07-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-photo-calorie-tracking/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Users log meals by sending food photos on WhatsApp; the bot replies with a calorie/macro range per meal (combining photos sent close together into one meal), maintains a running daily total, and sends exactly one end-of-day report per day (total calories, total protein/carbs/fat, and coach-voice feedback vs. the user's daily calorie target — collected once via chat and reused thereafter, subject to a safety floor). Built as an extension of the existing WhatsApp bot backend: new prompt for feedback generation, two small schema additions (`users.daily_calorie_target`, `daily_totals.carbs_g`/`fat_g`), a new `daily_reports` table for once-per-day idempotency, and a scheduled job to trigger the report per user's local time.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI (webhook/API layer), Claude API (vision analysis + feedback generation), Meta WhatsApp Business Cloud API (messaging), APScheduler or an external cron trigger hitting an internal endpoint (once-daily report dispatch)

**Storage**: PostgreSQL (Supabase) — extends existing `users`, `meals`, `daily_totals` tables; adds `daily_reports`

**Testing**: pytest — unit tests (aggregation math, safety-floor validation, grouping-window logic), contract tests (webhook image handling, prompt output schemas), existing accuracy regression suite (`tests/test_calorie_accuracy.py` against `tests/fixtures/food_photos/`, unchanged >5% MAE gate), plus the `coach-simulator` agent for the new push behavior before release

**Target Platform**: Linux server (Railway/Render), stateless FastAPI process + scheduled trigger

**Project Type**: single backend web-service (WhatsApp is the only UI; no frontend)

**Performance Goals**: Photo → reply within 60s p95 (SC-001); end-of-day reports for all users dispatched within their local report-time window with ≤1 minute drift

**Constraints**: Outbound messages ≤600 chars (coach-persona voice); every proactive message must be answerable to keep the WhatsApp 24h window open; calorie/macro values shown to users are always ranges, never exact figures; daily calorie targets below 1200/1500 kcal rejected

**Scale/Scope**: MVP scope — one new user-facing flow (photo logging → daily total → end-of-day report) added to an existing single-tenant WhatsApp coaching bot; no specific concurrent-user target specified, design should not require re-architecture at low-thousands of daily active users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Accuracy honesty | Calorie/macro totals always shown as ranges (±20%, per existing calorie-estimation convention); prompt changes go through `prompt-tester` agent against labeled fixtures | PASS |
| II. Push, not pull | End-of-day report and target-collection prompt are bot-initiated and phrased to be answerable | PASS — **see note below** |
| III. Safety first | Daily target floor enforced (1200/1500 kcal, FR-015); feedback generation explicitly forbidden from medical advice/crash-diet pressure (FR-016, SC-008); disordered-eating escalation per coach-persona still applies | PASS |
| IV. Schema discipline | New/changed LLM outputs (feedback message) validated against a versioned schema before send; DB changes via migration files only; new prompt lives in `app/prompts/` | PASS |
| V. Platform independence | WhatsApp-specific code (webhook parsing, sending, media download) stays in `app/whatsapp/`; meal-logging/report/target logic in channel-agnostic `app/services/` | PASS |
| Security | Webhook signature verification unchanged; no PII in logs (phone numbers masked); secrets via env vars | PASS |

**Note on Principle II**: `.claude/skills/coach-persona/SKILL.md` currently documents the evening check-in as firing "only if user logged ≥1 meal today." This spec's FR-008 (resolved via explicit user clarification during `/speckit.specify`) deliberately changes that to "every day, regardless of activity," with zero-meal days showing encouraging feedback instead of criticism. This is treated as an intentional, spec-level supersession of that line in coach-persona for this report — not a constitution violation — but two follow-ups are required before release: (1) run the `coach-simulator` agent against the new daily-regardless-of-activity behavior, since it changes push cadence, and (2) update `coach-persona/SKILL.md`'s check-in bullet afterward so the two documents don't drift out of sync.

### Post-Phase-1 re-check

Re-evaluated after data-model.md/contracts/quickstart.md were drafted: no new violations introduced. The `daily_reports` unique-constraint design (data-model.md) reinforces Principle II's "never spam" intent by making "at most one report per day" a DB-enforced guarantee rather than app-logic-only. All gates remain PASS with the single documented note above.

## Project Structure

### Documentation (this feature)

```text
specs/001-photo-calorie-tracking/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
app/
├── whatsapp/
│   ├── webhook.py          # inbound POST, signature verification, media download
│   ├── send.py             # outbound message sending
│   └── templates.py        # pre-approved template messages (existing)
├── prompts/
│   ├── calorie_vision.md   # existing — unchanged output schema
│   └── eod_feedback.md     # new — versioned feedback-generation prompt
├── services/
│   ├── meal_logging.py     # photo grouping window, meal entry creation/append
│   ├── daily_totals.py     # running total maintenance, day-rollover reset
│   ├── daily_target.py     # target collection via chat, safety-floor validation
│   └── eod_report.py       # report composition, feedback generation, idempotent send
├── scheduler/
│   └── eod_trigger.py      # per-user local-time check, invoked by cron/external scheduler
├── db/
│   ├── migrations/         # new migration files (see data-model.md)
│   └── queries.py
└── main.py                 # FastAPI app entrypoint

tests/
├── contract/
│   ├── test_webhook_image.py
│   └── test_eod_feedback_schema.py
├── integration/
│   └── test_meal_to_report_flow.py
├── unit/
│   ├── test_daily_totals.py
│   ├── test_grouping_window.py
│   └── test_target_safety_floor.py
└── fixtures/
    └── food_photos/        # existing labeled fixtures (accuracy regression, unchanged)
```

**Structure Decision**: Single backend project (Option 1). No frontend exists or is needed — WhatsApp is the sole client. New code is added as thin vertical slices inside the existing `app/whatsapp/`, `app/prompts/`, `app/db/` layout implied by the project's skills (db-schema, whatsapp-api, calorie-estimation), plus a new `app/services/` and `app/scheduler/` for the channel-agnostic logic this feature introduces (Constitution V).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No unjustified violations — the one deliberate deviation (Principle II note above) is a documented, spec-driven scope decision rather than a complexity/architecture violation, so no entry is required here.
