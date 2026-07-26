# Implementation Plan: Gemini Flash Model Migration

**Branch**: `claude/modal-gemini-flash-d5lmwj` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-gemini-flash-migration/spec.md`

## Summary

Switch the four existing LLM call sites (food-photo vision analysis,
text-based food parsing, end-of-day coach feedback, timezone extraction) from
Claude (Anthropic) to Gemini Flash (Google), using the `google-genai` SDK.
The vision call site keeps using the existing `VisionModelClient` registry
pattern from spec 003 — a new `GeminiVisionClient` entry is added and made
the live default, while existing Claude registry entries remain for the
vision-model-comparison feature. The other three call sites (no registry;
direct client calls) swap their Anthropic client construction for a new
shared `app/services/gemini_client.py::get_client()` singleton. Prompts stay
unchanged in `app/prompts/`; schema validation, ranged-calorie presentation,
and safety/coach-persona behavior are all preserved as-is — only the
model-calling plumbing changes.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged)

**Primary Dependencies**: FastAPI, pydantic-settings (unchanged); adds
`google-genai` (new); keeps `anthropic` (still required — see research.md #4)

**Storage**: PostgreSQL (Supabase) — unchanged, no schema changes

**Testing**: pytest / pytest-asyncio (unchanged); existing fake-client test
doubles updated to match the Gemini SDK's response shape (research.md #9)

**Target Platform**: Linux server (Railway/Render) — unchanged

**Project Type**: Single backend service (unchanged)

**Performance Goals**: No regression vs. current Claude latency for
user-facing replies (photo analysis, text parsing); EOD/timezone jobs
complete within existing scheduler windows

**Constraints**: MAE regression ≤5% vs. pre-migration Claude baseline on the
existing labeled fixture set (Constitution I, SC-002); no Claude/Anthropic
calls remain on any of the four migrated call sites (FR-009); calorie output
remains range-only, never a single exact number (FR-006)

**Scale/Scope**: 4 call sites across 4 files, 1 new shared client module, 1
new vision-registry entry, 1 new dependency, config/settings updates, test
fixture updates — no new user-facing capability, no schema/migration changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Accuracy honesty** — PASS. Calorie output stays range-only (FR-006);
  the prompt-tester agent runs against the existing labeled fixtures before
  this is considered done, gating on the same ≤5% MAE regression threshold
  the constitution already mandates for any prompt/model change.
- **II. Push, not pull** — PASS. No push-message logic changes; EOD feedback
  remains answerable (FR-012), verified via the coach-simulator agent.
- **III. Safety first** — PASS. No prompt content changes; safety-escalation
  and no-medical-advice rules are enforced by prompt content (unchanged) and
  the coach-persona skill, not by which provider executes the prompt.
- **IV. Schema discipline** — PASS. Every call site keeps its existing
  schema-validation function (`_validate_schema` / `_validate_feedback`);
  Gemini output is rejected identically to malformed Claude output before any
  DB write (FR-005). Prompts remain versioned files in `app/prompts/`
  (FR-007) — none are inlined or modified.
- **V. Platform independence** — PASS. No WhatsApp-specific code touched;
  this is entirely within `app/services/`.

No violations — Complexity Tracking section omitted.

*Re-checked after Phase 1 design below: still PASS, no new gates triggered
by the concrete file-level design (research.md).*

## Project Structure

### Documentation (this feature)

```text
specs/006-gemini-flash-migration/
├── plan.md              # This file
├── research.md           # Phase 0 output
├── quickstart.md          # Phase 1 output — manual verification steps
└── tasks.md              # Phase 2 output (/speckit.tasks — not created here)
```

No `data-model.md`: no new *tables or columns* (Key Entities in spec.md are
all pre-existing concepts). One new migration was still required, discovered
during implementation: `model_candidates` (0003_vision_model_comparison.sql)
is a seed table FK'd from `meals.model_id`/`model_results.model_id`, and it
only had Claude rows — see `0009_gemini_flash_model_candidate.sql`. No
`contracts/`: the
behavioral contracts for these four call sites already exist from prior
features (`contracts/vision_model_client.md`, `contracts/calorie-text-
prompt.md`, `contracts/eod-report.md` under their originating spec
directories) and are unchanged by a provider swap — only the model
implementing them changes.

### Source Code (repository root)

```text
app/
├── config.py                       # + gemini_api_key, live_vision_model_id default → gemini entry
├── services/
│   ├── gemini_client.py            # NEW: shared google-genai Client singleton
│   ├── vision_models.py            # + GeminiVisionClient, + MODEL_REGISTRY entry
│   ├── vision.py                   # unchanged (resolves registry by id, provider-agnostic already)
│   ├── text_analysis.py            # swap _get_client() → gemini_client.get_client(), swap call shape
│   ├── eod_report.py                # swap _get_client() → gemini_client.get_client(), swap call shape
│   └── timezone.py                  # swap _get_client() → gemini_client.get_client(), swap call shape
├── prompts/                         # unchanged — no prompt content edits
pyproject.toml                       # + google-genai dependency
tests/
├── unit/test_eod_report.py          # fake client/response shape updated to match Gemini SDK
├── unit/test_timezone.py             # fake client/response shape updated to match Gemini SDK
├── unit/test_vision_comparison.py    # unaffected (Protocol-level fakes, no shape change)
└── integration/test_vision_comparison_flow.py  # unaffected (same reason)
```

**Structure Decision**: No new top-level directories or services. This is a
same-shape swap within the existing `app/services/` layout: one new small
shared module (`gemini_client.py`) plus in-place edits to the four call-site
files and the vision-model registry, following the file layout every prior
feature in this repo already uses.

## Complexity Tracking

*No constitution violations — section not applicable.*
