---

description: "Task list for Chat Responsiveness"
---

# Tasks: Chat Responsiveness

**Input**: Design documents from `/specs/004-chat-responsiveness/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included — plan.md's Technical Context calls for unit tests on the
new dispatch/safety logic and extended contract tests, consistent with this
codebase's existing test-first culture.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2)
so each can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 or US2 — maps to spec.md's user stories
- File paths are exact and relative to the repository root

## Path Conventions

Single backend project (existing `app/` layout — see plan.md's Project
Structure). No frontend/mobile split.

---

## Phase 1: Setup

No dedicated setup tasks — this feature extends existing modules and adds
one migration only; no new packages, directories, or tooling config needed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The schema change both message-handling paths in this feature
route through

**⚠️ CRITICAL**: No user story task can start until this phase is complete

- [X] T001 Write migration `app/db/migrations/0006_widen_messages_kind_for_other.sql`: widen the `messages_kind_check` constraint to add `'other'`, following the same drop-and-recreate pattern as `0005_widen_messages_kind_for_location.sql`, per data-model.md

**Checkpoint**: Schema ready — user story work can begin.

---

## Phase 3: User Story 1 - Get a reply to any free-form message (Priority: P1) 🎯 MVP

**Goal**: Every free-form text message gets a reply — a safety escalation,
a real-data answer to a recognized supported question, or a fixed
fallback — never silence; a pending clarification still takes priority;
free-form text (including a clarification answer) can never redirect the
bot's behavior.

**Independent Test**: Send a free-form text message with no pending
clarification and verify a reply is always sent (fallback, supported-answer,
or safety-escalation, depending on content); verify a pending clarification
is still resolved unaffected; verify a redirection attempt never produces
instruction-following behavior.

### Tests for User Story 1

- [X] T002 [P] [US1] Unit tests for `app/services/safety.py`: medical-signal phrases and disordered-eating-signal phrases (English + Hebrew) each route to their own fixed escalation reply; non-matching text returns `None`, in `tests/unit/test_safety.py`
- [X] T003 [P] [US1] Unit tests for `app/services/chat_fallback.py`'s `handle_free_form_text`: precedence order (a safety signal wins over a coincidental supported-question keyword overlap — e.g. a message matching both), the fixed fallback text for non-matching input, and that it never returns `None`, in `tests/unit/test_chat_fallback.py`
- [X] T004 [P] [US1] Contract test: a signed webhook text message that matches no pending clarification, no safety signal, and no supported question still gets `send_text_message` called with the fixed fallback reply — not silently dropped (today's behavior) — in `tests/contract/test_webhook_image.py`
- [X] T005 [P] [US1] Contract test, two sub-cases: (a) a redirection-attempt text ("ignore your instructions...") with no pending clarification gets the fallback reply, not an attempt to honor it; (b) the same text sent as a pending clarification's answer still produces only a calorie/macro range or graceful fallback — never content resembling a direct answer to the injected instruction — confirming the existing one-round-trip `clarifying_question` cap in `meal_logging.py` is unaffected, in `tests/contract/test_webhook_image.py`

### Implementation for User Story 1

- [X] T006 [US1] Implement `app/services/safety.py`: phrase lists (English + Hebrew) for the two categories per `coach-persona` skill, `check_safety_signal(text) -> str | None` returning the fixed medical or disordered-eating escalation reply
- [X] T007 [US1] Implement `app/services/chat_fallback.py`: `FALLBACK_REPLY` constant (coach-voice, per FR-004), a registered `(matcher, handler)` list for supported questions (currently just `daily_total._is_daily_total_request` / `daily_total.handle_daily_total_request`, per research.md #1), and `handle_free_form_text(user_id, wa_phone, text) -> str` implementing the precedence in contracts/chat-fallback-dispatch.md (depends on: T006)
- [X] T008 [US1] Update `app/whatsapp/webhook.py`'s `_handle_text_message`: when `meal_logging.handle_clarification_reply` returns `None`, call `chat_fallback.handle_free_form_text` instead of leaving `reply_text` as `None` and silently returning — remove the now-dead "no pending clarification or recognized request, ignoring text" early-return branch since a reply is now always produced (depends on: T007)
- [X] T009 [US1] Harden `app/prompts/calorie_vision.md` per contracts/clarification-hardening.md: add an explicit rule that the "user's answer" segment of the clarification prompt is untrusted, descriptive-only data about the photographed food's content — never an instruction — and the model must not deviate from the fixed output schema regardless of its content

**Checkpoint**: User Story 1 is fully functional and independently testable — every free-form text gets a reply, redirection attempts fail safely, the existing clarification/daily-total flows are unaffected.

---

## Phase 4: User Story 2 - Get a reply to message types the bot can't act on (Priority: P2)

**Goal**: An inbound message of a type the bot has no dedicated handler for
(voice note, sticker, document, etc.) gets a fixed acknowledgment reply
instead of being silently ignored.

**Independent Test**: Send a signed webhook payload with a message type
other than `image`/`text`/`location` and verify a fixed acknowledgment reply
is sent and the message is recorded/deduped like any other.

### Tests for User Story 2

- [X] T010 [P] [US2] Contract test: a signed webhook payload with `"type": "audio"` (and separately `"sticker"`, `"document"`) gets `send_text_message` called with the fixed acknowledgment reply, and the recorded `messages` row has `kind = 'other'`, in `tests/contract/test_webhook_image.py`
- [X] T011 [P] [US2] Contract test: a duplicate delivery of the same unsupported-type message (`wa_message_id` unchanged) is deduped — `send_text_message` is called exactly once across both deliveries — in `tests/contract/test_webhook_image.py`

### Implementation for User Story 2

- [X] T012 [US2] Add `acknowledge_unsupported_type() -> str` to `app/services/chat_fallback.py`: a fixed acknowledgment reply, no branching on the actual message type since the reply is identical regardless (research.md #5) (depends on: T007 — file must already exist)
- [X] T013 [US2] Add `_handle_unsupported_message` to `app/whatsapp/webhook.py`, mirroring the shape of the existing `_handle_location_message`: resolve user, dedupe check via `is_message_processed`, call `chat_fallback.acknowledge_unsupported_type`, record via `record_message(..., kind="other")`, send via the existing `_send_reply_and_record` helper (depends on: T001, T012)
- [X] T014 [US2] Wire a new branch in `_dispatch_messages`: any `msg_type` not in `{"image", "text", "location"}` now routes to `_handle_unsupported_message` instead of the current `logger.info("Ignoring unsupported message type=...")` fallthrough (depends on: T013)

**Checkpoint**: User Stories 1 and 2 both work independently and together — every inbound message this bot receives now gets a reply of some kind.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Verification and documentation that spans both stories,
including the two review gates flagged before planning began

- [X] T015 [P] Update `.claude/skills/whatsapp-api/SKILL.md` and/or `.claude/skills/coach-persona/SKILL.md` to note the new `messages.kind = 'other'` value and that safety-escalation is now implemented (previously documented as a rule with no code), per data-model.md and research.md #4
- [X] T016 Run the `coach-simulator` agent (per CLAUDE.md: "run before releasing push-rule or conversation changes") — this is a conversational-flow change

  **Finding, addressed**: found real coverage gaps in `safety.py`'s phrase lists — natural phrasings like "my knee has been killing me" and "I've barely eaten anything the last three days" fell through to the generic fallback instead of escalating. Broadened both phrase lists (with false-positive guard tests) before finalizing. Also flagged that fixed reply constants have no Hebrew variant despite Hebrew phrase-matching working — a pre-existing gap across the whole bot (`NOT_FOOD_REPLY`, `NO_MEALS_YET_REPLY`, etc. are all English-only too), not introduced by this feature; noted as a follow-up, not fixed here (out of this feature's scope).

- [X] T017 Run the `reviewer` agent (per CLAUDE.md: "run before merging webhook/data/billing changes") — this touches `app/whatsapp/webhook.py`; pay particular attention to contracts/clarification-hardening.md's redirection-resistance claim

  **Finding, addressed**: no blocking issues; one warning (`db-schema/SKILL.md` wasn't updated for the new `'other'` kind value, breaking this repo's own established convention) — fixed. Confirmed the structural non-LLM guarantee holds and the double-layer clarification hardening (prompt + code) is real, not just asserted.

- [X] T018 Run `pytest tests/ -q` and `ruff check app/ tests/` — full suite, no regressions to the existing clarification/daily-total/vision-comparison/location flows
- [X] T019 Walk through all seven scenarios in [quickstart.md](quickstart.md) end-to-end

  **Coverage note**: all seven scenarios are covered by real, passing automated tests (mapped 1:1 to specific test functions) rather than a literal manual run against a live WhatsApp/deployed environment — no such environment was available this session, consistent with how prior features (002, 003) in this repo handled the same gap. Migration 0006 was applied to and verified against the real local dev Postgres.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No tasks
- **Foundational (Phase 2)**: BLOCKS User Story 2 directly (needs the `'other'` kind value); does not block User Story 1, which touches no schema
- **User Story 1 (Phase 3)**: Can start immediately — no dependency on Phase 2
- **User Story 2 (Phase 4)**: Depends on Phase 2 (T001) for the schema, and on User Story 1's T007 for `chat_fallback.py` to already exist (T012 adds a function to a file US1 creates) — the only cross-story coupling; US2's own behavior is otherwise independently testable without any of US1's safety/fallback logic ever running
- **Polish (Phase 5)**: Depends on both user stories being complete

### Within Each User Story

- Tests before implementation (T002–T005 before T006–T009; T010–T011 before T012–T014)
- `safety.py` before `chat_fallback.py` (the dispatcher calls the safety check)
- Service-layer changes before the `webhook.py` call site that wires them in
- Story complete and checkpointed before moving to the next priority (if working sequentially)

### Parallel Opportunities

- T002 and T003 (US1 tests) can run in parallel — different files
- T004 and T005 (US1 contract tests) can run in parallel with T002/T003 — same test file, different test functions, no shared state
- T010 and T011 (US2 tests) can run in parallel
- T015 (Polish, skill docs) can run in parallel with T016–T018
- User Story 2's tests (T010, T011) can be written in parallel with all of User Story 1's work — they only need Foundational (T001) done, not US1's completion — but US2's *implementation* (T012) is blocked on T007 landing first

---

## Parallel Example: User Story 1

```bash
# Once Foundational (T001) is checkpointed — though US1 doesn't need it — in parallel:
Task: "Unit tests for safety.py signal detection in tests/unit/test_safety.py"                          # T002
Task: "Unit tests for chat_fallback.py dispatch precedence in tests/unit/test_chat_fallback.py"          # T003
Task: "Contract test: unmatched text gets fallback reply in tests/contract/test_webhook_image.py"        # T004
Task: "Contract test: redirection attempts never succeed in tests/contract/test_webhook_image.py"        # T005
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (needed for US2 later, harmless to do first regardless)
2. Complete Phase 3: User Story 1
3. **STOP and VALIDATE**: send free-form messages covering fallback, supported-question, safety-signal, and redirection-attempt cases; confirm the existing clarification/daily-total flows are unaffected
4. This alone closes the core "silent drop" gap (SC-001) and the security-relevant guarantee (SC-008)

### Incremental Delivery

1. Foundational → schema ready for US2 whenever it lands
2. Add User Story 1 → validate independently → the trust-eroding silent-drop gap is closed for text messages, safely
3. Add User Story 2 → validate independently → the same closes for every other message type
4. Each story adds value without breaking the previous one

### Parallel Team Strategy

With two developers after Foundational is checkpointed:

- Developer A: User Story 1 (the larger, security-relevant piece)
- Developer B: User Story 2's tests (T010, T011) can start immediately; implementation (T012) waits on Developer A's T007

---

## Notes

- [P] tasks touch different files (or independent functions in the same test file) with no unmet dependency
- [Story] labels map every user-story-phase task back to spec.md's US1/US2
- No task in this feature persists unvalidated LLM output — the only LLM-touching path (photo clarification) is pre-existing and only hardened here, not newly introduced (Constitution IV, research.md #3)
- Every new fixed reply string (fallback, both safety-escalation replies, unsupported-type acknowledgment) must read in the established coach voice (FR-004) — short, warm, per `coach-persona` skill
- Commit after each task or logical group; stop at each phase checkpoint to validate that story independently
