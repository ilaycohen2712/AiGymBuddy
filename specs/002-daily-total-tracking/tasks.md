---

description: "Task list for Daily Calorie & Macro Total Tracking"
---

# Tasks: Daily Calorie & Macro Total Tracking

**Input**: Design documents from `/specs/002-daily-total-tracking/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included — this codebase has an established test-first culture (unit tests with monkeypatched `queries`/`get_pool`, contract tests via `TestClient`, integration tests for multi-step flows like meal grouping), and `001`/`003`'s plans both included tests on the same basis.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3/P4) so each can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3, or US4 — maps to spec.md's user stories
- File paths are exact and relative to the repository root

## Path Conventions

Single backend project (existing `app/` layout — see plan.md's Project Structure). No frontend/mobile split.

---

## Phase 1: Setup

**Purpose**: Groundwork that has no dependency on the feature's own logic

- [ ] T001 Add `phonenumbers` and `timezonefinder` to `pyproject.toml` dependencies

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, storage, and the meal-logging write path every user story depends on

**⚠️ CRITICAL**: No user story task can start until this phase is complete

- [ ] T002 Write migration `app/db/migrations/0003_daily_totals_and_timezone.sql`: add `carbs_g numeric NOT NULL DEFAULT 0` and `fat_g numeric NOT NULL DEFAULT 0` to `daily_totals`, and `time_zone text NOT NULL DEFAULT 'UTC'` to `users`, per data-model.md
- [ ] T003 [P] Implement `derive_default_timezone(wa_phone: str) -> str` in new file `app/services/timezone.py`, using `phonenumbers` to resolve a region code and a small region→IANA-zone mapping, falling back to `"UTC"` if unresolvable, per research.md #2 (depends on: T001)
- [ ] T004 Update `get_or_create_user_id` in `app/db/queries.py` to pass a `time_zone` value derived via `derive_default_timezone` (T003) when inserting a new user (depends on: T002, T003)
- [ ] T005 [P] Add `get_daily_total(pool, user_id, date) -> dict` and `upsert_daily_total(pool, user_id, date, *, calories, protein_g, carbs_g, fat_g) -> None` to `app/db/queries.py` — the upsert is additive via `ON CONFLICT (user_id, date) DO UPDATE SET x = daily_totals.x + EXCLUDED.x` for every numeric column, matching the `pending_clarifications` upsert style already in this file (depends on: T002)
- [ ] T006 [P] Add `get_user_time_zone(pool, user_id) -> str` and `update_user_time_zone(pool, user_id, time_zone: str) -> None` to `app/db/queries.py` (depends on: T002)
- [ ] T007 Wire `daily_totals` upserts into `create_meal` and `append_to_meal` in `app/services/meal_logging.py`: resolve the user's current `time_zone` (T006), convert the meal's UTC `logged_at` to that zone to get the local calendar date, and call `upsert_daily_total` (T005) — `create_meal` upserts the new meal's full totals; `append_to_meal` upserts only the *newly added* photo's delta (never the meal's whole recomputed total), so a combined meal is never double-counted (depends on: T004, T005, T006)

**Checkpoint**: Meals now populate `daily_totals` correctly, bucketed by each user's current local date at the moment they're logged — every user story below can now be implemented.

---

## Phase 3: User Story 1 - Ask for today's running total on demand (Priority: P1) 🎯 MVP

**Goal**: A user can text the bot at any time and get back the sum of calories/macros logged so far that calendar day.

**Independent Test**: Log one or more meals, send a total-request message at an arbitrary time, verify the reply states the correct sum; a user with zero meals logged gets a friendly zero-state reply instead of an error.

### Tests for User Story 1

- [ ] T008 [P] [US1] Unit test: `_is_daily_total_request` recognizes Hebrew and English total-request phrases and rejects unrelated text, in `tests/unit/test_daily_total.py`
- [ ] T009 [P] [US1] Unit test: `handle_daily_total_request` returns `None` without touching the DB for non-matching text, and returns a formatted reply sourced from `queries.get_daily_total` for matching text, in `tests/unit/test_daily_total.py`
- [ ] T010 [P] [US1] Contract test: `POST /webhook` with a total-request text message replies with the correct calorie/macro range; a zero-meals-yet user gets the friendly no-meals-yet message, in `tests/contract/test_webhook_image.py`

### Implementation for User Story 1

- [ ] T011 [US1] Implement `_is_daily_total_request(text: str) -> bool` (Hebrew + English phrase list) in new file `app/services/daily_total.py`
- [ ] T012 [US1] Implement `format_daily_total_reply(totals: dict) -> str` (±20% range, matching `format_range_reply`'s convention in `meal_logging.py`; a friendly fixed message when `calories` is zero) in `app/services/daily_total.py`
- [ ] T013 [US1] Implement `handle_daily_total_request(user_id, wa_phone, text) -> str | None` in `app/services/daily_total.py`: short-circuits to `None` on no phrase match (T011) without calling `get_pool()`; otherwise resolves "today" via the user's stored `time_zone` (T006) and `queries.get_daily_total` (T005), returning T012's formatted reply (depends on: T005, T006, T011, T012)
- [ ] T014 [US1] Wire `handle_daily_total_request` into `_handle_text_message` in `app/whatsapp/webhook.py`: call it when `handle_clarification_reply` returns `None`, before falling through to the existing "ignore unmatched text" behavior (depends on: T013)

**Checkpoint**: User Story 1 is fully functional and independently testable. This is the MVP (Setup + Foundational + US1).

---

## Phase 4: User Story 2 - Running total always matches logged meals (Priority: P2)

**Goal**: Every total request reflects the exact sum of meals logged so far that day — no drift, no double-counting, no missed entries.

**Independent Test**: Log several meals across a day and verify a total request after each one reflects the cumulative sum so far; verify a non-food photo and a grouped/combined meal are each handled correctly.

Foundational's additive-upsert design (T007) already guarantees these properties by construction — this phase is primarily dedicated verification, plus closing any gap the tests surface.

- [ ] T015 [P] [US2] Integration test: log three meals across a day (asking for the total after each), verify each reply reflects the cumulative sum so far, in `tests/integration/test_meal_grouping.py`
- [ ] T016 [P] [US2] Unit test: a photo not recognized as food (the `NOT_FOOD_REPLY` path) never calls `upsert_daily_total`, in `tests/unit/test_meal_logging.py`
- [ ] T017 [US2] Integration test: two photos combined into one meal within the existing 10-minute grouping window increment `daily_totals` by the combined delta exactly once, not twice, in `tests/integration/test_meal_grouping.py` (depends on: T007)

**Checkpoint**: User Stories 1 and 2 both independently verified.

---

## Phase 5: User Story 3 - Daily total resets at midnight in the user's own time zone (Priority: P3)

**Goal**: A user's running total starts fresh at midnight in whatever time zone is currently on file for them.

**Independent Test**: Log a meal before a user's local midnight, request the total again after that midnight has passed (simulated), verify the total reflects only the new day's meals.

Foundational (T007) already buckets by local date at write time, and User Story 1 (T013) already resolves "today" via the user's stored time zone at query time — this phase proves the reset boundary these produce is correct, including across users in different zones.

- [ ] T018 [P] [US3] Unit test: with a fixed/injected "now," a meal logged just before a user's local midnight stays in the current day's bucket, and a total request made just after that midnight reflects only the new day (zero, if nothing logged yet), in `tests/unit/test_daily_total.py`
- [ ] T019 [P] [US3] Unit test: two users with different stored `time_zone` values — one user's midnight passing does not reset or affect the other user's current-day total, in `tests/unit/test_daily_total.py`

**Checkpoint**: User Stories 1, 2, and 3 all independently verified — the reset boundary is correct per-user.

---

## Phase 6: User Story 4 - Time zone follows the user when they travel (Priority: P4)

**Goal**: A user's stored time zone updates automatically when they share their current WhatsApp location or mention a place they're in, without any manual settings change.

**Independent Test**: Establish a user's initial time zone, then have them share their location (or mention a place) from a different time zone, and verify subsequent total requests use the new time zone's midnight as the reset boundary — while meals already logged under the old time zone stay attributed to their original day.

### Tests for User Story 4

- [ ] T020 [P] [US4] Unit test: `extract_timezone_from_text` returns a valid IANA zone for a recognizable place mention and `None` for an ambiguous/unrecognized one (mocking the Claude call), in `tests/unit/test_timezone.py`
- [ ] T021 [P] [US4] Unit test: `timezone_from_location` returns a valid IANA zone for real coordinates, in `tests/unit/test_timezone.py`
- [ ] T022 [US4] Contract test: `POST /webhook` with a `location` message updates `users.time_zone` and replies with a confirmation; coordinates that don't resolve to a zone leave `time_zone` unchanged and reply explaining the location couldn't be used, in `tests/contract/test_webhook_image.py`
- [ ] T023 [US4] Integration test: a meal logged before a time-zone update (via a location share) stays attributed to its original day's `daily_totals` bucket after the update — proves FR-014 (no retroactive reattribution), in `tests/integration/test_meal_grouping.py`

### Implementation for User Story 4

- [ ] T024 [P] [US4] Write `app/prompts/timezone_extraction.md`: a versioned prompt (Haiku-class model) that extracts at most one place mention from a short message and returns an IANA time zone or nothing, per research.md #4
- [ ] T025 [US4] Implement `extract_timezone_from_text(text: str) -> str | None` in `app/services/timezone.py`: calls the Haiku-class model with T024's prompt, validates the result against `zoneinfo.available_timezones()`, returns `None` if missing or invalid (depends on: T024)
- [ ] T026 [P] [US4] Implement `timezone_from_location(latitude: float, longitude: float) -> str | None` in `app/services/timezone.py` using `timezonefinder`, validated against `zoneinfo.available_timezones()` (depends on: T001)
- [ ] T027 [US4] Add a `location` message-type branch (`_handle_location_message`) to `app/whatsapp/webhook.py`'s dispatch: resolve/dedupe the user (existing convention), call `timezone_from_location` (T026), update `users.time_zone` via `update_user_time_zone` (T006) and send a confirmation reply on success, or send a "couldn't use that location" reply on failure — never silent (depends on: T006, T026)
- [ ] T028 [US4] In `_handle_text_message` in `app/whatsapp/webhook.py`, after the existing clarification and total-request checks, independently run `extract_timezone_from_text` (T025) on the message body and silently update `users.time_zone` via `update_user_time_zone` (T006) if a valid zone comes back — no dedicated reply for this path (depends on: T006, T025)

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements spanning multiple user stories

- [ ] T029 [P] Update `.claude/skills/whatsapp-api/SKILL.md` to document the new `location` inbound message type
- [ ] T030 [P] Update `.claude/skills/db-schema/SKILL.md`'s `daily_totals`/`users` rows to reflect `carbs_g`, `fat_g`, and `time_zone`
- [ ] T031 Add structured logging (masked `wa_phone`, via the existing `_mask` helper) for total requests and time-zone updates, in `app/services/daily_total.py` and `app/services/timezone.py`
- [ ] T032 Run all of `quickstart.md`'s validation scenarios end-to-end
- [ ] T033 Run the `reviewer` agent before merging, since this touches the webhook and persisted user data (new message type, new columns)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational (Phase 2) completion.
  - US1 has no dependency on US2/US3/US4.
  - US2 and US3 both depend on Foundational's T007 (the write path) but not on each other or on US1's implementation — though in practice US1 is what makes them observable end-to-end, so implementing in priority order (US1 → US2 → US3 → US4) is the natural path.
  - US4 depends on Foundational's T006/T007 (time zone storage, write-once bucketing) but not on US1/US2/US3's code.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within Each User Story

- Tests before implementation.
- `app/services/*.py` logic before wiring into `app/whatsapp/webhook.py`.
- Story complete and checkpoint-verified before moving to the next priority.

### Parallel Opportunities

- T003 (timezone default) and T005/T006 (query functions) can run in parallel once T002 (migration) lands — different functions, same file (`queries.py`) for T005/T006 so coordinate if literally simultaneous, but no logical dependency between them.
- All test tasks marked `[P]` within a story phase can run in parallel (different test functions/files).
- T024 (prompt) and T026 (location→tz) can run in parallel — independent files.
- US2 and US3's test-writing can happen in parallel once Foundational is done, since both only *read* the write path Foundational already built.

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test: _is_daily_total_request phrase matching in tests/unit/test_daily_total.py"
Task: "Unit test: handle_daily_total_request short-circuit and reply behavior in tests/unit/test_daily_total.py"
Task: "Contract test: POST /webhook total-request reply in tests/contract/test_webhook_image.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1-2 independently
5. Deploy/demo if ready — a user can already ask for and receive their running total

### Incremental Delivery

1. Setup + Foundational → daily_totals is correctly populated as meals are logged
2. Add User Story 1 → test independently → deploy/demo (MVP!)
3. Add User Story 2 → test independently → deploy/demo (confidence in accuracy, not new user-visible behavior)
4. Add User Story 3 → test independently → deploy/demo (confidence in reset correctness, not new user-visible behavior)
5. Add User Story 4 → test independently → deploy/demo (the traveling-user capability)
6. Each story adds value (or confidence) without breaking previous stories

---

## Notes

- `[P]` tasks = different files, no dependencies
- `[Story]` label maps task to specific user story for traceability
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
