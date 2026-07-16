---

description: "Task list template for feature implementation"
---

# Tasks: Photo Calorie Tracking MVP

**Input**: Design documents from `/specs/001-photo-calorie-tracking/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — plan.md's Technical Context and the project constitution (Principle I: prompt regression via labeled fixtures; Principle IV: LLM outputs schema-validated) both require test coverage for this feature, so test tasks are generated alongside implementation.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths follow plan.md's Project Structure: `app/` (backend) and `tests/` at repository root — this is a greenfield repo, so Setup/Foundational tasks create these from scratch.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization — nothing under `app/` or `tests/` exists yet.

- [ ] T001 Create backend project structure per plan.md (`app/whatsapp/`, `app/prompts/`, `app/services/`, `app/scheduler/`, `app/db/`, `tests/contract/`, `tests/integration/`, `tests/unit/`, `tests/fixtures/food_photos/`)
- [ ] T002 Initialize Python 3.11+ project with FastAPI, pytest, Claude API client, and Postgres client dependencies in `pyproject.toml`/`requirements.txt`
- [ ] T003 [P] Configure linting/formatting (ruff/black) and pytest config in `pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Setup migration framework and initial schema migration (baseline `users`, `meals`, `daily_totals`, `messages` tables per `.claude/skills/db-schema/SKILL.md`) in `app/db/migrations/0001_init.sql`
- [ ] T005 [P] Implement webhook signature verification (`X-Hub-Signature-256`) and the `hub.challenge` verification handshake in `app/whatsapp/webhook.py`
- [ ] T006 [P] Implement media download helper (fetch image by media ID, 5-min-valid download URL) in `app/whatsapp/media.py`
- [ ] T007 [P] Implement outbound WhatsApp message sending (mark inbound read, typing indicator, POST to Graph API messages endpoint, 4096-char max) in `app/whatsapp/send.py`
- [ ] T008 Create FastAPI app entrypoint wiring the webhook route (GET verification + POST events) in `app/main.py` (depends on T005)
- [ ] T009 [P] Implement environment/config management (WhatsApp app secret/token, Claude API key, DB URL) in `app/config.py`

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Log a meal from one or more photos (Priority: P1) 🎯 MVP

**Goal**: User sends a food photo; bot replies with a calorie/macro range; multiple photos of the same meal sent close together combine into one entry.

**Independent Test**: Send one or more food photos for a single meal via the webhook and verify the reply contains one combined calorie/macro range, with no dependency on daily totals or reports.

### Tests for User Story 1

- [ ] T010 [P] [US1] Contract test for inbound image webhook handling per `contracts/webhook-image-message.md` in `tests/contract/test_webhook_image.py`
- [ ] T011 [P] [US1] Integration test: two photos sent within the 10-minute grouping window combine into one meal entry in `tests/integration/test_meal_grouping.py`
- [ ] T012 [P] [US1] Accuracy regression test against labeled fixtures (Constitution I gate: >5% MAE regression fails) in `tests/test_calorie_accuracy.py` using `tests/fixtures/food_photos/`

### Implementation for User Story 1

- [ ] T013 [P] [US1] Author versioned calorie-vision prompt per `.claude/skills/calorie-estimation/SKILL.md` schema in `app/prompts/calorie_vision.md`
- [ ] T014 [US1] Implement vision pipeline client (call Claude API with T013's prompt, validate response against the `{"foods":[...],"total_calories":0,"confidence":0.0,"clarifying_question":null}` schema) in `app/services/vision.py` (depends on T013)
- [ ] T015 [US1] Implement meal entry queries (create meal row; append foods + `photo_media_ids` to an existing row) in `app/db/queries.py` (depends on T004)
- [ ] T016 [US1] Implement meal-logging service: check for an open meal within the 10-minute grouping window, create-or-append, recompute combined totals per `research.md` #2 in `app/services/meal_logging.py` (depends on T014, T015)
- [ ] T017 [US1] Wire image-message handling into the webhook: download media (T006) → vision (T014) → meal-logging (T016) → reply with the ±20% calorie/macro range in `app/whatsapp/webhook.py` (depends on T016, T006, T007, T008)
- [ ] T018 [US1] Handle photos that can't be identified as food: reply explaining, exclude from daily total (FR-010) in `app/services/meal_logging.py`
- [ ] T019 [US1] Add structured logging for meal-logging operations, phone numbers masked, no PII (Security requirement) in `app/services/meal_logging.py`

**Checkpoint**: User Story 1 is fully functional and independently testable/demoable.

---

## Phase 4: User Story 2 - Track a running daily total (Priority: P2)

**Goal**: Running total of calories/macros consumed so far today, reset at the start of each new calendar day per the user's local time zone.

**Independent Test**: Log several food photos in a day and verify the running total reflects the sum of all logged estimates, correctly reset from the previous day.

### Tests for User Story 2

- [ ] T020 [P] [US2] Unit test for daily total aggregation math (calories, protein, carbs, fat) in `tests/unit/test_daily_totals.py`
- [ ] T021 [P] [US2] Integration test for day-rollover reset (new calendar day starts fresh, per user's local time zone) in `tests/integration/test_daily_rollover.py`

### Implementation for User Story 2

- [ ] T022 [US2] Migration adding `daily_totals.carbs_g` and `daily_totals.fat_g` columns in `app/db/migrations/0002_daily_totals_macros.sql`
- [ ] T023 [US2] Implement `daily_totals` upsert logic (calories, protein, carbs, fat), mirroring the existing `protein_g` pattern, in `app/services/daily_totals.py` (depends on T022)
- [ ] T024 [US2] Implement day-rollover logic keyed to the user's local time zone in `app/services/daily_totals.py`
- [ ] T025 [US2] Wire `daily_totals` updates into the meal-logging flow from User Story 1 in `app/services/meal_logging.py` (depends on T023, T016)

**Checkpoint**: User Stories 1 AND 2 both work independently — running total always equals the sum of the day's logged estimates (SC-005).

---

## Phase 5: User Story 3 - Receive an end-of-day report (Priority: P3)

**Goal**: Once per day, every day regardless of activity, send total calories/macros and generated feedback vs. the user's daily calorie target (collected once via chat, subject to a safety floor).

**Independent Test**: Advance to the configured report time for a user with ≥1 logged meal and verify exactly one report is sent containing totals and feedback; repeat for a user with zero meals logged.

### Tests for User Story 3

- [ ] T026 [P] [US3] Contract test for daily-target collection and safety-floor rejection per `contracts/daily-target-collection.md` in `tests/contract/test_daily_target.py`
- [ ] T027 [P] [US3] Contract test for end-of-day report schema and once-per-day idempotency per `contracts/eod-report.md` in `tests/contract/test_eod_report.py`
- [ ] T028 [P] [US3] Integration test: a zero-meal day still receives exactly one encouraging (non-critical) report in `tests/integration/test_eod_report_flow.py`

### Implementation for User Story 3

- [ ] T029 [US3] Migration adding `users.daily_calorie_target` and new `daily_reports` table (unique on `user_id, date`) in `app/db/migrations/0003_daily_target_and_reports.sql`
- [ ] T030 [P] [US3] Author versioned end-of-day feedback prompt (`{"feedback_text": "", "tone": "encouraging|neutral"}`, ≤600 chars, no medical advice/crash-diet pressure) per `contracts/eod-report.md` in `app/prompts/eod_feedback.md`
- [ ] T031 [US3] Implement daily-target collection service: ask via chat, parse numeric reply, reject values below the 1200/1500 kcal safety floor and re-ask (FR-015) in `app/services/daily_target.py` (depends on T029)
- [ ] T032 [US3] Implement end-of-day report service: read today's `daily_totals`, call the T030 prompt, validate its output schema in `app/services/eod_report.py` (depends on T029, T030)
- [ ] T033 [US3] Implement idempotent report send — insert into `daily_reports`, treating a unique-constraint conflict as "already sent, skip" (FR-006, SC-003) in `app/services/eod_report.py` (depends on T032)
- [ ] T034 [US3] Implement the scheduler trigger: per-user local-time check, invoke daily-target collection (T031) if no target set, else the end-of-day report (T033) in `app/scheduler/eod_trigger.py` (depends on T031, T033)
- [ ] T035 [US3] Ensure every proactive message (target ask + report) is phrased to be answerable, keeping the 24h window open (FR-009) in `app/services/daily_target.py` and `app/services/eod_report.py`
- [ ] T036 [US3] Run the `coach-simulator` agent against the new daily-regardless-of-activity report cadence (validates the deliberate deviation from `coach-persona/SKILL.md` flagged in plan.md's Constitution Check)

**Checkpoint**: All three user stories are independently functional — this is the full MVP.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T037 [P] Update `.claude/skills/coach-persona/SKILL.md`'s evening check-in bullet to match the new daily-report cadence (plan.md's flagged follow-up from the Constitution Check note)
- [ ] T038 [P] Add consistent structured logging/error handling across `app/scheduler/` and `app/services/` (no PII, phone numbers masked)
- [ ] T039 Run all four `quickstart.md` validation scenarios end-to-end
- [ ] T040 [P] Documentation pass: confirm `CLAUDE.md` and skill references remain accurate after implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational; integrates with US1's meal-logging flow (T025 depends on T016) but is independently testable via T020/T021
- **User Story 3 (Phase 5)**: Depends on Foundational; reads `daily_totals` maintained by US2 (T032 depends on data US2 produces) but is independently testable via T026–T028 against seeded data
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Parallel Opportunities

- All Setup tasks marked [P] (T003) can run in parallel with T001/T002 once those are underway
- Foundational [P] tasks T005, T006, T007, T009 can run in parallel (different files)
- US1 tests T010–T012 can run in parallel; US1 impl T013 can run standalone before T014
- US2 tests T020–T021 can run in parallel
- US3 tests T026–T028 can run in parallel; T030 can run in parallel with T029

---

## Parallel Example: User Story 1

```bash
# Tests together:
Task: "Contract test for inbound image webhook in tests/contract/test_webhook_image.py"
Task: "Integration test for photo grouping in tests/integration/test_meal_grouping.py"
Task: "Accuracy regression test in tests/test_calorie_accuracy.py"

# Then the prompt file standalone, before the client that depends on it:
Task: "Author calorie-vision prompt in app/prompts/calorie_vision.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `quickstart.md` Scenario 1 independently
5. Deploy/demo if ready — a user can already log a meal photo and get a range back

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add User Story 1 → validate via quickstart Scenario 1 → demo (MVP!)
3. Add User Story 2 → validate via quickstart Scenario 2 → demo
4. Add User Story 3 → validate via quickstart Scenarios 3 & 4 (including `coach-simulator`) → demo
5. Polish phase → close out `coach-persona` doc drift and run full quickstart suite

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to its user story for traceability
- Commit after each task or logical group
- T036 (coach-simulator) and T037 (coach-persona doc update) are release gates for US3, per CLAUDE.md's workflow rule for push-logic changes — do not skip them before merging US3
