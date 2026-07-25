# Contract: `app/services/text_meal_logging.py` dispatch

The internal decision function `webhook.py`'s `_handle_text_message` calls after `meal_logging.handle_clarification_reply` and `daily_target.handle_daily_target_reply` both already returned `None`, and before falling through to `chat_fallback.handle_free_form_text`. No external HTTP surface — this is the interface between the webhook layer and "should this text log a meal."

```python
async def handle_text_meal_description(
    user_id: str, wa_phone: str, text: str
) -> str | None:
    """Returns None if this text isn't a food-logging attempt, or is
    safety-relevant (defer entirely to chat_fallback in either case).
    Otherwise estimates, logs the meal (or asks a clarifying question,
    capped at one round trip like the photo flow), and returns the reply
    text to send."""
```

## Precedence (fixed order, first match wins)

1. **Safety signal** (`app/services/safety.py`) — if `text` matches a medical or disordered-eating phrase, return `None` immediately without calling the text-estimation prompt at all. Deferred to `chat_fallback.handle_free_form_text`'s own (unchanged) safety-first check, which produces the actual escalation reply. This function never generates a safety reply itself — it only decides not to touch safety-flagged text (research.md #2).
2. **Text-estimation call** — call `text_analysis.analyze_text(text)` (contracts/calorie-text-prompt.md). If `is_food_description` is `false`, return `None` (defer to the next dispatch layer — this wasn't a food-logging attempt).
3. **Clarifying question** — if `is_food_description` is `true` and `clarifying_question` is set, persist the pending clarification (reusing `queries.set_pending_clarification`/`get_pending_clarification`/`clear_pending_clarification` — already generic over media type, extended to allow a `media_type` of `"text"` with no `media_id`) and return the question text.
4. **Log the meal** — otherwise, call the shared `log_meal_contribution` helper (data-model.md) with `text_entry=text`, get back the updated `MealRecord`, and return the formatted reply via `meal_logging.py`'s existing `_reply_for_logged_meal`-equivalent (now driven by `_contribution_count`, not `len(photo_media_ids)` alone).

## Postconditions

- Returning `None` means: this text was either safety-relevant or not about food at all — the caller (`webhook.py`) proceeds to `chat_fallback.handle_free_form_text`, unchanged.
- Returning a string means: a clarifying question was asked, or a meal was logged and its calorie-range reply is ready to send — the caller sends it directly, same as the existing clarification/daily-target layers, and does **not** also call `chat_fallback` (first non-`None` wins, same pattern as the two existing layers above it in the chain).
- `text` is never logged verbatim in application logs (existing PII rule) — only whether it was treated as a food description, a clarification, or deferred.

## Compatibility

- `chat_fallback.py`'s dispatch contract (`specs/004-chat-responsiveness/contracts/chat-fallback-dispatch.md`) is unchanged — this is a new caller inserted *before* it in `webhook.py`, not a modification to it. Its own internal safety check remains as a defense-in-depth backstop.
- `daily_target.handle_daily_target_reply` is unchanged. `meal_logging.handle_clarification_reply`'s *return contract* (`None` when nothing pending, a reply string otherwise) is unchanged, but its body was materially extended: it now also checks `safety.check_safety_signal` first (reviewer-flagged during this feature's review — a safety-relevant reply to a pending clarification was previously swallowed by a meal-logged or `NOT_FOOD_REPLY` response instead of the safety escalation) and branches on `pending["media_type"] == "text"` to complete a text-originated clarification via `text_analysis.analyze_text` instead of re-downloading a photo. This module (`text_meal_logging.py`) only adds a new *layer* after both return `None` — it doesn't call either directly.
- A pending clarification set by this module (text-originated) must be resolvable by the *same* `meal_logging.handle_clarification_reply` completion path already used for photo-originated clarifications — not a separate parallel mechanism — since a user's reply to "how many grams of chicken?" looks identical whether the original prompt came from a photo or a text description.
