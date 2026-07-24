# Phase 0 Research: Chat Responsiveness

No `NEEDS CLARIFICATION` markers remained in the spec (the requirements
checklist confirms this: 16/16). Research here resolves *design* unknowns —
two of which turned out to be genuine, codebase-verified scope findings, not
just implementation choices.

## 1. What is the actual initial list of "supported questions" (FR-008, FR-011)?

**Finding**: The spec's own examples ("their running total so far today,
their daily calorie target") assume both are already-tracked data. Verified
against the actual codebase: the **running daily total** is fully shipped
(`app/services/daily_total.py`, spec 002, merged). The **daily calorie
target** is *not* — `specs/001-photo-calorie-tracking`'s User Story 3
(target collection + end-of-day report) is unimplemented: no
`users.daily_calorie_target` column exists in any migration, no
`app/scheduler/eod_trigger.py`, no `app/prompts/eod_feedback.md` (confirmed
by `grep` across `app/` and the migrations directory; 001's own `tasks.md`
shows 19/40 done, with exactly the target-collection/report phase pending).

**Decision**: The initial supported-question set for this feature is
**exactly one**: the running daily total, via 002's existing
`daily_total.handle_daily_total_request`. This matches spec's own
Assumption ("finalized during planning, based on what data is already
available from shipped features at that time") — it is not a scope cut,
it's applying that stated rule to the actual current state. `chat_fallback.py`
registers supported-question handlers as a small ordered list so adding
"daily calorie target" later (once 001 ships it) is a one-line addition, not
a redesign.

**Alternatives considered**:
- *Build a stub "calorie target" answer now (e.g., "not set yet")*: rejected
  — FR-011 says this feature must not introduce new data collection, and a
  stub risks looking like a real, finished feature when the underlying data
  path doesn't exist; better to add it for real once 001 ships.

## 2. How does the bot recognize a "supported question" in free-form text?

**Decision**: Reuse `daily_total.py`'s existing substring/keyword matcher
(`_TOTAL_REQUEST_PHRASES`, English + Hebrew) unchanged as the sole
recognizer — no new LLM call. `chat_fallback.py` calls
`daily_total.handle_daily_total_request` first; if it returns `None` (no
match), that *is* "no recognized supported question" per FR-009.

**Rationale**: The spec's own quality bar is "reasonably direct phrasings...
not exhaustive natural-language understanding" — the existing matcher
already meets this bar in production (002). Reusing it means zero new LLM
calls, zero new latency/cost on this path, and — critically for FR-013 —
zero new place where free text is fed to a model that could shape output.

**Alternatives considered**:
- *An LLM classifier (Haiku-class, mirroring `timezone_extraction.md`'s
  pattern) mapping free text to a bounded enum of question categories*:
  rejected for now — with only one supported question, a keyword matcher is
  simpler, free, and equally correct; revisit if/when the supported-question
  list grows large enough that keyword coverage becomes unwieldy (the
  registered-handler-list design in decision #1 keeps this swappable later
  without a rewrite).

## 3. How is the anti-injection guarantee (FR-012, FR-013, SC-008) actually structural, not just a stated rule?

**Decision**: Every *new* reply path this feature adds — safety escalation,
supported-question answer, unsupported-message-type acknowledgment, general
fallback — is built from a **fixed template string**, never an LLM call
shaped by the inbound text. The matching step (safety-signal keywords,
question keywords) only decides *which* fixed reply to send; user text is
never concatenated into a prompt or reflected back verbatim in any of these
four paths.

**Rationale**: This is what makes SC-008 ("0% of free-form messages...
succeed in producing bot behavior outside its established purpose") true by
construction rather than by hoping a prompt's instructions hold: there is no
interpretive layer in these four paths for a "ignore your instructions"
message to exploit, because none of them interpret free text as anything
other than a lookup key into a fixed set of replies.

**The one gap this doesn't cover**: the pre-existing photo-clarification
answer *does* get concatenated into the vision prompt
(`app/services/vision.py` / `app/prompts/calorie_vision.md`, spec 001) —
this is the literal scenario AS6/FR-012 describe and the one LLM-touching
path in scope. Mitigation (defense-in-depth, not a claim of perfect
prevention — no prompt-level defense against injection is 100% guaranteed):
add an explicit rule to `calorie_vision.md` that the user's answer is
untrusted, descriptive-only data about the photographed food, never an
instruction, and that the model must not deviate from the fixed output
schema regardless of the answer's content. The existing one-round-trip cap
("Deliberately not re-triggering a second clarifying_question", already in
`meal_logging.py`) already limits the blast radius of a successful
injection to a single reply.

**Alternatives considered**:
- *Sanitize/strip the clarification text before use*: rejected as
  insufficient alone — pattern-based sanitization against prompt injection
  is unreliable and gives false confidence; an explicit prompt rule plus the
  existing round-trip cap is the standard, honest mitigation, not a
  guarantee.

## 4. Where does safety-signal detection (FR-005) actually live, since nothing implements it today?

**Finding**: Verified via `grep` across `app/` for "disordered", "escalat",
"safety" — zero matches. The `coach-persona` skill documents *what* the
escalation behavior should be (medical symptoms → stop topic, advise
professional care; disordered-eating signals → empathetic message, suggest
professional support, no further deficit advice) but no code implements it
anywhere in the shipped product.

**Decision**: Build a minimal keyword/phrase-based detector,
`app/services/safety.py`, in the same shape as `daily_total.py`'s matcher
(English + Hebrew phrase lists), checked **first** in `chat_fallback.py`'s
dispatch order — before the supported-question check — so a safety signal
always wins over a coincidental keyword overlap. Two fixed escalation
replies (medical, disordered-eating), per `coach-persona`'s existing rules.

**Rationale**: FR-005 is a MUST inside *this* spec's own scope, and this is
the first feature where every free-form message is inspected at all — there
is no other natural owner for it yet. Building it here, at the same
quality bar as the supported-question matcher (best-effort keyword
matching, not exhaustive clinical detection), is honest about its limits
while still satisfying the requirement as written.

**Alternatives considered**:
- *Defer FR-005 entirely to a future dedicated safety feature*: rejected —
  FR-005 is written as a MUST within 004's own functional requirements, not
  cross-referenced as "out of scope, see spec X"; deferring it would leave a
  written requirement unimplemented without spec authorization to do so.
- *An LLM-based signal classifier*: rejected for the same reason as decision
  #2 — keyword matching meets the stated bar, costs nothing, and adds no new
  injection surface; can be revisited later.

## 5. How are unsupported message types (voice, sticker, document, etc.) recorded for dedupe (FR-006)?

**Decision**: Add a single new `messages.kind` value, `'other'`, covering
every WhatsApp message type this feature doesn't give dedicated handling to
(audio, document, sticker, video, contacts, interactive, button, order,
reaction, system, and any future type Meta introduces) — one migration
(`0006_widen_messages_kind_for_other.sql`), not one kind value per type.

**Rationale**: The bot's behavior is identical for all of them (one fixed
acknowledgment reply); the dedupe/record mechanism (FR-006, reusing the
existing `is_message_processed`/`record_message` pattern per spec's own
Assumption) only needs to distinguish "was this exact `wa_message_id`
already handled," not which specific unsupported type it was. Enumerating
each type would mean a new migration every time WhatsApp adds a message
type, for no behavioral benefit.

**Alternatives considered**:
- *One `messages.kind` value per WhatsApp message type*: rejected — no
  code path or query anywhere reads `kind` to distinguish between, say,
  `sticker` and `document`; it would be schema churn with no consumer.
