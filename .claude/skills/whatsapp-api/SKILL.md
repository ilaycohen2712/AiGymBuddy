---
name: whatsapp-api
description: Rules and knowledge for integrating with the Meta WhatsApp Business Cloud API — webhooks, message types, template messages, the 24-hour window. Use whenever writing or reviewing code that sends/receives WhatsApp messages.
---

# WhatsApp Business Cloud API

## Core concepts
- All inbound messages arrive as webhook POSTs to our `/webhook` endpoint. Always verify `X-Hub-Signature-256` (HMAC-SHA256 of raw body with the App Secret) before processing.
- Webhook verification handshake: GET with `hub.mode=subscribe` — echo back `hub.challenge` if `hub.verify_token` matches ours.
- Message types we handle: `text`, `image` (food photos — fetch media via media ID → GET /{media-id} → download URL, valid 5 min), `location` (latitude/longitude, optional name/address — used to update a user's stored time zone, specs/002-daily-total-tracking). Every other inbound message type (voice notes, stickers, documents, `interactive` button/list replies, etc.) gets a fixed acknowledgment reply rather than being silently dropped, recorded as `messages.kind='other'` (specs/004-chat-responsiveness, User Story 2).
- Every free-form text message gets a reply — a recognized supported-question answer (from real data), a safety escalation, a logged meal, or a fixed fallback — never silence (specs/004-chat-responsiveness). Dispatch precedence in `webhook.py::_handle_text_message` (first non-`None` wins): (1) pending clarifying-question answer (`meal_logging.handle_clarification_reply`), (2) pending daily-target ask (`daily_target.handle_daily_target_reply`), (3) a typed food description to log as a meal (`text_meal_logging.handle_text_meal_description`, specs/005-text-meal-logging — internally checks safety first and defers to (4) on a hit, so a safety-relevant message is never treated as food data even if it mentions food), (4) `chat_fallback.handle_free_form_text` (safety check again as a backstop, then supported-question, then fixed fallback).

## The 24-hour customer service window
- We may send free-form messages ONLY within 24h of the user's last inbound message.
- Outside the window: only pre-approved **template messages** (billed per conversation). Templates live in `app/whatsapp/templates.py` and must be registered in Meta Business Manager first.
- Design rule: every proactive push should invite a reply, to reopen the window.

## Sending
- POST `https://graph.facebook.com/v21.0/{phone_number_id}/messages` with Bearer token.
- Max text length 4096 chars; keep coach messages under 600 chars.
- Always mark inbound messages as read and show typing indicator for photo analysis (takes seconds).

## Errors & rate limits
- 131047: window expired → fall back to template. 131026: user not on WhatsApp. 80007: rate limit → exponential backoff.
- Never retry non-idempotent sends blindly; dedupe by `wa_message_id` via `queries.claim_message` — **claim it atomically before any expensive work starts (an LLM call, a slow DB write), not after handling finishes.** A check-then-record-at-the-end pattern was tried first and had a confirmed-live bug: Meta redelivers on timeout, a real Claude vision call comfortably takes long enough to hit that window, and a redelivery arriving before the first attempt recorded itself got fully reprocessed — duplicate paid API calls and duplicate meal logging for one photo. Every webhook handler in `app/whatsapp/webhook.py` claims first, unconditionally, before touching any handler logic.
