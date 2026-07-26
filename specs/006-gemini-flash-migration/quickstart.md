# Quickstart: Gemini Flash Model Migration

Validation scenarios for this feature once implemented. Assumes a local dev
environment with `GEMINI_API_KEY` set (new) and `ANTHROPIC_API_KEY` still set
(kept — required by the vision-comparison feature's Claude registry entries,
research.md #4).

## Prerequisites

```bash
export GEMINI_API_KEY=...           # new
export ANTHROPIC_API_KEY=...        # still required (comparison entries)
.venv/bin/python -m pytest tests/ -q   # full suite green before manual testing
```

## Scenario 1 — Photo calorie estimate via Gemini Flash (User Story 1, SC-001/SC-002)

1. Send a labeled fixture food photo through `app.services.vision.analyze_photo`
   (or via the WhatsApp webhook in a dev environment).
2. **Expect**: a schema-valid result (`foods`, `total_calories`, `confidence`,
   `clarifying_question`) with a calorie range shown to the user, not a
   single exact number.
3. Confirm (via logs or a debugger) that the call went through
   `GeminiVisionClient`, not `ClaudeVisionClient`.
4. Run the prompt-tester agent against the labeled fixture set; confirm MAE
   regression is ≤5% vs. the pre-migration Claude baseline (Constitution I).

## Scenario 2 — Text-based food logging via Gemini Flash (User Story 2)

1. Send a text food description, e.g. `2 eggs and toast`, through
   `app.services.text_analysis.analyze_text`.
2. **Expect**: the same schema-valid, ranged output shape as before, now
   produced by Gemini Flash.

## Scenario 3 — EOD feedback via Gemini Flash (User Story 3)

1. Trigger `app.services.eod_report.build_report` for a fixture user with a
   non-zero daily total.
2. **Expect**: an encouraging, safety-compliant `feedback_text` under
   `FEEDBACK_MAX_CHARS`, generated via Gemini Flash. Confirm the resulting
   push message is answerable (opens with content a user can reply to), per
   the coach-persona/push-rule requirements.
3. Run the coach-simulator agent to confirm no regression in tone or
   push-rule compliance.

## Scenario 4 — Timezone extraction via Gemini Flash (User Story 3)

1. Call `app.services.timezone.extract_timezone_from_text("just landed in Tokyo!")`.
2. **Expect**: `"Asia/Tokyo"` returned, generated via Gemini Flash.
3. Call it again with a message containing no place reference.
4. **Expect**: `None` returned (no guess persisted).

## Scenario 5 — Schema-invalid Gemini response is rejected (FR-005, Edge Cases)

1. Using a test double, make the Gemini client return a response missing a
   required schema field (e.g. no `confidence`).
2. **Expect**: `ValueError` raised by the existing `_validate_schema` /
   `_validate_feedback` function, exactly as a malformed Claude response
   would have been rejected before this migration — nothing reaches the
   database.

## Scenario 6 — Vision-model comparison still works with Claude candidates (Edge Cases)

1. Run the existing comparison script/flow
   (`tests/integration/test_vision_comparison_flow.py` or
   `scripts/compare_vision_models.py`) selecting `claude-sonnet-5` and the
   new Gemini registry entry as the two candidates.
2. **Expect**: both candidates run and record results independently — the
   comparison feature is unaffected by the live path's default switching to
   Gemini (FR-008).

## Scenario 7 — No Anthropic calls on the four migrated live call sites (FR-009)

1. With `ANTHROPIC_API_KEY` unset (or pointed at an invalid value) but
   `GEMINI_API_KEY` valid, exercise Scenarios 1–4 above.
2. **Expect**: all four succeed — confirming none of the four live call
   sites depends on a working Anthropic credential anymore. (The
   vision-comparison feature, Scenario 6, is expected to still need a valid
   `ANTHROPIC_API_KEY` for its Claude candidates — that's out of scope for
   this check.)
