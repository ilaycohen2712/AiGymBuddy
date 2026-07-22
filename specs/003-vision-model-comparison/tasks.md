---

description: "Task list for Vision Model Abstraction & Comparison"
---

# Tasks: Vision Model Abstraction & Comparison

**Input**: Design documents from `/specs/003-vision-model-comparison/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included — plan.md's Technical Context explicitly calls for unit tests
on the registry/scoring logic and an integration test for the end-to-end
comparison flow, on top of this codebase's existing test-first culture
(`prompt-tester` agent, `tests/test_calorie_accuracy.py`).

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3)
so each can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, or US3 — maps to spec.md's user stories
- File paths are exact and relative to the repository root

## Path Conventions

Single backend project (existing `app/` layout — see plan.md's Project
Structure). No frontend/mobile split.

---

## Phase 1: Setup

**Purpose**: Groundwork that has no dependency on the new abstraction itself

- [ ] T001 Create `scripts/__init__.py` (new `scripts/` package at repo root) so `scripts/compare_vision_models.py` can later be run as `python -m scripts.compare_vision_models`
- [ ] T002 [P] Update `tests/fixtures/food_photos/README.md` to document the new optional `expected_protein_g`, `expected_carbs_g`, `expected_fat_g` manifest fields (additive to the existing `expected_calories`), per data-model.md's `accuracy_scores` design

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared abstraction and schema every user story builds on

**⚠️ CRITICAL**: No user story task can start until this phase is complete

- [ ] T003 Write migration `app/db/migrations/0003_vision_model_comparison.sql`: create `model_candidates`, `comparison_runs`, `model_results`, `accuracy_scores` tables and add nullable `meals.model_id` column, exactly per data-model.md (types, checks, FKs, `UNIQUE (comparison_run_id, model_id, fixture_image)` on `model_results`)
- [ ] T004 [P] Define the `VisionModelClient` Protocol and a `MODEL_REGISTRY: dict[str, VisionModelClient]` with at least two entries (e.g. `"claude-sonnet-5"`, `"claude-opus-4-8"`) in `app/services/vision_models.py`, per contracts/vision_model_client.md
- [ ] T005 [P] Add `live_vision_model_id: str` to the `Settings` class in `app/config.py`, defaulting to the model id `app/services/vision.py` uses today (`"claude-sonnet-5"`)
- [ ] T006 Insert a `model_candidates` seed row for every `MODEL_REGISTRY` key from T004 (in the migration from T003 or a follow-up statement in the same file) so `meals.model_id` and `model_results.model_id` FKs have valid targets from the start (depends on: T003, T004)

**Checkpoint**: Schema exists, the registry exists, config exists — user story work can now begin.

---

## Phase 3: User Story 1 - Compare multiple models on the same photos (Priority: P1) 🎯 MVP

**Goal**: A team member runs two or more candidate models against the same
fixture photos in one comparison run and sees each model's calorie/macro
results grouped per photo; one model's failure never blocks the others.

**Independent Test**: Run the CLI against ≥2 registered models and the
fixture set; verify `model_results` has one row per (model, photo) and stdout
groups every photo's models together, with a live webhook request during the
run unaffected (covered structurally — comparison code never touches
`settings.live_vision_model_id` or the live call path).

### Tests for User Story 1

- [ ] T007 [P] [US1] Unit tests for `MODEL_REGISTRY` resolution (unknown id raises) and per-pair failure handling (schema-invalid response recorded as `status='failed'` without raising past the caller) in `tests/unit/test_vision_comparison.py`
- [ ] T008 [P] [US1] Integration test: a comparison run across 2 fake `VisionModelClient`s (one always-succeeds, one always-fails) × the fixture manifest, asserting every `(model, photo)` pair gets a `model_results` row, the failing model doesn't affect the succeeding model's rows, and `comparison_runs.status` reaches `completed`, in `tests/integration/test_vision_comparison_flow.py`

### Implementation for User Story 1

- [ ] T009 [US1] Implement `app/db/vision_comparison_queries.py`: `create_comparison_run(pool) -> uuid`, `record_model_result(pool, run_id, model_id, fixture_image, status, foods=None, total_calories=None, protein_g=None, carbs_g=None, fat_g=None, confidence=None, error_message=None)`, `complete_comparison_run(pool, run_id)`, `get_model_results(pool, run_id)` (depends on: T003)
- [ ] T010 [US1] Implement `run_comparison(pool, model_ids, fixtures_dir) -> uuid` in `app/services/vision_comparison.py`: create a run, iterate every `(model_id, manifest entry)` pair, call `MODEL_REGISTRY[model_id].analyze(...)`, catch `ValueError`/`json.JSONDecodeError` as a `failed` result (with `error_message`), persist each result immediately (not buffered), sum per-food macros into `protein_g`/`carbs_g`/`fat_g` for `ok` results, then mark the run `completed` (depends on: T004, T009)
- [ ] T011 [US1] Implement `scripts/compare_vision_models.py`: parse `--models` (comma-separated, ≥2, validated against `MODEL_REGISTRY`) and `--fixtures-dir` (default `tests/fixtures/food_photos/`), call `run_comparison`, print a grouped per-photo/per-model summary table to stdout, exit codes per contracts/compare_vision_models_cli.md (depends on: T010)

**Checkpoint**: User Story 1 is fully functional and independently testable/demoable via the CLI.

---

## Phase 4: User Story 2 - Score model accuracy against known answers (Priority: P2)

**Goal**: Every candidate model in a completed comparison run gets an
aggregate MAE-percent accuracy score per nutrient (calories, protein, carbs,
fat), excluding failed results and photos without ground truth for that
nutrient.

**Independent Test**: Run a comparison across the full labeled fixture set
and query `accuracy_scores` for the run; verify one row per `(model,
metric)` with a plausible `mean_absolute_error_pct` and a `sample_count` that
excludes failures/missing ground truth.

### Tests for User Story 2

- [ ] T012 [P] [US2] Unit tests for the MAE-percent scoring function: correct aggregation across multiple photos, exclusion of `failed` `model_results` rows, exclusion of photos missing that nutrient's manifest ground truth, in `tests/unit/test_vision_comparison.py` (same file as T007 — add alongside, not parallel with it)

### Implementation for User Story 2

- [ ] T013 [US2] Add `expected_protein_g`/`expected_carbs_g`/`expected_fat_g` (each optional) to at least one sample entry pattern documented in `tests/fixtures/food_photos/manifest.json` handling — i.e., ensure manifest loading tolerates entries with or without these fields (depends on: T002)
- [ ] T014 [US2] Implement `record_accuracy_scores(pool, run_id, scores)` and `get_accuracy_scores(pool, run_id)` in `app/db/vision_comparison_queries.py` (depends on: T009)
- [ ] T015 [US2] Implement `score_accuracy(model_results, manifest) -> list[AccuracyScore]` in `app/services/vision_comparison.py`, computing MAE% per `(model_id, metric)` using the same method as `tests/test_calorie_accuracy.py`, and call it from `run_comparison` right before marking the run `completed` (depends on: T010, T013, T014)
- [ ] T016 [US2] Extend `scripts/compare_vision_models.py`'s stdout summary to print each model's aggregate accuracy scores after the per-photo grouping (depends on: T011, T015)

**Checkpoint**: User Stories 1 and 2 both work independently and together — a single CLI run now produces grouped results and accuracy scores.

---

## Phase 5: User Story 3 - Switch the live bot to a different model (Priority: P3)

**Goal**: A team member designates a new live model via a deliberate config
change; subsequent live photos are analyzed by that model with no other
behavior change, and every meal row records which model produced it.

**Independent Test**: Send a live food photo through the webhook path, then
change `live_vision_model_id` and send another; verify each resulting `meals`
row's `model_id` matches the model that was live at that time, and replies/
meal-grouping/daily-totals are unchanged.

### Tests for User Story 3

- [ ] T017 [P] [US3] Extend `tests/contract/test_webhook_image.py` (or add a case) asserting the created meal's `model_id` equals `settings.live_vision_model_id` at request time, and is unaffected by a concurrently "in-progress" comparison run

### Implementation for User Story 3

- [ ] T018 [US3] Add `model_id: str | None` to `MealRecord` in `app/db/queries.py`; thread a `model_id` parameter through `MealRepository.create_meal`/`append_to_meal` and `AsyncpgMealRepository`'s SQL (depends on: T003)
- [ ] T019 [P] [US3] Update `InMemoryMealRepository` in `tests/fakes.py` to accept and store the new `model_id` parameter, matching T018's signature
- [ ] T020 [US3] Refactor `app/services/vision.py`'s `analyze_photo` to resolve `MODEL_REGISTRY[settings.live_vision_model_id]` (from `app/services/vision_models.py`) and delegate to it, preserving its existing public signature and return shape exactly (depends on: T004, T005)
- [ ] T021 [US3] Update `app/services/meal_logging.py` to pass `settings.live_vision_model_id` through as `model_id` on every `create_meal`/`append_to_meal` call (depends on: T018, T020)

**Checkpoint**: All three user stories are independently functional; live traffic is fully attributable and switchable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation and documentation that spans all three stories

- [ ] T022 [P] Update `.claude/skills/db-schema/SKILL.md` to list the four new tables and the `meals.model_id` column, per data-model.md
- [ ] T023 Run `pytest tests/test_calorie_accuracy.py -v` to confirm the existing single-model MAE regression gate (Constitution I) still passes unaffected by the `vision.py` refactor
- [ ] T024 Run `pytest tests/unit/test_vision_comparison.py tests/integration/test_vision_comparison_flow.py tests/contract/test_webhook_image.py -v`
- [ ] T025 Walk through all four scenarios in [quickstart.md](quickstart.md) end-to-end against a local Postgres + real `ANTHROPIC_API_KEY`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends only on Foundational
- **User Story 2 (Phase 4)**: Depends on Foundational; T013/T014/T015 also depend on US1's `run_comparison`/`vision_comparison_queries.py` (T009, T010) since accuracy scoring runs inside the same comparison flow
- **User Story 3 (Phase 5)**: Depends only on Foundational — has no dependency on US1 or US2 and can be built in parallel with either
- **Polish (Phase 6)**: Depends on all three user stories

### Within Each User Story

- Tests before implementation (T007/T008 before T009–T011; T012 before T013–T016; T017 before T018–T021)
- Repository/query layer before orchestration layer before CLI/caller
- Story complete and checkpointed before moving to the next priority (if working sequentially)

### Parallel Opportunities

- T002 (Setup) can run alongside T001
- T004 and T005 (Foundational) can run in parallel — different files
- T007 and T008 (US1 tests) can run in parallel — different files
- Once Foundational is done, **US3 can be developed entirely in parallel with US1/US2** — it touches `app/services/vision.py`, `app/db/queries.py`, and `app/services/meal_logging.py`, none of which US1/US2 touch
- T017 and T019 (US3) can run in parallel with each other

---

## Parallel Example: Foundational + User Story 1

```bash
# After T003 (migration) lands, in parallel:
Task: "Define VisionModelClient Protocol + MODEL_REGISTRY in app/services/vision_models.py"      # T004
Task: "Add live_vision_model_id setting to app/config.py"                                        # T005

# Once Foundational is checkpointed, in parallel:
Task: "Unit tests for registry resolution and failure handling in tests/unit/test_vision_comparison.py"          # T007
Task: "Integration test for comparison run against fakes in tests/integration/test_vision_comparison_flow.py"    # T008
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything else)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run the CLI against ≥2 models and the fixture set; confirm grouped output and per-pair failure isolation
5. This alone delivers the spec's core research capability (raw side-by-side comparison)

### Incremental Delivery

1. Setup + Foundational → schema, registry, config ready
2. Add User Story 1 → validate independently → team can already eyeball model differences
3. Add User Story 2 → validate independently → comparisons now produce an evidence-based ranking
4. Add User Story 3 → validate independently → a research finding can now actually be shipped to live users, with full traceability
5. Each story adds value without breaking the previous ones

### Parallel Team Strategy

With two developers after Foundational is checkpointed:

- Developer A: User Story 1 → User Story 2 (sequential — US2 builds on US1's run/query plumbing)
- Developer B: User Story 3 (fully independent of A's work)

---

## Notes

- [P] tasks touch different files with no unmet dependency
- [Story] labels map every user-story-phase task back to spec.md's US1/US2/US3
- Every `model_results` row is schema-validated before insert (Constitution IV) — no task should persist an unvalidated model response
- The `vision.py` refactor (T020) must not change its existing public signature — anything calling `analyze_photo` today keeps working unchanged
- Commit after each task or logical group; stop at each phase checkpoint to validate that story independently
