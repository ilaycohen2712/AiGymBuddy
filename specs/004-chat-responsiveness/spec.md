# Feature Specification: Chat Responsiveness

**Feature Branch**: `004-chat-responsiveness`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "Make the chatbot responsive to inbound messages: when a user sends a message, the bot receives it and answers back, instead of the current behavior where free-form text (outside of completing a pending clarifying question about a food photo) is silently dropped with no reply."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a reply to any free-form message (Priority: P1)

A user sends the bot a text message that isn't completing a pending clarifying question about a food photo (e.g., a greeting, a question, a comment). Today that message is silently dropped. Instead, the bot should receive it and send back a reply, so the user never sends a message into what feels like silence.

**Why this priority**: This is the core gap — a chatbot that sometimes doesn't answer erodes trust in the whole product, including the parts (meal logging, reports) that already work well. It's the minimum needed for the bot to feel like a responsive conversation partner rather than a one-way photo-in, calories-out tool.

**Independent Test**: Can be fully tested by sending a free-form text message with no pending clarifying question outstanding, and verifying the bot sends back a reply rather than no response.

**Acceptance Scenarios**:

1. **Given** a user has no pending clarifying question outstanding, **When** they send a free-form text message, **Then** the bot sends back a reply instead of leaving the message unanswered.
2. **Given** a user does have a pending clarifying question outstanding, **When** they send a text message, **Then** the existing clarification-completion behavior still takes priority and is unaffected by this feature.
3. **Given** a user sends several free-form messages in a row, **When** each one is processed, **Then** each individually receives its own reply (no messages skipped or merged).

---

### User Story 2 - Get a reply to message types the bot can't act on (Priority: P2)

A user sends a message type the bot has no dedicated handling for (e.g., a voice note, a sticker, a document, a location share). Today these are silently ignored. Instead, the bot should acknowledge receipt and let the user know what it can actually help with, so the user isn't left wondering if the message went through.

**Why this priority**: Less frequent than free-form text, but the same trust problem applies — and it's a natural extension of the same "never leave a message unanswered" principle once User Story 1 exists.

**Independent Test**: Can be fully tested by sending a non-text, non-image message (e.g., a voice note) and verifying the bot sends back an acknowledgment reply rather than no response.

**Acceptance Scenarios**:

1. **Given** a user sends a message type the bot has no dedicated handling for, **When** it is received, **Then** the bot sends back a reply acknowledging it rather than staying silent.

---

### Edge Cases

- What happens when a reply to a general message would be sent outside the WhatsApp 24-hour customer-service window? (Governed by existing WhatsApp messaging rules; out of scope to change here.)
- What happens if the bot receives a burst of free-form messages from the same user in quick succession? (Each is still deduplicated and replied to individually, per existing per-message dedupe behavior — no new batching introduced by this feature.)
- What happens if generating a reply fails (e.g., an upstream error)? (Falls back to the same graceful fallback reply already used for photo/clarification failures — the user never receives silence even on error.)
- What happens if a free-form message contains a medical or disordered-eating signal? (The existing safety-escalation behavior applies, same as any other user-facing reply.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST send a reply to every free-form text message a user sends, even when there is no pending clarifying question outstanding for that user, instead of leaving it unanswered.
- **FR-002**: A pending structured flow (e.g., an outstanding clarifying question about a photo, an outstanding daily-calorie-target request) MUST continue to take priority over this feature's general reply behavior — this feature only governs what happens when no such flow is pending.
- **FR-003**: System MUST send an acknowledging reply to inbound message types it has no dedicated handling for (e.g., voice notes, stickers, documents, location shares), rather than silently ignoring them.
- **FR-004**: Replies sent under this feature MUST use the bot's established coaching voice (short, warm, mirrors the user's language) and MUST NOT include medical advice or prescriptive diet instructions.
- **FR-005**: A free-form message containing medical or disordered-eating warning signs MUST trigger the bot's existing safety-escalation behavior rather than a routine reply.
- **FR-006**: System MUST deduplicate and record every newly-answered message the same way inbound messages are already deduplicated and recorded today, so a redelivered webhook does not produce a duplicate reply.
- **FR-007**: If reply generation fails for any reason, the system MUST still send the user a graceful fallback reply rather than no reply at all, consistent with existing failure handling for photo and clarification messages.
- **FR-008**: The content of a reply to a free-form text message MUST [NEEDS CLARIFICATION: what should the bot actually say back? (a) hold an open-ended conversation on any topic within its coaching persona, using the LLM to generate a contextual answer; (b) recognize a bounded set of supported intents about the user's own data (e.g., "what's my total today", "what's my target") and answer only those, with a generic fallback otherwise; or (c) always send the same short generic acknowledgment (e.g., "Got it! Send a food photo to log a meal, or wait for your daily report.") regardless of what the user said]

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of free-form text messages sent when no clarifying question is pending receive a reply — zero are silently dropped.
- **SC-002**: 100% of inbound messages of a type the bot has no dedicated handling for receive an acknowledgment reply rather than no reply.
- **SC-003**: A reply to a free-form message arrives within the same response time users already experience for a meal-photo reply, with no perceptible added delay.
- **SC-004**: 0% of replies generated under this feature contain medical advice or crash-diet language, matching the existing safety bar for all other bot replies.
- **SC-005**: An existing pending clarifying question or daily-target request is still resolved correctly 100% of the time after this feature ships — no regression to that already-working flow.

## Assumptions

- This feature reuses the existing per-message deduplication and persistence pattern (the `messages` record and processed-message check) already used for photo and clarification-reply handling; no new dedupe mechanism is introduced.
- This feature reuses the existing WhatsApp send/mark-as-read plumbing; no new outbound channel work is needed.
- Standard WhatsApp messaging-window rules (e.g., the 24-hour customer service window) already govern when a reply can be sent and are unchanged by this feature.
- This feature covers reactive replies only — it does not add any new proactive/push messaging behavior (that remains governed separately by the coach-persona push rules).
