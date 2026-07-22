# Implementation Plan: Vision Model Abstraction & Comparison

**Branch**: `003-vision-model-comparison` | **Date**: 2026-07-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-vision-model-comparison/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Abstract `app/services/vision.py`'s single hard-coded Claude call behind a
`VisionModelClient` protocol and a small registry of named candidate models.
A new offline comparison path runs every registered candidate against the
existing labeled fixture set (`tests/fixtures/food_photos/`), persists each
model's per-photo result and an aggregate accuracy score, while live traffic
keeps flowing through exactly one designated model, unaffected. Switching the
live model is a deliberate config change (env var), and every meal row records
which model produced it.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing app/)

**Primary Dependencies**: FastAPI, `anthropic` SDK (vision + chat), asyncpg, pydantic-settings, pytest/pytest-asyncio

**Storage**: PostgreSQL (Supabase), migrations in `app/db/migrations/`

**Testing**: pytest — unit tests for the registry/scoring logic, integration test for the end-to-end comparison flow, and the existing `tests/test_calorie_accuracy.py` pattern extended to per-model scoring

**Target Platform**: Linux server (Railway/Render), same deployment as the rest of the app

**Project Type**: Single backend service — extends the existing `app/` layout (Option 1), no new project

**Performance Goals**: N/A — this is an offline, manually-triggered research tool, not a request-serving path; no latency budget beyond "doesn't block or slow live webhook traffic"

**Constraints**: Must not alter live request behavior, latency, or replies while a comparison run is in progress or after it completes without a deliberate switch (FR-006, FR-009); no new WhatsApp-facing behavior (spec Assumption); ranges-not-exact-numbers rule (Constitution I) applies only to end-user-facing replies, not internal comparison output (spec Assumption)

**Scale/Scope**: Small internal fixture set (tens of labeled photos) × a handful of candidate models, triggered manually by a team member; not designed for concurrent or high-volume use

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Accuracy honesty | Comparison scoring reuses and extends the existing labeled-fixture regression mechanism (`tests/test_calorie_accuracy.py` / `prompt-tester` agent) rather than inventing a parallel one; accuracy scores are per-model MAE against the same ground truth | PASS |
| II. Push, not pull | Feature is entirely pull/manual (team-triggered research run); no proactive messaging added | PASS (N/A) |
| III. Safety first | FR-010: comparison output is internal numbers/tables only, no advice text generated | PASS |
| IV. Schema discipline | Every candidate model's output is validated against the existing versioned calorie-estimation schema (`app/prompts/calorie_vision.md` / `calorie-estimation` skill) before being persisted; new tables added only via migration files | PASS |
| V. Platform independence | The new `VisionModelClient` abstraction lives in `app/services/`, stays out of `app/whatsapp/`; live traffic and comparison runs share the same abstraction so WhatsApp code never changes | PASS |
| Security requirements | No new secrets beyond existing `ANTHROPIC_API_KEY`; no PII in new tables (fixture filenames + numeric results only) | PASS |

No violations — Complexity Tracking is not needed.

*Post-design re-check (after Phase 1)*: data-model.md and contracts/ add
tables and an internal Protocol only, no new external surface, no change to
`app/whatsapp/`, and every persisted `model_results` row is schema-validated
before insert (same validator as the live path). Gate table above still
holds — no new violations introduced by the design.

## Project Structure

### Documentation (this feature)

```text
specs/003-vision-model-comparison/
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
├── config.py                          # + live_vision_model_id setting
├── services/
│   ├── vision.py                      # thin wrapper: resolves the live client, unchanged public API
│   ├── vision_models.py                # NEW: VisionModelClient protocol + candidate registry
│   └── vision_comparison.py            # NEW: comparison-run orchestration + accuracy scoring
├── db/
│   ├── migrations/
│   │   └── 0003_vision_model_comparison.sql   # NEW: model_candidates, comparison_runs,
│   │                                            #      model_results, accuracy_scores + meals.model_id
│   ├── queries.py                      # + model_id passed through create_meal/append_to_meal
│   └── vision_comparison_queries.py    # NEW: repositories for the four new tables
scripts/
└── compare_vision_models.py            # NEW: CLI entrypoint a team member runs manually

tests/
├── fixtures/food_photos/
│   ├── manifest.json                   # extended with expected_protein_g/carbs_g/fat_g (additive)
│   └── README.md                       # updated to document the new fields
├── unit/
│   └── test_vision_comparison.py       # NEW: registry, scoring math, failure handling
└── integration/
    └── test_vision_comparison_flow.py  # NEW: end-to-end comparison run against fakes
```

**Structure Decision**: Single backend project (existing `app/` layout, Option 1
— no frontend/mobile split exists or is needed). The feature adds two new
service modules, one migration, one query module, one CLI script, and tests —
no new top-level project or package.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
