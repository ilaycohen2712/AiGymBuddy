# Implementation Plan: Chat Responsiveness

**Branch**: `004-chat-responsiveness` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-chat-responsiveness/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Close the "silent drop" gap: every inbound free-form text message and every
inbound message of a type the bot has no dedicated handler for gets a reply,
never silence. The recognition-and-reply layer this adds is deliberately
**non-generative** for every new path — a safety-signal check, a bounded
supported-question match (reusing 002's daily-total handler), a fixed
unsupported-message-type acknowledgment, and a fixed fallback reply are all
keyword-matched and template-based, never an LLM call shaped by user text.
That's the structural anti-injection guarantee FR-012/FR-013 ask for: there
is no interpretive layer for a "ignore your instructions" message to
exploit, because nothing new here interprets free text as instructions. The
one pre-existing place user text *does* reach an LLM — the photo-clarification
answer, concatenated into the vision prompt — gets hardened (not newly
introduced) as part of this feature, per FR-012/AS6.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing app/)

**Primary Dependencies**: FastAPI, `anthropic` SDK (existing, not newly invoked by this feature's own paths), asyncpg, pytest/pytest-asyncio

**Storage**: PostgreSQL (Supabase), migrations in `app/db/migrations/`

**Testing**: pytest — unit tests for the safety-signal/fallback dispatch logic, contract tests extending `tests/contract/test_webhook_image.py`'s pattern for text and unsupported-type messages

**Target Platform**: Linux server (Railway/Render), same deployment as the rest of the app

**Project Type**: Single backend service — extends the existing `app/` layout (Option 1), no new project

**Performance Goals**: SC-003 — a reply to a free-form message arrives with no perceptible added delay vs. today's meal-photo reply. Since every new path is a keyword match + fixed string (no LLM call), this is trivially met — the only latency-bearing new code is faster than the vision-model call it's being compared to.

**Constraints**: Must never let user-supplied free text reach an LLM in a way that could shape the bot's *own* reply content in any new code path (FR-012, FR-013); must not regress the existing clarification/daily-total flows (FR-002, SC-005); replies must use the existing coach voice (FR-004) but are static, not generated, so this is a copy-writing constraint, not a prompting one.

**Scale/Scope**: Same traffic profile as the rest of the bot — every inbound text/unsupported-type message from every user, no new data collection (FR-011).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Accuracy honesty | No new calorie/macro estimation logic; reuses 002's existing range-formatted daily-total reply verbatim | PASS (N/A) |
| II. Push, not pull | This feature is purely reactive (spec Assumption: "does not add any new proactive/push messaging behavior") | PASS (N/A) |
| III. Safety first | FR-005 requires safety escalation on medical/disordered-eating signals in free-form text — **no such detector exists anywhere in the codebase today** (verified: no matches for "disordered"/"escalat"/"safety" in `app/`). This plan builds a minimal keyword-based detector as part of this feature, since FR-005 is a MUST within this spec's own scope and no other feature currently owns it (research.md #4) | PASS (addressed, not deferred) |
| IV. Schema discipline | The one LLM call this feature touches (photo-clarification, pre-existing) already validates its output against the calorie-estimation schema before persistence; no new unvalidated LLM output is introduced since no new path calls an LLM | PASS |
| V. Platform independence | New dispatch logic lives in `app/services/`, not `app/whatsapp/`; only the WhatsApp-specific message-type routing stays in `webhook.py` | PASS |
| Security requirements | Webhook signature verification already covers every message type via the shared `receive_webhook` entrypoint (unchanged); no new secrets | PASS |

No violations — Complexity Tracking is not needed.

*Post-design re-check (after Phase 1)*: data-model.md adds one CHECK-
constraint value (no new table), and the two new service modules
(`chat_fallback.py`, `safety.py`) contain zero LLM calls between them — the
Constitution IV concern ("LLM outputs schema-validated before insert") never
applies to this feature's own new code, only to the pre-existing
clarification path this feature hardens (contracts/clarification-hardening.md).
Gate table above still holds — no new violations introduced by the design.

## Project Structure

### Documentation (this feature)

```text
specs/004-chat-responsiveness/
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
├── services/
│   ├── chat_fallback.py           # NEW: dispatch — safety check → supported
│   │                               #      question → fallback; fixed reply text
│   ├── safety.py                   # NEW: keyword-based medical/disordered-eating
│   │                               #      signal detection (FR-005) + fixed
│   │                               #      escalation replies (coach-persona)
│   └── daily_total.py              # UNCHANGED: reused as-is as the sole
│                                     #      registered "supported question" handler
├── prompts/
│   └── calorie_vision.md           # MODIFIED: harden the clarification-answer
│                                     #      block against being read as instructions
├── whatsapp/
│   └── webhook.py                  # MODIFIED: _handle_text_message no longer
│                                     #      returns silently when nothing matches;
│                                     #      new _handle_unsupported_message for any
│                                     #      message type besides image/text/location
└── db/
    └── migrations/
        └── 0006_widen_messages_kind_for_other.sql   # NEW: messages.kind += 'other'

tests/
├── unit/
│   ├── test_chat_fallback.py       # NEW: dispatch precedence, fallback text
│   └── test_safety.py              # NEW: signal detection, escalation replies
└── contract/
    └── test_webhook_image.py       # EXTENDED: fallback-reply, unsupported-type-ack,
                                      #      redirection-attempt, dedupe-of-new-kind cases
```

**Structure Decision**: Single backend project (existing `app/` layout,
Option 1). Two new small service modules (`chat_fallback.py`, `safety.py`),
one migration, one prompt hardening, and `webhook.py` changes confined to
the two spots that currently drop messages silently. No new tables — this
feature is routing/reply behavior, not new data.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
