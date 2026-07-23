# Phase 0 Research: Vision Model Abstraction & Comparison

No `NEEDS CLARIFICATION` markers remained in the spec (the requirements
checklist confirms this), so research here resolves *design* unknowns needed
to fill in the plan, not spec ambiguities.

## 1. How should the live model be designated and switched?

**Decision**: A single Settings field, `live_vision_model_id: str`, read from
the environment (same pattern as every other config value in `app/config.py`).
`app/services/vision.py` resolves this id against the candidate registry on
each call (no in-process caching across the switch — the setting is read from
`settings` each time, so a redeploy with the new env value takes effect
immediately).

**Rationale**: The codebase has no admin UI or CLI for runtime config, and
every existing per-environment value (`whatsapp_access_token`,
`database_url`, etc.) is an env var. Introducing a DB-backed "live model"
table would add a new kind of mutable runtime config the project doesn't
otherwise have, for a switch that happens rarely (spec: "deliberate,
explicit action... separate from running a comparison"). A env var change +
redeploy already satisfies "deliberate and explicit," and keeps the pattern
consistent (Constitution V — no new special-case config mechanism).

**Alternatives considered**:
- *DB-backed singleton config row, mutable at runtime*: rejected — adds a new
  runtime-mutable-config concept to a codebase that has none, for a switch
  that is inherently rare and already deliberate as an env var change.
- *Feature flag service*: rejected — no such service exists in the stack;
  would be new infrastructure for a single boolean-ish decision.

## 2. How is model-attribution (FR-008) persisted for live traffic?

**Decision**: Add a nullable `model_id text REFERENCES model_candidates(id)`
column to `meals`, populated at write time in `create_meal`/`append_to_meal`
with whatever `settings.live_vision_model_id` was at the moment of that
photo's analysis.

**Rationale**: This is the only place live estimates are persisted today
(`app/db/queries.py` / `0001_init.sql`). Storing the id directly on the row
(rather than deriving it later) is the only way to answer "which model
produced this now-historical estimate" if the live model is switched later —
FK to `model_candidates` keeps it a real, join-able reference rather than a
free-text string that could drift from the registry.

**Alternatives considered**:
- *Separate `meal_model_attribution` table*: rejected as unnecessary
  indirection — it's a 1:1, append-only fact about the meal row itself.

## 3. Where does comparison-run state live, and how are partial/interrupted runs handled?

**Decision**: Persist per-photo-per-model results (`model_results`) as they
are produced, not just a final summary. `comparison_runs.status` moves
`running -> completed` only after every (candidate × photo) pair has been
attempted; if the process is killed mid-run, already-written `model_results`
rows remain queryable and the run's `status` stays `running` (never silently
marked `completed`).

**Rationale**: Directly satisfies the spec's edge case ("if a comparison run
is interrupted partway through, results already produced remain available;
the run is not silently treated as complete") and FR-006 keeps this fully
decoupled from anything the live path reads.

**Alternatives considered**:
- *Buffer all results in memory, write once at the end*: rejected — loses
  everything on interruption, which the spec explicitly calls out as
  unacceptable.

## 4. How is accuracy (FR-004/FR-005) computed, and how does it relate to the existing MAE gate?

**Decision**: Extend `tests/fixtures/food_photos/manifest.json` entries with
optional `expected_protein_g`, `expected_carbs_g`, `expected_fat_g` fields
(additive — `expected_calories`-only entries stay valid for the existing
`test_calorie_accuracy.py` regression gate). `app/services/vision_comparison.py`
computes, per model per nutrient, mean-absolute-error percentage across all
fixture photos that have both a model result and a ground-truth value for
that nutrient, writing one `accuracy_scores` row per (run, model, nutrient).
Photos with no ground truth for a nutrient, or with a failed/invalid model
response, are excluded from that nutrient's score (FR-005 / Edge Cases) but
the underlying `model_results` row still records the failure for review.

**Rationale**: Reuses the exact MAE-percent method the constitution already
mandates for the single-model regression gate (Principle I), so "is this
model good enough" and "which model is better" are measured the same way —
no second accuracy methodology to maintain.

**Alternatives considered**:
- *Absolute deviation in raw units (kcal/g) instead of percent*: rejected —
  inconsistent with the existing gate's percent-based threshold, and percent
  is what makes calories and grams-of-macro comparable/aggregable.

## 5. How are "candidate models" represented and invoked?

**Decision**: A `VisionModelClient` Protocol (`async def analyze(image_bytes,
media_type, clarification) -> dict`, returning the existing calorie-estimation
schema) in `app/services/vision_models.py`, with a `MODEL_REGISTRY: dict[str,
VisionModelClient]` mapping a stable `model_id` string to a concrete client
instance. The current Claude Sonnet 5 call in `vision.py` becomes one
registry entry; additional entries (other Claude model ids, or other
providers later) implement the same Protocol. `model_candidates` is the DB
mirror of the registry's keys (id + display name), giving `meals.model_id`
and `model_results.model_id` something real to reference via FK.

**Rationale**: Matches FR-001 ("two or more different candidate models
independently") and keeps the live path (`vision.analyze_photo`) and the
comparison path (`vision_comparison.py`) calling the exact same interface, so
a model behaves identically whether it's serving live traffic or being
compared — no behavioral drift between the two call sites.

**Alternatives considered**:
- *Ad-hoc if/else branching on a model-name string inside `vision.py`*:
  rejected — doesn't scale past two models and mixes live-serving and
  research-comparison concerns in one function.

## 6. How does comparison output satisfy FR-002's "range" requirement given point-valued storage?

**Decision**: `model_results` stores point values (decision #5's rationale:
"same result structure" = the calorie-estimation schema, which is itself
point-valued). The comparison CLI's printed summary (contracts/
compare_vision_models_cli.md) applies the same ±20% method
`app/services/meal_logging.py::format_range_reply` uses for calories to
**both** calories and each macro for every model/photo shown, computed at
print time from the stored point values — never persisted as a range.

**Rationale**: FR-002 explicitly asks for "an estimated calorie range and
macro ranges... using the same result structure already used for live bot
estimates." Read literally this is two things at once: the *storage*
structure (point-valued, matching live estimates — decision #5) and the
*range* a reviewer sees (matching how live users perceive uncertainty,
Constitution I). Today's live reply only ranges calories, not macros
(`format_range_reply` prints macros as bare point sums) — but that's a
brevity choice for a WhatsApp reply, not a signal that macro uncertainty
doesn't matter; a research comparison explicitly built to judge macro
accuracy needs macro uncertainty bounds too. Applying the same ±20% method
to macros in the comparison summary satisfies FR-002 without changing the
live reply format or the stored schema.

**Alternatives considered**:
- *Store ranges in `model_results` directly*: rejected — duplicates
  information that's fully derivable from the point value, and diverges
  from the "same result structure as live estimates" the spec calls for.
- *Only range calories, leave macros as bare numbers (mirror the live reply
  exactly)*: rejected — doesn't satisfy FR-002's explicit "macro ranges"
  language, and defeats User Story 2's need to see macro-specific
  disagreement between models.

## 7. Where does a team member trigger and review a comparison run?

**Decision**: A CLI script, `scripts/compare_vision_models.py`, run manually
(`python -m scripts.compare_vision_models --models sonnet-5,opus-4-8`). It
writes to the DB tables above and prints a grouped, per-photo /
per-model summary table to stdout at the end (or partial progress if
interrupted, per decision #3).

**Rationale**: There is no admin UI or dashboard anywhere in this codebase
(FastAPI app only exposes the WhatsApp webhook + health check); a CLI script
matches the project's existing "team member runs a thing locally" pattern
(e.g., `prompt-tester` agent invoking pytest directly) and requires no new
web surface for an internal, occasional, manual research action.

**Alternatives considered**:
- *New authenticated admin API endpoint*: rejected — real surface area
  (auth, input validation, hosting) for a feature the spec frames as
  internal/manual with no urgency for a UI.
