# Phase 0 Research: Daily Calorie & Macro Total Tracking

## 1. How the running total is maintained: upsert-on-write vs. live-computed-per-request

**Decision**: Maintain `daily_totals` via an additive upsert every time a meal is created or appended to, bucketed by the meal's *local calendar date at the moment it is logged* (using whichever time zone is on file for the user at that instant). A total request just reads that row.

**Rationale**: `.claude/skills/db-schema/SKILL.md` already documents `daily_totals` as "maintained by trigger/upsert on meals" — this is the established convention, not a new one. More importantly, once time zones are per-user and mutable (User Story 4), a live-computed sum (re-scanning `meals` and re-bucketing by *today's* stored time zone at query time) would silently misattribute old meals whenever a user's time zone changes: a meal logged at 23:00 under time zone A could get pulled into a different day's bucket the moment the user's stored time zone shifts to B, even though nothing about that meal changed. That directly violates FR-014 (no retroactive reattribution). Fixing the bucket at write time, once, sidesteps this entirely — a later time-zone change can only affect the reset boundary for meals logged *after* the change.

**Alternatives considered**: Live `SUM(...)` over `meals` filtered by a day-boundary computed from the user's *current* stored time zone — simpler code, no upsert logic to get right, but breaks FR-014 as above. Rejected.

## 2. Initial time-zone default (before any location share or place mention)

**Decision**: Derive a default from the country region embedded in the user's WhatsApp number (via `phonenumbers`), mapped to one representative IANA zone for that region; fall back to `UTC` if the region can't be determined or mapped.

**Rationale**: The spec's own Edge Cases explicitly allow a reasonable default "out of scope to define... exact source" before onboarding establishes a real value. This codebase has no onboarding conversation flow implemented yet — `users` already has several onboarding-oriented columns (`goal`, `experience`, `height_cm`, etc.) that stay unpopulated for the same reason, so building a dedicated onboarding step just for time zone would be new scope this feature doesn't need. Deriving from the phone number's country costs nothing at signup time and is strictly better than defaulting straight to UTC.

**Alternatives considered**: Ask the user's time zone in a dedicated onboarding question (rejected — no onboarding flow exists to hang this off yet); hardcode `Asia/Jerusalem` since both current real users are in Israel (rejected — works today but isn't a general answer, and the phone-derived default costs barely more).

## 3. Location share → time zone

**Decision**: `timezonefinder` (pure-Python, offline, no network call) maps a shared location's latitude/longitude to an IANA time zone name.

**Rationale**: No new secret or external geocoding API needed; works fully offline; well-maintained pure-Python package.

**Alternatives considered**: A third-party geocoding/timezone HTTP API (e.g. Google Time Zone API) — rejected: adds a new secret, a new network dependency and failure mode, and ongoing cost for something an offline library already solves.

## 4. Text place-mention → time zone

**Decision**: A small, cheap Claude call (Haiku-class model — distinct from the Sonnet-class vision model used for photo analysis) with a versioned prompt (`app/prompts/timezone_extraction.md`) that returns either a single IANA time zone string or nothing. The result is validated against Python's built-in `zoneinfo.available_timezones()` before being persisted; anything that fails validation (or the model returning nothing) leaves the stored time zone unchanged (FR-013).

**Rationale**: Free-form place references ("I landed in Tokyo," "I'm in São Paulo now") aren't realistically catchable with a keyword list the way the total-request phrases are — this is exactly the kind of open-ended extraction task an LLM call is suited for and a hand-maintained place-name table isn't. Using a cheap/fast model keeps the added cost and latency negligible; the existing `anthropic` dependency is reused, no new provider.

**Alternatives considered**: A hardcoded city/country-name → time zone dictionary (rejected — necessarily incomplete, and place names are ambiguous across languages/spellings in a way a small LLM call handles better); running full vision-model-grade extraction (rejected — unnecessarily expensive for a short-text classification task).

## 5. Total-request recognition (User Story 1)

**Decision**: A deterministic phrase/keyword list (Hebrew + English), following the same lightweight-dispatch style already used for the pending-clarification check — not an LLM call.

**Rationale**: Cheap, deterministic, and easy to unit test with no external call in the hot path. `004-chat-responsiveness` (spec only, not yet planned) separately describes a more general "bounded set of recognized supported questions" that a running total would eventually be one instance of — this feature's phrase-list matcher is written so it can be folded into that broader framework later without changing its behavior, but doesn't block on 004 being planned or implemented first.

**Alternatives considered**: Routing every free-form text message through an LLM intent classifier — rejected as unnecessary cost/latency for a single, narrow recognized intent.

## 6. Text-message dispatch composition

**Decision**: For an inbound text message, after the existing pending-clarification check (unchanged — a pending clarifying question about a photo still takes priority over anything in this feature): (a) check the total-request phrase list — if it matches, reply with the current total; (b) independently of (a), run the place-mention extraction on the same message text — if a valid time zone comes back, update `users.time_zone` silently (no dedicated reply for the update itself); if neither (a) nor any other existing handler matches, current behavior is unchanged (the message is unhandled, per the "not a general-purpose chat" convention) until `004-chat-responsiveness` is implemented.

**Rationale**: The two checks are orthogonal signals a single message could contain in principle ("I'm in Tokyo, what's my total?"), so running both independently rather than treating them as mutually exclusive is simplest and most correct. A silent time-zone update (no confirmation text) avoids inventing new user-facing copy this spec doesn't require, though the location-share path (a deliberate, explicit user action) does get a short confirmation — see contracts/timezone-update.md.

## 7. New WhatsApp message type: `location`

**Decision**: Add a dedicated handler for inbound message type `location` (latitude/longitude + optional name/address), alongside the existing `text`/`image` handling in `app/whatsapp/webhook.py` — verify signature (already global), resolve/create the user, dedupe by `wa_message_id` (existing convention), reverse-geocode via `timezonefinder`, update `users.time_zone`, send a short confirmation reply, record the message.

**Rationale**: `.claude/skills/whatsapp-api/SKILL.md` currently documents `text`, `image`, and `interactive` as the handled types; `location` is a standard WhatsApp Cloud API inbound message type not yet documented there because nothing needed it before this feature. Follows the exact same dispatch shape as the existing `image`/`text` branches — no new plumbing invented.
