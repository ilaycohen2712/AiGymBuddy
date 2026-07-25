# Implementation Plan: Text-Based Meal Logging

**Branch**: `005-text-meal-logging` | **Date**: 2026-07-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-text-meal-logging/spec.md`

## Summary

Let users log a meal by typing a food description with quantities (e.g. "100 grams rice, 120 grams chicken breast") instead of only sending a photo. A new versioned prompt (`app/prompts/calorie_text.md`), mirroring `calorie_vision.md`'s schema and accuracy discipline, does detection and estimation in a single LLM call: given free-form text, it either returns a food estimate (same `foods`/`total_calories`/`confidence`/`clarifying_question` shape as the vision pipeline) or signals that the text isn't a food-logging message at all. A new `app/services/text_meal_logging.py` module wraps this, reusing `meal_logging.py`'s existing grouping-window, daily-totals-accumulation, and range-reply-formatting logic rather than duplicating it. It's wired into `webhook.py`'s existing text-dispatch chain as one more None-returning layer, after the pending-clarification and daily-target layers and before `chat_fallback`.

## Technical Context

**Language/Version**: Python 3.11+ (existing stack, no change)

**Primary Dependencies**: FastAPI, asyncpg, Claude API (Messages API, text-only — no vision content block needed for this path)

**Storage**: PostgreSQL (Supabase) — one schema migration (nullable `photo_media_id`, new `text_entries` column on `meals`)

**Testing**: pytest (unit + contract), `prompt-tester` agent for the new prompt, `coach-simulator` agent for the detection-precedence behavior (SC-004)

**Target Platform**: Existing Railway/Render-deployed FastAPI server — no new deployment target

**Project Type**: Single project (existing web-service backend) — no new top-level structure

**Performance Goals**: Text-based logging reply latency should be comparable to photo-based logging (a few seconds, dominated by the Claude API round trip) — no stricter real-time requirement than the existing photo path

**Constraints**: Must not alter `chat_fallback.py`'s existing, already-tested safety-first precedence or its non-generative reply guarantee (FR-008, FR-010) — achieved by having the new detection layer perform its own safety check internally and defer (return `None`) on a hit, rather than restructuring `chat_fallback.py`

**Scale/Scope**: Same single-tenant coaching-bot scale as the rest of the bot — no new scale dimension

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Accuracy honesty** — PASS, with a known pre-existing gap. The new `calorie_text.md` prompt gets the same range-not-exact presentation and needs the same fixture-based regression discipline as `calorie_vision.md`. `tests/fixtures/food_photos/manifest.json` regression testing only covers image fixtures today; text-estimation fixtures are a separate, currently-nonexistent set. This plan does not block on creating them (matching this repo's existing accepted gap for vision fixtures), but `prompt-tester` must still review the new prompt qualitatively before merge, same as every prompt change this session.
- **II. Push, not pull** — N/A. This is a reactive (pull) feature, not a new proactive message; it doesn't touch push logic.
- **III. Safety first** — PASS, by construction (see Constraints above): the new detection layer checks `safety.check_safety_signal` first and defers to the existing, unchanged safety path on any hit. No new medical/diet content is introduced.
- **IV. Schema discipline** — PASS, with a migration required. `meals.photo_media_id` is currently `NOT NULL`, which has no valid value for a text-originated meal. Resolved via migration (see data-model.md): make it nullable, add a `text_entries text[]` column paralleling `photo_media_ids`, so a meal's origin and contribution count are both still derivable without a photo. LLM output continues to validate against a fixed JSON schema before persistence, same as the vision pipeline.
- **V. Platform independence** — PASS. New logic lives in `app/services/`, channel-agnostic; only the WhatsApp-specific wiring point (`app/whatsapp/webhook.py`'s existing text branch) is WhatsApp-specific, unchanged in kind from how photo/clarification handling already works.
- **Security requirements** — PASS, with a required hardening step. This is the second place in the bot (after the photo-clarification-answer path) where free-form user text reaches an LLM prompt whose output becomes both a user-facing reply and persisted data. The new prompt must carry the same untrusted-input framing as `calorie_vision.md` rule 11 (user text is descriptive food content only, never an instruction) from the start, not bolted on after a live incident like last time.

No violations requiring Complexity Tracking justification.

## Project Structure

### Documentation (this feature)

```text
specs/005-text-meal-logging/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not created by this command)
```

### Source Code (repository root)

```text
app/
├── prompts/
│   └── calorie_text.md              # NEW — versioned text-estimation prompt (mirrors calorie_vision.md)
├── services/
│   ├── meal_logging.py              # EXTENDED — reply formatters / grouping / totals reused, not duplicated
│   └── text_meal_logging.py         # NEW — detection + estimation entrypoint, mirrors meal_logging.py's photo entrypoints
├── db/
│   ├── migrations/
│   │   └── 0008_text_meal_logging.sql   # NEW — nullable photo_media_id, add text_entries column
│   └── queries.py                   # EXTENDED — MealRecord/MealRepository gain text_entries; create/append accept a text-originated contribution
└── whatsapp/
    └── webhook.py                   # EXTENDED — _handle_text_message gains one more None-returning layer

tests/
├── contract/
│   └── test_webhook_text.py         # NEW or EXTENDED — end-to-end text-logging + precedence regression coverage
└── unit/
    └── test_text_meal_logging.py    # NEW — detection/estimation/grouping unit coverage
```

**Structure Decision**: Single existing project, no new top-level directories. This feature is additive within the established `app/prompts/`, `app/services/`, `app/db/`, `app/whatsapp/` layout, following the same file-per-concern pattern already used for photo-based meal logging (spec 001) and the clarification/fallback chain (spec 004).
