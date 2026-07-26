# Tasks: Gemini Flash Model Migration

**Input**: Design documents from `/specs/006-gemini-flash-migration/`

**Prerequisites**: plan.md, research.md, spec.md, quickstart.md

**Tests**: Included — the spec's schema-discipline and accuracy-regression
requirements (FR-005, SC-002, SC-003) are only verifiable through the
existing automated test suite and the prompt-tester/coach-simulator agents.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)

## Phase 1: Setup

- [X] T001 Add `google-genai` to `dependencies` in `pyproject.toml`; keep
      `anthropic` (still required by `ClaudeVisionClient` comparison
      entries, research.md #4). Install into the dev environment.
- [X] T002 Add `gemini_api_key: str = ""` to `app/config.py`
      (`Settings`, env var `GEMINI_API_KEY`, same pattern as
      `anthropic_api_key`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared Gemini client all four call sites depend on.

**⚠️ CRITICAL**: No call-site migration (Phase 3+) can start until this is done.

- [X] T003 Create `app/services/gemini_client.py`: a `genai.Client` singleton
      behind an async `get_client()`, using the same double-checked-lock
      pattern as the `_get_client()` functions being replaced
      (`Client(api_key=settings.gemini_api_key)`).

**Checkpoint**: `gemini_client.get_client()` is importable and returns a
working client — call-site migrations can now proceed.

---

## Phase 3: User Story 1 - Photo calorie estimate via Gemini Flash (Priority: P1) 🎯 MVP

**Goal**: Food-photo analysis is produced by Gemini Flash, via a new
registry entry, with the existing Claude entries preserved for comparison.

**Independent Test**: Send a labeled fixture photo through
`vision.analyze_photo`; confirm a schema-valid, ranged result attributable
to the new Gemini registry entry.

### Tests for User Story 1

- [X] T004 [P] [US1] Update `tests/unit/test_vision_comparison.py` /
      `tests/integration/test_vision_comparison_flow.py` fixtures only if
      they reference `MODEL_REGISTRY` keys by name in a way the new entry
      would collide with — confirm no collision, add a case that both the
      existing `claude-sonnet-5` and a new `gemini-flash-latest` key coexist
      in `MODEL_REGISTRY` (Edge Cases: comparison capability preserved).

### Implementation for User Story 1

- [X] T005 [US1] In `app/services/vision_models.py`, add `GeminiVisionClient`
      implementing the `VisionModelClient` Protocol: builds
      `google.genai.types.Part.from_bytes(data=image_bytes,
      mime_type=media_type)` + a text part, calls
      `client.aio.models.generate_content(model=self._model,
      contents=[...], config=types.GenerateContentConfig(system_instruction=
      _load_prompt(), max_output_tokens=4096))` via
      `gemini_client.get_client()`, extracts `response.text`, and reuses the
      existing `_extract_json_block` / `_validate_schema` unchanged
      (research.md #4, #6, #7).
- [X] T006 [US1] Register the new client in `MODEL_REGISTRY` under
      `"gemini-flash-latest"`, alongside the existing `claude-sonnet-5` /
      `claude-opus-4-8` entries (do not remove them — FR-008).
- [X] T007 [US1] In `app/config.py`, change
      `live_vision_model_id` default from `"claude-sonnet-5"` to
      `"gemini-flash-latest"`.
- [X] T007a [US1] Add `app/db/migrations/0009_gemini_flash_model_candidate.sql`
      seeding `model_candidates` with `('gemini-flash-latest', 'Gemini Flash')`
      — `meals.model_id` and `model_results.model_id` are FK'd to
      `model_candidates(id)` (0003_vision_model_comparison.sql), so a live
      meal insert with `model_id='gemini-flash-latest'` would violate that
      FK without this row. Discovered during implementation, not anticipated
      in plan.md's "no data-model.md" call — the registry gained a new
      logical entry even though no new table/column was needed.
- [ ] T008 [US1] Run the prompt-tester agent against the labeled fixture set
      (`tests/fixtures/food_photos/manifest.json`); confirm MAE regression
      ≤5% vs. the pre-migration Claude baseline (Constitution I, SC-002).
      If it fails, this story is not done — do not proceed to T009+.
      **BLOCKED in this environment**: requires a real `GEMINI_API_KEY` and
      live network access to the Gemini API, neither available in this
      sandbox — `tests/test_calorie_accuracy.py` is `skipif`-gated on
      exactly that key (now fixed to check `GEMINI_API_KEY` instead of
      `ANTHROPIC_API_KEY` — see Phase 6 note). Must be run with real
      credentials before this migration is considered production-ready.

**Checkpoint**: Live photo analysis runs on Gemini Flash; Claude vision
entries still work for comparison; accuracy gate passes.

---

## Phase 4: User Story 2 - Text-based food logging via Gemini Flash (Priority: P1)

**Goal**: Text food-description parsing is produced by Gemini Flash.

**Independent Test**: Send a labeled text fixture through
`text_analysis.analyze_text`; confirm a schema-valid, ranged result.

### Implementation for User Story 2

- [X] T009 [US2] In `app/services/text_analysis.py`, replace the module-level
      `anthropic.AsyncAnthropic` singleton (`_client`, `_client_lock`,
      `_get_client()`) with `gemini_client.get_client()`; replace the
      `client.messages.create(...)` call with
      `client.aio.models.generate_content(model=settings.live_vision_model_id,
      contents=user_content, config=types.GenerateContentConfig(
      system_instruction=_load_prompt(), max_output_tokens=1024))`; replace
      the Anthropic block-join with `response.text`. Leave
      `_extract_json_block` / `_validate_schema` unchanged.
- [X] T010 [P] [US2] Update `tests/unit/test_text_analysis.py` if it mocked
      `_get_client`/the Anthropic response shape (currently it only tests
      the pure `_extract_json_block` function — confirm no client-shape
      mocks need updating; add one if a live-call test exists).

**Checkpoint**: Live text-based food logging runs on Gemini Flash,
independent of US1/US3.

---

## Phase 5: User Story 3 - EOD feedback & timezone extraction via Gemini Flash (Priority: P2)

**Goal**: The two lower-frequency call sites (EOD coach feedback, timezone
extraction) run on Gemini Flash.

**Independent Test**: Trigger `eod_report.build_report` for a fixture user
and `timezone.extract_timezone_from_text` for a fixture message; confirm
correct, schema-valid output.

### Tests for User Story 3

- [X] T011 [P] [US3] Update `tests/unit/test_eod_report.py`'s `_FakeClient` /
      `_FakeResponse` / `_FakeMessages` doubles to match the Gemini SDK
      shape (a fake exposing `.text` directly instead of `.content` blocks),
      and retarget `monkeypatch.setattr(eod_report, "_get_client", ...)` to
      whatever the new call site actually calls (research.md #9).
- [X] T012 [P] [US3] Update `tests/unit/test_timezone.py`'s equivalent fake
      doubles the same way.

### Implementation for User Story 3

- [X] T013 [P] [US3] In `app/services/eod_report.py`, replace the
      `anthropic.AsyncAnthropic` singleton with `gemini_client.get_client()`;
      change `_FEEDBACK_MODEL = "claude-haiku-4-5"` to `_FEEDBACK_MODEL =
      "gemini-flash-latest"`; swap the `messages.create(...)` call for
      `generate_content(...)` (system_instruction, max_output_tokens=256);
      swap block-join for `response.text`. Leave `_extract_json_block` /
      `_validate_feedback` unchanged.
- [X] T014 [P] [US3] In `app/services/timezone.py`, apply the same swap:
      `_EXTRACTION_MODEL = "claude-haiku-4-5"` → `"gemini-flash-latest"`,
      client singleton, `generate_content(...)` (max_output_tokens=64),
      `response.text`. Leave the IANA-zone validation logic unchanged.
- [ ] T015 [US3] Run the coach-simulator agent to confirm EOD feedback tone,
      safety-escalation behavior, and push-rule (answerable message)
      compliance are unchanged (Constitution II/III, SC-005).
      **BLOCKED in this environment**: same credential/network limitation as
      T008 — the simulator needs to call the live (Gemini) EOD-feedback path
      with a real `GEMINI_API_KEY`.

**Checkpoint**: All four call sites run on Gemini Flash; US1/US2/US3 each
independently pass their own tests.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 Run `.venv/bin/python -m pytest tests/ -q` — full suite green.
- [X] T017 Run `ruff check .` — no lint regressions from the new/edited files.
- [ ] T018 Walk through `quickstart.md` Scenarios 1–7 manually (or via a dev
      webhook) to confirm end-to-end behavior, including Scenario 7 (no
      Anthropic dependency on the four live call sites) and Scenario 6
      (comparison feature still works with Claude candidates).
      **BLOCKED in this environment** for the same reason as T008/T015 (no
      real `GEMINI_API_KEY`/network access). Scenarios 5 (schema-invalid
      rejection) and the registry-coexistence half of Scenario 6 are covered
      by the automated suite (`test_vision_models.py`,
      `test_vision_comparison*.py`) and don't need live credentials; the
      rest need a real deploy/CI run with `GEMINI_API_KEY` set.
- [X] T019a Discovered during implementation: fixed
      `tests/test_calorie_accuracy.py`'s `skipif` gate, which checked
      `ANTHROPIC_API_KEY` — now checks `GEMINI_API_KEY`, matching the live
      pipeline's actual credential (it would otherwise never run once only
      `GEMINI_API_KEY` is configured, silently disabling the MAE regression
      gate this migration explicitly must satisfy, SC-002).
- [X] T019b Discovered during implementation: added
      `app/db/migrations/0009_gemini_flash_model_candidate.sql` (see T007a)
      — a required fix, not covered by plan.md's original file list.
- [X] T019 Grep the codebase for any remaining reference to
      `claude-sonnet-5`/`claude-haiku-4-5` as a *default* on a live call
      site (not a `MODEL_REGISTRY` comparison entry) to confirm FR-009 is
      fully satisfied.

---

## Dependencies & Execution Order

- **Setup (T001-T002)**: No dependencies — start immediately.
- **Foundational (T003)**: Depends on T001-T002 (needs the dependency and
  the API key setting). Blocks every call-site migration.
- **US1 (T004-T008)**, **US2 (T009-T010)**, **US3 (T011-T015)**: Each
  depends only on Foundational (T003) — independently implementable and
  testable, touch disjoint files, no cross-story dependencies.
- **Polish (T016-T019)**: Depends on all three user stories being complete.

### Parallel Opportunities

- T001 and T002 can run in parallel.
- Once T003 is done, US1/US2/US3 implementation can proceed in parallel
  (different files: `vision_models.py` vs `text_analysis.py` vs
  `eod_report.py`/`timezone.py`).
- Within US3, T011/T012 (test doubles) and T013/T014 (implementation) touch
  different files and can run in parallel with each other.

## Phase 7: Follow-up — Provider-swap abstraction for the other three call sites

**Purpose**: The vision call site could already swap providers cheaply via
`MODEL_REGISTRY` (spec 003). Requested as a follow-up: give
`text_analysis.py` / `eod_report.py` / `timezone.py` the same swappability,
rather than leaving them hardcoded to whichever provider is currently live.

- [X] T020 Create `app/services/text_models.py`: `TextModelClient` Protocol
      (`generate(system_instruction, user_content, max_tokens) -> str`),
      `ClaudeTextClient` / `GeminiTextClient` implementations, and
      `MODEL_REGISTRY` seeded with `claude-sonnet-5`, `claude-haiku-4-5`,
      and `gemini-flash-latest` — mirrors `vision_models.py` one level
      below the vision-specific (image-handling) concerns.
- [X] T021 Rewire `text_analysis.py`, `eod_report.py`, `timezone.py` to
      resolve a client from `MODEL_REGISTRY` (keyed by
      `settings.live_vision_model_id`, `_FEEDBACK_MODEL`,
      `_EXTRACTION_MODEL` respectively) and call `.generate(...)`, instead
      of calling `gemini_client.get_client()` directly. Each file's own
      prompt loading and JSON/plain-text extraction/validation is
      unchanged.
- [X] T022 Update `tests/unit/test_eod_report.py` and
      `tests/unit/test_timezone.py` to monkeypatch a `_FakeTextClient` into
      `MODEL_REGISTRY` (`monkeypatch.setitem`) instead of patching
      `gemini_client.get_client` / mocking the Gemini SDK response shape —
      tests now target the Protocol, not a specific provider's SDK.
- [X] T023 Add `tests/unit/test_text_models.py` asserting the registry has
      both Claude and Gemini entries and the right concrete types, mirroring
      `test_vision_models.py`.
- [X] T024 Full suite + lint green; amend research.md decision #5 to record
      that this reverses its original "no shared abstraction" call now that
      swappability was explicitly requested.

**Result**: switching any of the four call sites to a different provider in
the future (back to Claude, or to a third provider implementing the
relevant Protocol) is now a one-line model-id change for all four, not a
file-by-file rewrite — vision via `settings.live_vision_model_id` /
`MODEL_REGISTRY`, the other three via `text_models.MODEL_REGISTRY`.

---

## Implementation Strategy

**MVP first**: T001-T008 (Setup → Foundational → US1) gets the
highest-volume, highest-priority path (photo analysis) onto Gemini Flash
with the accuracy gate enforced, while leaving text/EOD/timezone on Claude
until their own tasks land — each story ships independently rather than as
one big-bang cutover.
