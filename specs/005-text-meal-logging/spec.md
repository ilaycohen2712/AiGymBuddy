# Feature Specification: Text-Based Meal Logging

**Feature Branch**: `005-text-meal-logging`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description: "Allow users to log a meal by sending a free-form text description of food and quantities (e.g. '100 grams rice, 120 grams chicken breast'), not only a photo. The bot should estimate calories/macros from the text the same way it does from a photo — using a calorie-range reply in the same format as photo-based logging — and log it as a meal (subject to the same 10-minute grouping window, daily totals accumulation, and range-not-exact-number presentation as photo-based logging). This must not break the existing text-message flows: a pending clarifying-question answer still takes priority, then a food-description message should be detected and logged, and anything else still falls through to the existing safety/supported-question/fallback handling in chat_fallback.py."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Log a meal by typing it (Priority: P1)

A user who doesn't have (or doesn't want to take) a photo of their food types a description with quantities directly into the chat — e.g. "100 grams rice, 120 grams chicken breast" — and the bot replies with a calorie/macro range for that meal, in the same style as a photo-based reply, and the meal is recorded toward the user's daily total.

**Why this priority**: This is the entire feature — without it there's nothing to test or ship. Photo logging already exists; this closes the gap for users who'd rather type than photograph (at a desk, food already eaten, no camera handy).

**Independent Test**: Send a text message describing specific food items and quantities to the bot with no prior photo or pending clarification. Verify the reply is a calorie-range message (not a fallback or safety message) and that the meal appears in the user's daily total.

**Acceptance Scenarios**:

1. **Given** a user with no open meal and no pending clarification, **When** they send "100 grams rice, 120 grams chicken breast", **Then** the bot replies with a calorie/macro range covering both items and logs a new meal.
2. **Given** a user who logged a photo-based meal 3 minutes ago, **When** they send a text description of another food item, **Then** the bot treats it as an addition to the still-open meal (same 10-minute grouping window as photo-to-photo), replying with this item's contribution and the meal's updated running total.
3. **Given** a user sends a text description in Hebrew (e.g. "150 גרם אורז ו-100 גרם חזה עוף"), **When** the bot processes it, **Then** it estimates and logs the meal the same as it would for the English equivalent.

---

### User Story 2 - Existing text flows keep working unchanged (Priority: P1)

Every other kind of text message a user might send — a pending clarifying-question answer, a safety-relevant message, a supported question like "what's my total today", or plain small talk — continues to be handled exactly as it is today, with food-description logging never intercepting or breaking those flows.

**Why this priority**: Equally critical to User Story 1 — a regression here (e.g. a safety-relevant message getting misrouted into meal logging, or a pending clarification being ignored) would be a safety and correctness failure, not just a missed feature. Both stories must ship together for this feature to be safe to release.

**Independent Test**: Exercise each existing text pathway (pending clarification answer, a message matching a safety signal, a supported-question match, an unrelated chat message) with the new detection logic active, and confirm each still produces its original, unchanged reply and behavior.

**Acceptance Scenarios**:

1. **Given** a user has a pending clarifying question from a photo, **When** they reply with any text (even one that also looks like a food description), **Then** it is treated as the clarification answer, not a new text-based meal log.
2. **Given** a user sends a message matching a safety signal (per coach-persona's escalation rules), **When** the message is processed, **Then** the safety escalation reply is sent and no meal is logged, regardless of whether the message also mentions food.
3. **Given** a user sends "what's my total today", **When** the message is processed, **Then** the existing daily-total reply is returned, not a meal-logging attempt.
4. **Given** a user sends a message with no food/quantity content (e.g. "how's it going"), **When** the message is processed, **Then** the existing fixed fallback reply is returned, unchanged.

---

### Edge Cases

- What happens when the text mentions food but gives no usable quantity (e.g. "I had some chicken and rice")? The estimate would be low-confidence and risks misleading the user's daily total (Constitution I).
- What happens when the text is a mix of a food description and an unrelated question in the same message (e.g. "100g rice, also what's my total today")?
- What happens when the described food is implausible or the text is nonsensical ("500kg rice")?
- What happens when the text contains something that reads like an instruction rather than a food description (the same untrusted-input concern already handled for photo clarification answers, calorie_vision.md rule 11)?
- What happens when a user sends numbers with no food context at all (e.g. just "120")?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect, for any free-form text message that is not a pending-clarification answer, whether the message is a food-description-with-quantities intended for meal logging.
- **FR-002**: When a food description is detected, the system MUST estimate calories and macros (protein/carbs/fat) for the described items, grounded in the same nutritional-density discipline already required for photo-based estimation (calorie_vision.md rules 5, 12, 13 equivalents), not a false-precision guess.
- **FR-003**: The system MUST present the estimate to the user as a range, never an exact number, using the same reply formatting already used for photo-based meal logging (`app/services/meal_logging.py` reply formatters).
- **FR-004**: The system MUST log a text-based meal using the same grouping rules as photo-based meals: append to an already-open meal within the existing 10-minute window, or start a new meal otherwise.
- **FR-005**: The system MUST accumulate a text-logged meal's calories/macros into the user's daily totals, using the same additive, non-double-counting accumulation already used for photo-based meals.
- **FR-006**: The system MUST support text-based meal descriptions in both Hebrew and English (matching the bot's existing bilingual usage in this chat).
- **FR-007**: The system MUST NOT treat a pending clarifying-question answer as a new food-description message — that existing flow takes priority, unchanged.
- **FR-008**: The system MUST NOT treat a safety-relevant message as a food-description message — safety escalation (coach-persona) takes priority over meal logging, even if the message also mentions food.
- **FR-009**: The system MUST fall through to the existing supported-question handling (e.g. daily-total requests) when the message matches a supported question rather than a food description.
- **FR-010**: The system MUST fall through to the existing fixed fallback reply when a message is neither a pending-clarification answer, a safety signal, a food description, nor a supported question — unchanged from current behavior.
- **FR-011**: The system MUST treat any text following a food-description prompt as untrusted, descriptive input only — never as an instruction that changes the estimation model's behavior, output schema, or role (same defense-in-depth principle as calorie_vision.md rule 11 for clarification answers).
- **FR-012**: When a described food item's quantity is genuinely unstated and materially affects the estimate (e.g. "chicken and rice" with no amounts), the system MUST ask a clarifying question for the missing quantity rather than silently guessing, reusing the existing one-round-trip clarification mechanism.

### Key Entities

- **Meal** (existing entity, `meals` table): gains a text-originated creation path alongside the existing photo-originated path. A text-logged meal's `photo_media_ids` has no corresponding photo — this feature must define how a meal record represents "no photo" without breaking existing assumptions built around photo IDs.
- **Text meal description** (new, ephemeral): the parsed/estimated result of a user's free-form text — same shape as a photo's vision result (foods list, total calories, confidence, optional clarifying question) — not persisted as its own entity beyond becoming a Meal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can log a meal by typing a food description with quantities and receive a calorie-range reply, without ever needing to take a photo.
- **SC-002**: Every existing text-message behavior (clarification answers, safety escalation, supported questions, fallback) is unaffected — measured by zero regressions in existing text-flow test coverage.
- **SC-003**: A text-logged meal contributes correctly to the user's daily total exactly once (verified the same way photo-logged meals are verified not to double- or under-count).
- **SC-004**: In a simulated week of realistic mixed messages (food descriptions, questions, small talk, safety-relevant messages), food-description detection does not misfire on non-food messages, and does not miss genuine food-description messages (validated via `coach-simulator`).

## Assumptions

- Detection of "is this text a food description" and estimation of its calories/macros are done together, in one LLM call, using a dedicated versioned prompt (mirroring `calorie_vision.md`'s pattern) rather than two separate calls — the same model that estimates the food can also report "this isn't a food description" for clearly-unrelated text, avoiding a separate classification step.
- Detection is free-form / natural-language based — there is no required trigger phrase or command syntax (e.g. no requirement to prefix with "log:"), matching the user's own example phrasing.
- Precedence order for an incoming text message is: pending clarification answer → safety check → food-description detection/logging → supported-question match → fixed fallback. This extends the existing chat_fallback.py precedence (safety → supported-question → fallback) by inserting food-description handling after safety and before supported-question matching, since a food-description message would not otherwise match a supported-question pattern.
- A meal record's "no photo" case (text-originated) is represented by the DB schema explicitly allowing an empty/absent photo reference, rather than a placeholder or fake photo ID — the exact mechanism is a `/speckit.plan` / db-schema decision, not a product decision.
- The bot does not attempt to log a meal from a message that mentions food only in passing with no quantity intent at all (e.g. "I'm not hungry") — FR-012's clarifying-question path is reserved for messages that read as an actual logging attempt with a materially missing quantity, not every passing food mention.
