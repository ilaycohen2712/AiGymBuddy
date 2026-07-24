# Contract: `app/services/chat_fallback.py` dispatch

The internal decision function `webhook.py`'s `_handle_text_message` calls
once its existing clarification check (`meal_logging.handle_clarification_reply`)
returns `None`. No external HTTP surface — this is the interface between the
webhook layer and the "what should we say back" decision.

```python
async def handle_free_form_text(
    user_id: str, wa_phone: str, text: str
) -> str:
    """Never returns None — always a reply string (FR-001, FR-009). Reused
    only when meal_logging.handle_clarification_reply already returned None
    (FR-002: a pending structured flow takes priority, unaffected)."""
```

## Precedence (fixed order, first match wins)

1. **Safety signal** (`app/services/safety.py`) — if `text` matches a
   medical or disordered-eating phrase, return the corresponding fixed
   escalation reply. Always checked first (research.md #4): a safety signal
   overrides a coincidental keyword overlap with a supported question.
2. **Supported question** — iterate the registered `(matcher, handler)`
   list (data-model.md); the first matcher that returns non-`None` from its
   handler wins. Currently: `daily_total.handle_daily_total_request` only.
3. **General fallback** — if nothing above matched, return the fixed
   `FALLBACK_REPLY` constant (FR-009).

## Postconditions

- The return value is always one of: a safety-escalation string, a
  supported-question answer built from the user's real current data
  (FR-010), or the fixed fallback string. **Never** text derived from an
  LLM call shaped by `text` — no new path in this module calls an LLM
  (research.md #3).
- `text` is never logged verbatim (existing PII rule, Constitution/Security
  requirements) — only whether a signal/question matched, at most.

## Unsupported message types

A parallel, simpler function for FR-003:

```python
def acknowledge_unsupported_type() -> str:
    """Always returns the same fixed acknowledgment string — no branching
    on the actual message type, since the reply is identical regardless
    (research.md #5)."""
```

Called from a new `webhook.py::_handle_unsupported_message`, mirroring the
shape of the existing `_handle_location_message`: resolve user, dedupe
check, call this, record with `kind="other"`, send.

## Compatibility

- `meal_logging.handle_clarification_reply` and `daily_total.handle_daily_total_request`'s
  own signatures and behavior are unchanged — this module only adds a new
  caller after both already return `None`.
