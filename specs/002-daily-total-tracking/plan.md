# Implementation Plan: Daily Calorie & Macro Total Tracking

**Branch**: `002-daily-total-tracking` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-daily-total-tracking/spec.md`

## Summary

A user can text the bot asking for their running total at any time and get back the sum of calories/macros logged so far that calendar day. The sum is maintained by upserting `daily_totals` (extended with `carbs_g`/`fat_g`) at meal-log time — completing a postcondition `001-photo-calorie-tracking`'s webhook contract already specified but never implemented — rather than recomputed live per request, because a live per-request sum would silently misattribute past meals once time zones become per-user and mutable (violates FR-014). Each user gets a stored `time_zone` (new `users` column), defaulted from their WhatsApp number's country code at creation, and updated automatically when they either share a WhatsApp location (reverse-geocoded offline) or mention a place in text (extracted via a small, cheap Claude call) — so the midnight reset boundary follows them without a settings screen.

## Technical Context

**Language/Version**: Python 3.11+ (existing stack, unchanged)

**Primary Dependencies**: FastAPI, asyncpg, anthropic (existing); adding `phonenumbers` (phone number → country region, for the initial time-zone default) and `timezonefinder` (lat/lng → IANA time zone, offline, for WhatsApp location shares)

**Storage**: PostgreSQL (Supabase) — extends existing `daily_totals` and `users` tables via a new migration file, no new tables

**Testing**: pytest + pytest-asyncio, following this repo's existing patterns: unit tests with monkeypatched `queries`/`get_pool` (`tests/unit/`), contract tests against the FastAPI `TestClient` with a stubbed DB layer (`tests/contract/`), an in-memory fake repository (`tests/fakes.py`)

**Target Platform**: Linux server (Render), stateless FastAPI process — unchanged

**Project Type**: Single backend project (existing `app/` layout, no new top-level structure)

**Performance Goals**: A total-request reply is a single indexed primary-key lookup (`daily_totals` by `user_id, date`) — no LLM call, no perceptible added delay versus existing bot replies (SC-003). The place-mention extraction call (Haiku-class model) runs in the same request/reply cycle as any other free-form text message today; given current traffic (a handful of users), this is negligible — revisit only if usage grows enough for it to matter.

**Constraints**: No passive access to a user's phone location or IP (WhatsApp Cloud API doesn't expose either) — time-zone updates while traveling depend entirely on the user sharing a location or mentioning a place, per spec Assumptions. A meal's local-day bucketing must be fixed at the moment it's logged, using whatever time zone was on file *then* — never recomputed later — so a subsequent time-zone change can't retroactively reattribute it (FR-014).

**Scale/Scope**: Two active users today; no scale-driven design pressure. Optimize for correctness and simplicity over throughput.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Accuracy honesty**: No new calorie/macro estimation happens here — this feature sums numbers `001-photo-calorie-tracking`'s vision pipeline already produced and validated. Totals are presented as ±20% ranges (FR-006), the same convention as individual meal replies. PASS.
- **II. Push, not pull**: This feature is deliberately reactive (on-demand query), not proactive — considered and explicitly scoped out in spec Assumptions ("a separate, future feature... not a new proactive push message"). Not a violation: the constitution asks every feature to *consider* its proactive dimension, and this one did, with a documented reason to defer it. PASS (with this note, not a Complexity Tracking entry).
- **III. Safety first**: No new diet/medical advice surface. Existing safety-escalation behavior is unaffected and untouched by this feature. PASS.
- **IV. Schema discipline**: DB changes only via a new migration file (`0004_daily_totals_and_timezone.sql`). The Claude-based place-extraction output is schema-validated — checked against Python's `zoneinfo.available_timezones()` before ever being persisted to `users.time_zone`; anything that doesn't validate is treated as ambiguous/unrecognized (FR-013), never stored. The new extraction prompt lives in a versioned file, `app/prompts/timezone_extraction.md`, per the existing convention. PASS.
- **V. Platform independence**: The new WhatsApp `location` message-type handling lives in `app/whatsapp/`; timezone-derivation and daily-total logic live in `app/services/`, channel-agnostic. PASS.
- **Security requirements**: Reuses existing webhook signature verification (no change). New logging (timezone updates, total requests) masks `wa_phone` the same way existing meal-logging logs already do (`_mask` helper). No new secrets — `timezonefinder` is offline/no API key, and place-extraction reuses the existing `ANTHROPIC_API_KEY`. PASS.

No violations — Complexity Tracking table not needed.

**Post-Phase-1 re-check**: Design artifacts (research.md, data-model.md, contracts/, quickstart.md) introduce no new surface not already covered above — same gates re-checked, still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-daily-total-tracking/
├── plan.md              # This file (__SPECKIT_COMMAND_PLAN__ command output)
├── research.md          # Phase 0 output (__SPECKIT_COMMAND_PLAN__ command)
├── data-model.md        # Phase 1 output (__SPECKIT_COMMAND_PLAN__ command)
├── quickstart.md        # Phase 1 output (__SPECKIT_COMMAND_PLAN__ command)
├── contracts/           # Phase 1 output (__SPECKIT_COMMAND_PLAN__ command)
└── tasks.md             # Phase 2 output (__SPECKIT_COMMAND_TASKS__ command - NOT created by __SPECKIT_COMMAND_PLAN__)
```

### Source Code (repository root)

```text
app/
├── db/
│   ├── migrations/
│   │   └── 0004_daily_totals_and_timezone.sql   # NEW: carbs_g/fat_g on daily_totals, time_zone on users
│   └── queries.py                # NEW: get_daily_total, upsert_daily_total, get/set users.time_zone
├── services/
│   ├── meal_logging.py           # CHANGED: upsert daily_totals (local-date-bucketed) on create/append
│   ├── daily_total.py            # NEW: total-request recognition + reply formatting (US1/US2)
│   └── timezone.py               # NEW: default-from-phone, location→tz, text-place→tz (US3/US4)
├── prompts/
│   └── timezone_extraction.md    # NEW: versioned prompt for text place-mention extraction
└── whatsapp/
    └── webhook.py                # CHANGED: new `location` message-type branch; text dispatch
                                   # tries total-request, then best-effort place-mention, before
                                   # falling through to existing (unhandled) behavior

tests/
├── contract/
│   └── test_webhook_image.py     # CHANGED: new tests for location messages, total-request text
├── unit/
│   ├── test_meal_logging.py      # CHANGED: daily_totals upsert coverage
│   ├── test_daily_total.py       # NEW
│   └── test_timezone.py          # NEW
└── fakes.py                      # CHANGED: extend in-memory fakes if needed for daily_totals
```

**Structure Decision**: Single existing backend project (`app/`), no new top-level structure. New logic slots into the existing `services/`, `db/`, `whatsapp/`, `prompts/` layout exactly as `001-photo-calorie-tracking` and `003-vision-model-comparison` already do.

## Complexity Tracking

No Constitution Check violations — table not needed.

Two new dependencies are added (not a constitution violation, but worth recording the reasoning): `phonenumbers` (parses a WhatsApp `wa_phone` into a country region for the initial time-zone default) and `timezonefinder` (offline lat/lng → IANA time zone for location shares). Both were chosen over hand-rolling a country-calling-code or geo-boundary lookup table: calling codes are variable-length and genuinely ambiguous without a real library (e.g. "1" alone doesn't disambiguate US/Canada/Caribbean NANP members), and a hand-built lat/lng-to-timezone table would either be inaccurate near boundaries or require bundling the same reference data these libraries already ship. Neither adds a network call or a new secret.
