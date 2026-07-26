# Phase 0 Research: Gemini Flash Model Migration

No `NEEDS CLARIFICATION` markers remained in the spec, so research here
resolves *design* unknowns needed to fill in the plan.

## 1. Which Google SDK, and what package name?

**Decision**: `google-genai` (import `from google import genai`), the current
unified Google Gen AI SDK, used via its async surface
(`genai.Client(...).aio.models.generate_content(...)`).

**Rationale**: It is Google's actively maintained SDK for the Gemini API
(covers both the Gemini Developer API and Vertex AI behind one client), has
first-class multimodal (image + text) support, and an async client matching
this codebase's `async`/`await` style (mirrors `anthropic.AsyncAnthropic`).
The older `google-generativeai` package is legacy and was intentionally not
chosen for new integration work.

**Alternatives considered**:
- *`google-generativeai` (legacy SDK)*: rejected — superseded by
  `google-genai`; starting a new integration on the legacy package would mean
  migrating again shortly after.
- *Raw HTTP calls via `httpx` (already a dependency)*: rejected — the SDK
  gives typed request/response objects and multimodal content helpers for
  free; hand-rolling that duplicates what a maintained SDK already does
  correctly, with no offsetting benefit here.

## 2. Which exact Gemini Flash model identifier?

**Decision**: `gemini-flash-latest` — Google's rolling alias that always
resolves to the current stable Flash-tier model — set as the default via
`app/config.py`, fully overridable per-environment through an env var with no
code change.

**Rationale**: This plan is written without live access to confirm which
dated Flash snapshot (e.g. a specific `gemini-2.x-flash` build) is current as
of the deploy date. Pinning a guessed dated model id risks shipping a
reference to a model that has since been retired or renamed. The rolling
alias avoids that failure mode entirely and matches the spec's own framing
("the exact model identifier is a technical detail resolved during planning,
not fixed in this spec"). Because the id is a plain config value (same
pattern as `live_vision_model_id` today), swapping to a specific dated
snapshot later — e.g. to pin behavior for reproducibility — is a one-line
config change, not a code change.

**Alternatives considered**:
- *Hardcode a specific dated snapshot id*: rejected — higher risk of
  referencing a model id that doesn't exist or has been deprecated by the
  time this code runs, for no accuracy benefit over the rolling alias.

## 3. One Gemini tier for all four call sites, or keep the Sonnet/Haiku-style split?

**Decision**: All four call sites (vision, text parsing, EOD feedback,
timezone extraction) default to the same `gemini-flash-latest` model id.

**Rationale**: The spec asks uniformly for "Gemini Flash" as the answering
model (SC-001), not a mix of tiers. The prior Claude setup used a
cheaper/smaller model (`claude-haiku-4-5`) for the two low-complexity tasks
(EOD feedback, timezone extraction) distinct from the vision-capable model
used for photo analysis and text parsing. Gemini Flash is already the
fast/cheap tier in Google's lineup (there is no cheaper text-capable model
being asked for here), so a single id for all four sites satisfies the spec
without reintroducing a second tier the user didn't ask for. Each call site
keeps its own model-id constant/setting (no cross-file coupling), so a future
split remains a one-line change per site if warranted.

**Alternatives considered**:
- *Keep a separate, even-cheaper "flash-lite" tier for EOD/timezone*:
  rejected — not what was requested, and adds a second model dimension to
  reason about for a migration whose goal is a straightforward provider
  swap.

## 4. How does the existing vision-model registry (spec 003) accommodate a second provider?

**Decision**: Add a `GeminiVisionClient` implementing the existing
`VisionModelClient` Protocol (`app/services/vision_models.py`) alongside the
existing `ClaudeVisionClient` entries, registered in `MODEL_REGISTRY` under a
new key (e.g. `"gemini-flash-latest"`). `settings.live_vision_model_id`
switches to that key. The existing Claude registry entries
(`claude-sonnet-5`, `claude-opus-4-8`) are **not removed** — they remain
valid comparison candidates for the vision-model-comparison feature (spec
003), which is a distinct, internal/manual research capability from the
live, user-facing path.

**Rationale**: Directly satisfies FR-008 ("preserved and extended... not
replaced") and the spec's edge case about the comparison capability
remaining usable. The Protocol was explicitly designed in spec 003 to make
the live model swappable without new abstractions — this migration is the
first real use of that extension point for a second provider, validating the
design. Because comparison entries stay in the registry, the `anthropic` SDK
dependency stays in `pyproject.toml` (still required for
`ClaudeVisionClient`) even though the live path no longer calls it.

**Alternatives considered**:
- *Replace `MODEL_REGISTRY` entirely, dropping Claude entries*: rejected —
  explicitly against FR-008 and removes a working, spec-003 capability
  (comparing candidate models) that has nothing to do with this migration's
  goal.

## 5. text_analysis.py / eod_report.py / timezone.py have no registry — how do they migrate?

**Decision**: Direct swap. Each of the three files' `anthropic.AsyncAnthropic`
singleton-client boilerplate is replaced with a call into a new shared
helper, `app/services/gemini_client.py::get_client()`, returning a
`genai.Client` singleton (same double-checked-lock pattern each file already
used individually). Each file's own prompt-loading, JSON-extraction, and
schema-validation logic is untouched — only the client construction and the
`messages.create(...)` call shape change to the Gemini equivalent
(`client.aio.models.generate_content(model=..., contents=..., config=
types.GenerateContentConfig(system_instruction=..., max_output_tokens=...))`).

**Rationale**: These three files never had a registry/Protocol (spec 003
scoped that abstraction to vision only) and have no comparison use case —
FR-009 requires them fully off Claude, with no equivalent of "keep the old
provider as an option" applying here. The client-singleton boilerplate was
already duplicated identically across all three files before this migration;
consolidating it into one shared `get_client()` while already touching all
three call sites removes that duplication rather than adding a new
abstraction layer, consistent with the project's anti-over-engineering rule.
Domain-specific pieces (prompt files, `_extract_json_block`,
`_validate_schema`/`_validate_feedback`) stay local per file, since they
differ per call site and coupling them would cost more than it saves.

**Alternatives considered**:
- *Give vision_models.py's `ClaudeVisionClient`-style per-instance client to
  a new `GeminiTextClient` class per call site, no shared helper*: rejected —
  reproduces the exact duplication already being cleaned up, for no benefit
  (these three call sites don't need Protocol-style swappability; nothing
  compares against them).

**Superseded**: after this migration shipped, the user explicitly asked for
future-proof swappability on these three call sites too (not just vision) —
see `app/services/text_models.py`, added as a follow-up. A `TextModelClient`
Protocol (`generate(system_instruction, user_content, max_tokens) -> str`)
plus a `MODEL_REGISTRY` (`ClaudeTextClient` / `GeminiTextClient` entries)
now sits between `gemini_client.get_client()` and all three call sites,
mirroring `vision_models.py`'s pattern one level down (text-only, no image
handling). Each call site still owns its own prompt/JSON-or-plain-text
extraction/validation — only "which model answers" is now a one-line change
(the `_FEEDBACK_MODEL` / `_EXTRACTION_MODEL` constant, or
`settings.live_vision_model_id` for `text_analysis.py`) rather than an edit
to the call-site file itself. This reverses the rejection above: it wasn't
wrong when this file was written (there was no real second-provider need
yet), but "swap providers again easily" turned out to be a real requirement
once asked directly, not a hypothetical one.

## 6. How does multimodal (image) content shape change?

**Decision**: `ClaudeVisionClient`'s base64-encoded `image` content block
becomes a `google.genai.types.Part.from_bytes(data=image_bytes,
mime_type=media_type)` content part passed alongside a text part in
`contents=[...]`. No base64 encoding step is needed — `google-genai` accepts
raw bytes directly. The system prompt continues to load unchanged from
`calorie_vision.md` via `_load_prompt()`, passed as
`config.system_instruction` (Gemini's equivalent of Anthropic's `system=`
parameter) rather than inlined into `contents`.

**Rationale**: This is the SDK's documented multimodal content shape;
dropping the base64 encode/decode round trip removes work the Anthropic
integration needed but Gemini doesn't.

## 7. How does response-text extraction change?

**Decision**: Anthropic's `response.content` (a list of typed blocks, text
joined via `"".join(block.text for block in response.content if block.type
== "text")`) becomes Gemini's `response.text` (a single string property the
SDK already assembles). Each file's existing `_extract_json_block` /
`_validate_schema` functions operate on that string exactly as before — only
the one line producing the string changes.

**Rationale**: Matches the SDK's actual response shape; no reason to
re-implement Anthropic's block-joining pattern against a provider that
doesn't need it.

## 8. Error handling equivalence

**Decision**: No change to error-handling *behavior* is required. A grep of
the codebase confirms no call site catches an Anthropic-specific exception
type (`anthropic.APIError` etc.) — errors from `messages.create(...)` and
schema-validation `ValueError`s already propagate as generic exceptions to
each caller (`vision.py`, `text_meal_logging.py`, `eod_trigger.py`,
onboarding flow), which already handle "the model call failed" generically
(user-facing fallback reply / skip-and-log-for-retry, per file). Gemini SDK
errors (`google.genai.errors.APIError` and friends) propagate the same way,
satisfying FR-010 (equivalent error behavior) with no caller-side changes.

**Rationale**: Least-change path that already satisfies the requirement —
introducing new Gemini-specific exception handling where none of the
Claude-specific equivalent existed would be scope creep, not a requirement
of this migration.

## 9. Test doubles

**Decision**: The existing unit tests that monkeypatch each module's
`_get_client` (`tests/unit/test_eod_report.py`,
`tests/unit/test_timezone.py`) and the `VisionModelClient` fakes
(`tests/unit/test_vision_comparison.py`,
`tests/integration/test_vision_comparison_flow.py`) are updated to match the
new response shape (a fake object exposing `.text` instead of `.content`
blocks) and the new shared `gemini_client.get_client` patch target. Test
*structure* and *intent* (what each test asserts) do not change — only the
fake response/client shape they construct.

**Rationale**: These tests validate this codebase's own schema-validation
and JSON-extraction logic, not the SDK — they were never testing Anthropic
behavior, so updating the fake's shape to match the new SDK's response
object is a mechanical follow-through of decisions #6/#7, not a test-design
change.
