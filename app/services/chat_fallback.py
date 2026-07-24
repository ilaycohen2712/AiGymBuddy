from __future__ import annotations

from app.services import daily_total, safety

# Fixed, non-generative reply text (research.md #3) — every reply this
# module returns is one of these constants or a real-data answer already
# built by a registered supported-question handler; nothing here ever
# concatenates `text` into an LLM prompt. That's what makes FR-013's
# anti-injection guarantee structural rather than just a stated rule.

FALLBACK_REPLY = (
    "I'm not sure how to help with that one — send me a photo of your meal to "
    "log it, or ask me for your total so far today."
)

UNSUPPORTED_TYPE_REPLY = (
    "Got that! Right now I can only work with food photos and text messages — "
    "send me a photo of your meal, or ask for your total so far today."
)

# research.md #1: "daily calorie target" isn't real, tracked data yet (spec
# 001's target-collection story is unimplemented) — the initial supported-
# question list is exactly this one entry. Add future entries here, once
# their underlying data actually ships, without touching the dispatch logic
# below.
_SUPPORTED_QUESTION_HANDLERS = (daily_total.handle_daily_total_request,)


async def handle_free_form_text(user_id: str, wa_phone: str, text: str) -> str:
    """Dispatch for any free-form text that isn't completing a pending
    clarification (that check happens one layer up, in webhook.py, before
    this is ever called — FR-002). Precedence, first match wins
    (contracts/chat-fallback-dispatch.md):

    1. A safety signal (medical or disordered-eating) — always checked
       first, overriding a coincidental supported-question keyword overlap.
    2. A recognized supported question, answered from the user's real data.
    3. The fixed fallback reply.

    Never returns None (FR-001, FR-009)."""
    safety_reply = safety.check_safety_signal(text)
    if safety_reply is not None:
        return safety_reply

    for handler in _SUPPORTED_QUESTION_HANDLERS:
        reply = await handler(user_id, wa_phone, text)
        if reply is not None:
            return reply

    return FALLBACK_REPLY


def acknowledge_unsupported_type() -> str:
    """Fixed reply for any inbound message type this bot has no dedicated
    handler for (FR-003) — no branching on the actual type, since the reply
    is identical regardless (research.md #5)."""
    return UNSUPPORTED_TYPE_REPLY
