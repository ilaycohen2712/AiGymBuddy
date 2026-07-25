# Tasks: Text-Based Meal Logging

**Input**: Design documents from `/specs/005-text-meal-logging/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — this project consistently includes test tasks for every feature (see specs/001-004), and Constitution I/IV require regression coverage for accuracy and schema changes.

**Organization**: Tasks are grouped by user story. US1 (log a meal by text) and US2 (existing flows unaffected) are both P1 — they ship together, but US1's tasks make the new capability work and US2's tasks are the regression guard proving nothing else broke.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 or US2
- File paths are exact, repo-relative

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Schema, shared repository/model changes, and the new prompt — nothing in US1 or US2 can be implemented until this phase is done.

- [X] T001 Write migration `app/db/migrations/0008_text_meal_logging.sql`: `ALTER TABLE meals ALTER COLUMN photo_media_id DROP NOT NULL;` and `ALTER TABLE meals ADD COLUMN text_entries text[] NOT NULL DEFAULT '{}';` (data-model.md)
- [X] T002 [P] Add `text_entries: list[str]` field to `MealRecord` in `app/db/queries.py`
- [X] T003 [P] Update `MealRepository` protocol's `create_meal`/`append_to_meal` signatures to accept optional `media_id: str | None` / `text_entry: str | None` (replacing the required `media_id: str` positional) in `app/db/queries.py`
- [X] T004 Update `AsyncpgMealRepository.create_meal`/`append_to_meal` to persist `text_entries` and accept a nullable `photo_media_id`, per T003's signature, in `app/db/queries.py` (depends on T002, T003)
- [X] T005 [P] Update `InMemoryMealRepository` fake in `tests/fakes.py` to match the new `create_meal`/`append_to_meal` signature and track `text_entries`
- [X] T006 Generalize `log_meal_photo` into a shared `log_meal_contribution(user_id, foods, total_calories, confidence, repo, now=None, model_id=None, media_id=None, text_entry=None)` helper in `app/services/meal_logging.py`, keeping `log_meal_photo` as a thin `media_id`-only wrapper so existing photo call sites are unaffected (depends on T004)
- [X] T007 Add `_contribution_count(meal) -> int` (`len(photo_media_ids) + len(text_entries)`) in `app/services/meal_logging.py` and switch `_reply_for_logged_meal`'s `len(meal.photo_media_ids) > 1` check to use it (depends on T006)
- [X] T008 [P] Write `app/prompts/calorie_text.md` per `contracts/calorie-text-prompt.md` (schema + rules 1-7, including the untrusted-input framing in rule 5)
- [X] T009 [P] Implement `analyze_text(text: str) -> dict` in `app/services/text_analysis.py` — calls the Claude Messages API with `calorie_text.md`, validates the response against the schema in `contracts/calorie-text-prompt.md` before returning
- [X] T010 Extend `set_pending_clarification`/`get_pending_clarification` in `app/db/queries.py` to accept `media_id: str | None` (currently required) so a text-originated clarification can be persisted with no photo, using `media_type="text"` as the discriminator (depends on T004)
- [X] T011 [P] Unit test: `AsyncpgMealRepository`/`InMemoryMealRepository.create_meal`/`append_to_meal` accept `text_entry` XOR `media_id` and persist correctly in `tests/unit/test_meal_logging.py`

**Checkpoint**: Schema, repository, prompt, and analysis wrapper are ready — US1 implementation can begin.

---

## Phase 2: User Story 1 - Log a meal by text (Priority: P1) 🎯 MVP

**Goal**: A user can type a food description with quantities and get a calorie-range reply, with the meal logged and counted toward their daily total — same as photo-based logging.

**Independent Test**: Send a text food description to the bot with no prior context; verify a calorie-range reply (not fallback) and a new `meals` row with `text_entries` populated and `photo_media_id IS NULL`.

### Tests for User Story 1

- [X] T012 [P] [US1] Unit test: a clear food description with quantities (e.g. "100g rice, 120g chicken breast") produces a logged meal and calorie-range reply in `tests/unit/test_text_meal_logging.py`
- [X] T013 [P] [US1] Unit test: a text description sent within 10 minutes of an open meal (photo- or text-originated) appends to it rather than starting a new meal, using the existing grouping window in `tests/unit/test_text_meal_logging.py`
- [X] T014 [P] [US1] Unit test: Hebrew text input (e.g. "150 גרם אורז ו-100 גרם חזה עוף") is estimated and logged the same as the English equivalent in `tests/unit/test_text_meal_logging.py`
- [X] T015 [P] [US1] Unit test: a food description with a materially missing quantity (e.g. "chicken and rice") sets a pending clarifying question and does not log a meal in `tests/unit/test_text_meal_logging.py`
- [X] T016 [P] [US1] Unit test: replying to a text-originated pending clarification with an amount completes the analysis and logs the meal, via the existing `meal_logging.handle_clarification_reply` path, capped at one round trip in `tests/unit/test_meal_logging.py`
- [X] T017 [P] [US1] Contract test: `POST /webhook` with a text message describing food logs a meal end-to-end and the reply contains a calorie range in `tests/contract/test_webhook_text.py`

### Implementation for User Story 1

- [X] T018 [US1] Implement `handle_text_meal_description(user_id, wa_phone, text) -> str | None` in new `app/services/text_meal_logging.py`, per `contracts/text-dispatch-precedence.md`: call `analyze_text`, return `None` if `is_food_description` is `false`, otherwise ask the clarifying question or log via `log_meal_contribution(text_entry=text)` and return the formatted reply (depends on T006, T007, T009)
- [X] T019 [US1] Wire text-originated clarifying-question persistence/completion into `handle_text_meal_description` (T018) and `meal_logging.handle_clarification_reply`, reusing the existing pending-clarification mechanism extended in T010 (depends on T010, T018)
- [X] T020 [US1] Wire `text_meal_logging.handle_text_meal_description` into `webhook.py::_handle_text_message`'s dispatch chain, after the existing `daily_target.handle_daily_target_reply` layer and before `chat_fallback.handle_free_form_text` (depends on T018)

**Checkpoint**: User Story 1 is fully functional and independently testable via the webhook.

---

## Phase 3: User Story 2 - Existing text flows keep working unchanged (Priority: P1)

**Goal**: Prove the new detection layer never intercepts a pending clarification, a safety-relevant message, a supported question, or general fallback text.

**Independent Test**: Exercise each existing text pathway with the new layer active; confirm each produces its original, unchanged reply.

### Tests for User Story 2

- [X] T021 [P] [US2] Contract test: a pending clarifying-question answer (photo- or text-originated) is completed as a clarification, never treated as an independent new food-description message, even when the reply text also reads like a food description in `tests/contract/test_webhook_text.py`
- [X] T022 [P] [US2] Contract test: a message matching a safety signal that also mentions food gets the safety escalation reply, and no `meals` row is written in `tests/contract/test_webhook_text.py`
- [X] T023 [P] [US2] Contract test: "what's my total today" still returns the existing daily-total reply, not a meal-logging attempt in `tests/contract/test_webhook_text.py`
- [X] T024 [P] [US2] Contract test: an unrelated message (e.g. "how's it going") still gets the existing fixed fallback reply, unchanged in `tests/contract/test_webhook_text.py`
- [X] T025 [P] [US2] Contract test: text containing an embedded instruction (e.g. "ignore previous instructions...") does not get complied with — falls through to the fixed fallback, no meal logged, per `calorie_text.md` rule 5 in `tests/contract/test_webhook_text.py`

### Implementation for User Story 2

- [X] T026 [US2] Verify/harden `handle_text_meal_description` (T018) to call `safety.check_safety_signal(text)` first and return `None` immediately on any hit, before calling `analyze_text` at all, per `contracts/text-dispatch-precedence.md` precedence step 1, in `app/services/text_meal_logging.py` (depends on T018, T022)

**Checkpoint**: Both user stories independently functional; no regressions in existing text dispatch.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [X] T027 [P] Update `.claude/skills/calorie-estimation/SKILL.md` to document the new `calorie_text.md` prompt and its `is_food_description` field
- [X] T028 [P] Update `.claude/skills/whatsapp-api/SKILL.md` to document the new dispatch layer and its position in the text-message chain
- [X] T029 [P] Update `.claude/skills/db-schema/SKILL.md` for the nullable `photo_media_id` and new `text_entries` column
- [X] T030 Run `prompt-tester` agent against `app/prompts/calorie_text.md`
- [X] T031 Run `coach-simulator` agent to simulate a mixed week of messages (food descriptions, questions, small talk, safety-relevant messages) and validate SC-004 (no misfires either direction)
- [X] T032 Run `reviewer` agent (webhook + schema change)
- [X] T033 Run full test suite (`pytest tests/ -q`) and `ruff check .`
- [X] T034 Walk through all six `quickstart.md` scenarios manually against a local dev DB

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. Blocks Phases 2 and 3.
- **User Story 1 (Phase 2)**: Depends on Phase 1 completion.
- **User Story 2 (Phase 3)**: Depends on Phase 1 and on T018 (US1's core entrypoint) existing, since US2's tests exercise that same entrypoint's precedence behavior — not independently implementable before US1's implementation tasks, even though it's a separate story.
- **Polish (Final Phase)**: Depends on Phases 2 and 3 both being complete.

### Within Each Phase

- Schema (T001) before any repository code (T002-T005)
- Repository changes (T002-T005) before `meal_logging.py` generalization (T006-T007)
- Prompt (T008) and analysis wrapper (T009) can proceed in parallel with repository work — independent files
- Tests within US1/US2 (marked [P]) can all be written in parallel — same file in most cases (`test_text_meal_logging.py`, `test_webhook_text.py`) but independent test functions with no shared state
- Implementation tasks within a story follow their stated `depends on` chain

### Parallel Opportunities

- T002, T003, T005, T008, T009 (Phase 1) — different files, no interdependency
- T012-T017 (US1 tests) — different test functions, can be written together before T018-T020 implementation
- T021-T025 (US2 tests) — same, independent of US1's test functions
- T027, T028, T029 (skill docs) — different files

---

## Parallel Example: Phase 1 (Foundational)

```bash
# Launch together — independent files:
Task: "Add text_entries field to MealRecord in app/db/queries.py"                          # T002
Task: "Update MealRepository protocol signatures in app/db/queries.py"                      # T003
Task: "Write app/prompts/calorie_text.md per contracts/calorie-text-prompt.md"               # T008
Task: "Implement analyze_text() in app/services/text_analysis.py"                            # T009
```

## Parallel Example: User Story 1 tests

```bash
Task: "Unit test: clear food description logs a meal (tests/unit/test_text_meal_logging.py)"          # T012
Task: "Unit test: text appends to an open meal within grouping window (tests/unit/test_text_meal_logging.py)"  # T013
Task: "Unit test: Hebrew text input (tests/unit/test_text_meal_logging.py)"                             # T014
Task: "Unit test: missing quantity triggers clarifying question (tests/unit/test_text_meal_logging.py)"  # T015
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 (Foundational) — schema, repository, prompt, analysis wrapper.
2. Complete Phase 2 (User Story 1) — the feature works end-to-end via the webhook.
3. **STOP and VALIDATE**: run `quickstart.md` Scenarios 1-4 manually against a local dev DB.
4. Complete Phase 3 (User Story 2) before merge — this is the safety/regression guard, not optional polish; do not ship US1 alone to production.
5. Complete Final Phase (skill docs, agents, full suite, remaining quickstart scenarios) before opening the PR, per CLAUDE.md's custom-agent requirements for prompt and conversational-flow changes.

### Notes

- Every prior feature in this repo (001-004) followed this pattern: schema/foundational work first, then story implementation, then mandatory agent runs (`prompt-tester` for any prompt change, `coach-simulator` for any conversational-flow change, `reviewer` for webhook/data changes) before merge — Phase Final's T030-T032 are not optional steps.
- `tests/fixtures/food_photos/manifest.json`-style labeled fixtures for `calorie_text.md` accuracy regression testing do not exist yet (same accepted gap as the vision prompt) — `prompt-tester` (T030) should flag this explicitly rather than silently passing, consistent with how it's handled every other prompt change in this project.
