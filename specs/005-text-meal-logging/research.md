# Phase 0 Research: Text-Based Meal Logging

No open `NEEDS CLARIFICATION` markers from the Technical Context — this feature extends an established stack with well-understood patterns already proven by 001 (photo logging), 002 (daily totals), and 004 (clarification/fallback chain). The items below are design decisions worth recording explicitly, since they weren't dictated by the spec and needed a concrete choice.

## 1. Detection: one LLM call, not two

**Decision**: A single Claude call, given the user's free-form text, either returns a food estimate (same schema as the vision pipeline) or signals "not a food-logging message" — no separate classification step beforehand.

**Rationale**: A two-call design (classify, then estimate) doubles latency and cost for every text message, and duplicates accuracy risk across two prompts instead of one. `calorie_vision.md` already proves the one-call pattern works: it returns either a populated `foods` estimate or an empty `foods` array with `confidence: 0.0` when the photo isn't food at all (rule 7). The text prompt reuses the identical pattern: empty `foods` + `confidence: 0.0` means "not a food-logging message," letting the caller fall through to the next dispatch layer with no extra call.

**Alternatives considered**: A cheap keyword/regex pre-filter (e.g. requiring a number + a food-like word) before the LLM call, to skip the API call entirely for obviously-unrelated text. Rejected for now — it would need a maintained food-word list and would risk false negatives (missing genuine food descriptions that don't match the list) for a marginal cost saving; the vision pipeline doesn't pre-filter "is this a food photo" before calling the model either, for the same reason. Revisit only if API cost/latency on non-food text becomes a measured problem.

## 2. Dispatch precedence: defer via internal safety check, don't restructure chat_fallback.py

**Decision**: `text_meal_logging`'s entrypoint checks `safety.check_safety_signal(text)` itself, first, and returns `None` (defer to the next layer) on any hit — it never attempts food detection on a safety-flagged message. It's wired into `webhook.py`'s existing chain after the pending-clarification and daily-target layers, before `chat_fallback.handle_free_form_text` (which still does its own, unchanged, safety-first check as a defense-in-depth backstop for anything that reaches it).

**Rationale**: `chat_fallback.py`'s contract (`contracts/chat-fallback-dispatch.md` from spec 004) is: safety always checked first, internally, and the function never returns `None`. Restructuring that to pull safety out as a shared pre-layer would touch already-shipped, already-tested, safety-critical code for this feature's benefit — higher risk than having the new layer perform its own (cheap, keyword-based, non-LLM) safety check before deciding whether to attempt logging. `safety.check_safety_signal` is a pure pattern-match, not an API call, so checking it twice (once here, once inside `chat_fallback` if control reaches that far) costs nothing meaningful.

**Alternatives considered**: Moving the safety check up into `webhook.py` itself, ahead of every dispatch layer. Rejected — it's a bigger blast-radius change (touches the entrypoint every text message goes through) for the same outcome this feature already achieves locally.

## 3. Schema: nullable `photo_media_id` + parallel `text_entries`, not a new meal-source table

**Decision**: Migration makes `meals.photo_media_id` nullable and adds `meals.text_entries text[] NOT NULL DEFAULT '{}'`, storing each text-originated contribution's raw body (parallel to how `photo_media_ids` stores each photo contribution's media ID). A meal's total contribution count for reply-shaping purposes (`meal_logging.py`'s single-item-collapse vs. item-and-running-total decision) becomes `len(photo_media_ids) + len(text_entries)` instead of `len(photo_media_ids)` alone.

**Rationale**: Minimal, additive schema change (Constitution IV: DB changes only via migrations) that keeps `MealRecord` a single flat shape rather than introducing a join to a new "contributions" table, which today's scale (single-tenant coaching bot, a handful of contributions per meal) doesn't need. Storing the raw text body (not just a count) preserves the same traceability photo IDs already give — useful for debugging a bad estimate later, and cheap.

**Alternatives considered**: A generic `meals.source text CHECK (source IN ('photo','text','mixed'))` column instead of inferring origin from which array is populated. Rejected as redundant — origin is already fully derivable from `photo_media_ids`/`text_entries` being empty or not, and an explicit column that has to be kept in sync with two arrays is one more way for state to drift out of sync with itself.
