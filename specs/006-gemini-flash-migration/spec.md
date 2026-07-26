# Feature Specification: Gemini Flash Model Migration

**Feature Branch**: `claude/modal-gemini-flash-d5lmwj`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "Switch the bot's LLM provider from Claude (Anthropic) to Gemini Flash (Google) for all model calls: food-photo vision analysis (calorie estimation), text-based food description parsing, end-of-day coach feedback generation, and timezone extraction from user messages. The bot should use Gemini Flash to generate all of its responses instead of Claude, while preserving existing behavior: prompts remain versioned files in app/prompts/, LLM outputs remain schema-validated before DB insert, calorie results remain shown as ranges never exact numbers, and the existing pluggable vision-model registry pattern is preserved/extended rather than removed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Photo calorie estimate still arrives correctly (Priority: P1)

A user sends a photo of their meal to the WhatsApp bot. The bot analyzes the photo and replies with an estimated calorie range and macros, exactly as it does today, but the analysis is now produced by Gemini Flash instead of Claude.

**Why this priority**: Photo-based calorie tracking is the core, highest-volume feature of the product. Any regression here directly breaks the primary value proposition and is immediately visible to every active user.

**Independent Test**: Send a labeled fixture food photo through the pipeline and confirm a schema-valid response is returned with a calorie range (not a single number) whose midpoint is within the existing accuracy tolerance (MAE regression ≤5%, per constitution).

**Acceptance Scenarios**:

1. **Given** a user sends a clear food photo, **When** the bot processes it, **Then** the user receives a calorie-range estimate and macro breakdown generated via Gemini Flash, formatted identically to the current Claude-generated response.
2. **Given** the vision call returns malformed or non-schema-conforming output, **When** the response is validated, **Then** the system rejects it and falls back to the existing error-handling behavior (no malformed data reaches the database or the user).

---

### User Story 2 - Text-based food logging still works (Priority: P1)

A user types a text description of a meal (no photo) and the bot parses it into structured food/calorie data the same way it does today, now via Gemini Flash.

**Why this priority**: Text logging is an existing, actively used alternate path to the same core calorie-tracking value; it must not regress when the underlying model changes.

**Independent Test**: Send a labeled text fixture ("2 eggs and toast") through the text-analysis pipeline and confirm the parsed structured output matches the expected schema and calorie range.

**Acceptance Scenarios**:

1. **Given** a user types a food description, **When** the bot parses it, **Then** it returns a schema-valid, ranged calorie estimate generated via Gemini Flash.

---

### User Story 3 - Daily coach feedback and timezone detection keep working (Priority: P2)

The bot's end-of-day proactive feedback message and its one-time timezone-detection step (used to schedule proactive messages correctly) continue to function, now generated via Gemini Flash.

**Why this priority**: These are supporting, lower-frequency features (once/day and once-per-user respectively). Important to migrate for consistency and to retire the Claude dependency, but a short delay in cutover has lower user-facing impact than P1 stories.

**Independent Test**: Trigger the EOD feedback job for a fixture user and confirm a coach-toned message is generated; trigger timezone extraction against a fixture message containing a location/time reference and confirm the correct IANA timezone string is extracted.

**Acceptance Scenarios**:

1. **Given** a user's day is closing out, **When** the EOD job runs, **Then** the bot sends an encouraging, safety-compliant feedback message generated via Gemini Flash, and that message is answerable (reopens the 24h WhatsApp window) per existing push rules.
2. **Given** a new user's first message contains a timezone cue, **When** timezone extraction runs, **Then** the correct timezone is stored, generated via Gemini Flash.

---

### Edge Cases

- What happens when the Gemini API is unreachable or rate-limited? The system must fail the same way the current Claude outage path fails today (surface a user-friendly error / retry, never a raw stack trace, never a silently corrupted DB row).
- How does the system handle a Gemini response that doesn't match the expected output schema (hallucinated fields, wrong JSON shape, refusal text)? It must be rejected by schema validation before reaching the database, identically to how a malformed Claude response is handled today.
- What happens to the existing multi-vision-model comparison capability (used to A/B different vision models) once Gemini Flash becomes an option? It must remain usable — Gemini Flash is added as a registered option, not a hard-coded replacement that removes the ability to select other models.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST generate food-photo calorie/macro analysis using Gemini Flash instead of Claude, while producing output in the same schema-validated, ranged (never exact-number) format currently produced.
- **FR-002**: The system MUST generate text-based food-description parsing using Gemini Flash instead of Claude, in the same schema-validated, ranged format.
- **FR-003**: The system MUST generate end-of-day coach feedback messages using Gemini Flash instead of Claude, preserving the existing coach persona, tone, and safety-escalation rules.
- **FR-004**: The system MUST perform timezone extraction from user messages using Gemini Flash instead of Claude.
- **FR-005**: The system MUST continue to validate every LLM output against its existing versioned JSON schema before any database write; a schema-invalid Gemini response MUST be rejected, never persisted.
- **FR-006**: The system MUST continue to present calorie results to users as ranges, never as a single exact number.
- **FR-007**: Prompts MUST remain versioned files under `app/prompts/`; no prompt text may be inlined in application code.
- **FR-008**: The existing pluggable vision-model registry (used for comparing multiple vision models) MUST be preserved and extended to include Gemini Flash as a selectable option, not replaced by a single hard-coded provider.
- **FR-009**: The system MUST NOT send any Claude/Anthropic API calls once the migration is complete for the four call sites in scope (vision, text parsing, EOD feedback, timezone extraction) — Gemini Flash becomes the sole active provider for these paths.
- **FR-010**: The system MUST handle Gemini API errors (timeouts, rate limits, outages) with user-facing behavior equivalent to the current Claude error handling — no raw errors surfaced to the end user, no partial/corrupt data persisted.
- **FR-011**: All safety and medical-advice-avoidance rules currently enforced on Claude-generated coach messages MUST continue to apply to Gemini-generated messages.
- **FR-012**: Every proactive (push) message generated via Gemini MUST remain answerable by the user, preserving the WhatsApp 24-hour window rule.

### Key Entities

- **Model call site**: One of the four existing points where the bot invokes an LLM (vision analysis, text food parsing, EOD feedback, timezone extraction) — each currently bound to Claude and, after this feature, bound to Gemini Flash.
- **Vision model registry entry**: A named, selectable vision-model configuration (e.g. existing Claude entries plus a new Gemini Flash entry) used by the vision-model comparison capability.
- **Prompt file**: A versioned file under `app/prompts/` supplying the instructions for a given call site, independent of which model provider executes it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of food-photo and text-based calorie estimates delivered to users are produced by Gemini Flash, with zero Claude/Anthropic calls remaining on those paths.
- **SC-002**: Calorie-estimate accuracy on the existing labeled fixture set does not regress by more than 5% mean absolute error versus the pre-migration Claude baseline (per constitution accuracy gate).
- **SC-003**: 100% of LLM responses across all four migrated call sites that fail schema validation are rejected before reaching the database, with no increase in the pre-migration validation-failure rate.
- **SC-004**: End-of-day feedback and timezone-extraction jobs complete successfully for fixture users with no increase in error rate compared to the pre-migration baseline.
- **SC-005**: No user-visible change in response format: calorie results still shown as ranges, coach tone and safety escalation behave identically to before the migration, as verified by the coach-simulator agent.

## Assumptions

- "Gemini Flash" refers to Google's current fast-tier Gemini model made available via the Gemini API; the exact model identifier is a technical detail resolved during planning, not fixed in this spec.
- A Google Gemini API key will be provisioned and supplied via environment variable, consistent with how the existing Anthropic API key is supplied (constitution: secrets only via environment variables).
- This migration is scoped to the four existing call sites identified in the codebase (vision analysis, text food parsing, EOD feedback, timezone extraction). No new user-facing capability is introduced.
- The existing vision-model comparison/registry mechanism (introduced in a prior feature) is the correct extension point for adding Gemini Flash as a vision option, rather than building a parallel mechanism.
- Chat fallback replies (the fixed, non-generative WhatsApp fallback messages) are out of scope since they do not call any LLM today.
- Workout-plan and meal-menu generation are out of scope for this migration since no such code exists in the current codebase.
