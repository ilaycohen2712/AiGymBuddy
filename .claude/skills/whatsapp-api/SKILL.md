---
name: whatsapp-api
description: Rules and knowledge for integrating with the Meta WhatsApp Business Cloud API — webhooks, message types, template messages, the 24-hour window. Use whenever writing or reviewing code that sends/receives WhatsApp messages.
---

# WhatsApp Business Cloud API

## Core concepts
- All inbound messages arrive as webhook POSTs to our `/webhook` endpoint. Always verify `X-Hub-Signature-256` (HMAC-SHA256 of raw body with the App Secret) before processing.
- Webhook verification handshake: GET with `hub.mode=subscribe` — echo back `hub.challenge` if `hub.verify_token` matches ours.
- Message types we handle: `text`, `image` (food photos — fetch media via media ID → GET /{media-id} → download URL, valid 5 min), `interactive` (button/list replies).

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
- Never retry non-idempotent sends blindly; dedupe by our message UUID stored in DB.
