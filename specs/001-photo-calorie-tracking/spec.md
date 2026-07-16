# Feature Specification: Photo Calorie Tracking MVP

**Feature Branch**: `001-photo-calorie-tracking`

**Created**: 2026-07-16

**Status**: Draft

**Input**: User description: "Photo calorie tracking MVP: user sends a food photo on WhatsApp, bot replies with calories and macros as a range, keeps a running daily total, and sends one end-of-day report with total calories eaten, protein/carbs/fat, and generated feedback relative to what they ate and their daily target."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Log a meal from one or more photos (Priority: P1)

A user takes a photo of their food and sends it to the bot on WhatsApp. The bot analyzes the photo and replies with an estimated calorie range and macro range (protein, carbs, fat) for that meal. If the user sends more photos of the same meal shortly after (e.g., one per dish), the bot combines them into a single meal entry rather than logging duplicates.

**Why this priority**: This is the core value exchange of the feature — without it, nothing else in this spec has a reason to exist. It must work standalone before any aggregation or proactive messaging is layered on.

**Independent Test**: Can be fully tested by sending one or more food photos for a single meal and verifying the bot's reply contains one combined calorie range and macro range, with no dependency on daily totals or check-ins.

**Acceptance Scenarios**:

1. **Given** a user in an active WhatsApp conversation with the bot, **When** they send a clear photo of a meal, **Then** the bot replies with an estimated calorie range and macro range (protein/carbs/fat) for that meal.
2. **Given** a user sends a photo that does not appear to contain food (e.g., a screenshot, a person, a blurry image), **When** the bot analyzes it, **Then** the bot replies explaining it could not identify food in the photo and does not add anything to the user's daily total.
3. **Given** a user sends two food photos close together in time (e.g., one per dish of the same meal), **When** the grouping window closes, **Then** the bot combines them into a single meal entry and replies once with the combined calorie/macro range.
4. **Given** a user sends a food photo well after their last one (outside the grouping window), **When** it is analyzed, **Then** it is logged as a new, separate meal entry.

---

### User Story 2 - Track a running daily total (Priority: P2)

As a user logs multiple meals throughout the day, the bot keeps a running total of estimated calories consumed so far that day.

**Why this priority**: This turns individual meal replies into a coherent daily picture, which is required before a meaningful end-of-day report can be sent. It depends on User Story 1 producing logged entries but does not require the end-of-day report to have value (a user could ask about it or see it referenced in meal replies).

**Independent Test**: Can be fully tested by logging several food photos in a day and verifying the running total reflects the sum of all logged estimates so far, correctly reset from the previous day.

**Acceptance Scenarios**:

1. **Given** a user has logged two meals earlier in the day, **When** they log a third meal, **Then** the system's running daily total reflects all three logged entries.
2. **Given** a new calendar day has started for the user, **When** they log their first meal of that day, **Then** the running daily total starts fresh and does not include prior days' entries.

---

### User Story 3 - Receive an end-of-day report (Priority: P3)

Once per day, the bot proactively sends the user a report covering total calories eaten, total protein/carbs/fat consumed, and a short generated feedback message that reacts to how their day's eating compares to their daily target.

**Why this priority**: This is the proactive, "push not pull" payoff of the feature and the most complex to get right (timing, spam avoidance, requiring a daily target to compare against, and generating feedback that stays within the coaching-safety rules). It builds directly on the running daily total from User Story 2.

**Independent Test**: Can be fully tested by advancing to the configured report time for a user with at least one logged meal that day and verifying exactly one report message is sent, containing total calories, macro totals, and a feedback message.

**Acceptance Scenarios**:

1. **Given** a user has logged one or more meals today, **When** the end-of-day report time is reached, **Then** the bot sends exactly one message containing total calories eaten, total protein/carbs/fat consumed, and feedback generated relative to those totals and the user's daily target.
2. **Given** a user logged no meals today, **When** the report time is reached, **Then** the bot still sends its one report, showing zero totals and feedback that encourages logging rather than criticizing the lack of data.
3. **Given** the end-of-day report has already been sent for the day, **When** the report time condition is evaluated again, **Then** the bot does not send a second report that day.
4. **Given** a user logs an additional meal after receiving their end-of-day report, **When** that late meal is analyzed, **Then** the bot still replies with a calorie/macro range for that meal but does not send a second report.
5. **Given** a user has no daily calorie target on file, **When** their first end-of-day report would otherwise fire, **Then** the bot instead asks the user for their daily calorie target and stores it for reuse on future days.
6. **Given** a user provides a daily calorie target below the safety floor (e.g., 1200/1500 kcal per coaching guidance), **When** the bot receives it, **Then** the bot rejects the value, explains why, and asks for a safe value instead.

---

### Edge Cases

- What happens when the photo doesn't appear to contain food or is too blurry/dark to analyze?
- What happens if a user sends a food photo after their end-of-day report has already gone out that day?
- How does the system determine "end of day" and the daily reset boundary for users in different time zones?
- What happens if the photo analysis produces a very wide or low-confidence range?
- What happens if a user never responds to the request to set their daily calorie target?
- What happens if a user sends photos for two different meals within the same grouping window (e.g., a snack right after lunch)?
- What tone should the generated feedback take when a user significantly exceeds their daily target, given the constitution's ban on medical advice and crash-diet pressure?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a food photo sent by a user via WhatsApp as valid input for calorie logging.
- **FR-002**: System MUST analyze each submitted food photo and reply to the user with an estimated calorie range (never a single exact number).
- **FR-003**: System MUST reply with an estimated macro range (protein, carbohydrates, fat) alongside the calorie range for each logged photo.
- **FR-004**: System MUST maintain a running total of estimated calories logged for the current calendar day, per user.
- **FR-005**: System MUST reset each user's running daily total at the start of a new calendar day in that user's local time zone.
- **FR-006**: System MUST send exactly one end-of-day report per user every calendar day, containing the user's total calories eaten, total protein/carbs/fat consumed, and a generated feedback message, regardless of whether the user logged any meals that day.
- **FR-007**: System MUST determine each user's daily calorie target by reusing a previously stored value if one exists, or by asking the user for it directly via chat if none exists yet, then storing the provided value for reuse on subsequent days.
- **FR-008**: On days with no logged meals (a case already covered by FR-006's "regardless of whether the user logged any meals"), the report's zero totals MUST be paired with feedback that encourages logging rather than criticizing the lack of data.
- **FR-009**: Every proactive message the bot sends, including the end-of-day report, MUST be phrased so that it can be answered, keeping the messaging channel open.
- **FR-010**: System MUST gracefully handle a photo that cannot be identified as food: inform the user and exclude it from the daily total.
- **FR-011**: System MUST persist each logged meal entry's result (calorie range, macro range, timestamp, associated user and day) as part of the user's food log history.
- **FR-012**: System MUST always present calorie and macro estimates and totals to users as ranges, never as false-precision exact figures.
- **FR-013**: System MUST NOT include medical advice or prescriptive diet instructions in calorie tracking replies or end-of-day reports.
- **FR-014**: System MUST combine multiple food photos submitted close together in time (within a short grouping window) into a single meal log entry, and reply once with the combined calorie and macro range for that meal; photos submitted outside the window start a new, separate entry.
- **FR-015**: System MUST reject any user-provided daily calorie target below the safety floor defined in coaching guidance (1200/1500 kcal), explain why, and ask for a safe value instead of storing it.
- **FR-016**: System MUST generate the end-of-day feedback message by comparing the user's total calories and macros eaten that day against their daily calorie target, in the bot's established coaching voice, without medical advice or crash-diet pressure regardless of how far over or under target the user is.

### Key Entities *(include if feature involves data)*

- **Food Log Entry**: The result of one or more food photos grouped into a single meal — timestamp, estimated calorie range, estimated macro ranges (protein/carbs/fat), and the user and calendar day it belongs to.
- **Daily Total**: The aggregated sum of a user's Food Log Entries for a given calendar day — total calories and total protein/carbs/fat — used to compute the end-of-day report.
- **Daily Calorie Target**: The user-provided goal used as the reference point for end-of-day feedback, collected once via chat when missing (subject to the safety floor) and reused on subsequent days.
- **End-of-Day Report**: A once-per-day, bot-initiated message containing the user's Daily Total (calories and macros) and a generated feedback message comparing that total to their Daily Calorie Target, sent every day regardless of activity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users receive a calorie and macro range reply for a submitted food photo within 60 seconds under normal conditions.
- **SC-002**: 100% of calorie and macro values shown to users are presented as ranges, never single exact numbers.
- **SC-003**: Users receive no more than one end-of-day report per calendar day.
- **SC-004**: At least 90% of clear, well-lit food photos submitted receive a usable calorie/macro range reply rather than an "unrecognized" response.
- **SC-005**: A user's running daily total, at any point in the day, always equals the sum of that day's individually logged estimates.
- **SC-006**: At least 80% of users who log a meal on a given day also open or respond to that day's end-of-day report.
- **SC-007**: 100% of user-provided daily calorie targets below the safety floor are rejected rather than stored.
- **SC-008**: 100% of generated feedback messages contain no medical advice or crash-diet language, regardless of how far the user's day was over or under target.

## Assumptions

- Users have already completed onboarding and are recognized as existing, opted-in WhatsApp contacts before using photo calorie tracking.
- Each user has a single, known time zone used to determine "end of day" and the daily reset boundary.
- The end-of-day report fires at one fixed local time for all users in the MVP (not user-configurable).
- Feedback is generated relative to the single Daily Calorie Target only; the MVP does not require separate protein/carbs/fat targets — macro totals are reported factually, and feedback may reference macro balance qualitatively without a numeric macro target.
- The photo-grouping window for combining multiple photos into one meal is a short, fixed duration (e.g., 10 minutes) for the MVP; there is no explicit "done with this meal" user signal.
- Correcting or editing a previously logged estimate (e.g., "that was actually two plates") is out of scope for this MVP.
- If a user never responds to the request to set their daily calorie target, the end-of-day report is deferred (not sent) until a target is provided.
- Photo calorie tracking is a core feature available to all users, not gated behind a paid subscription; the constitution's "subscription status checked before premium features" rule does not apply to this feature (confirmed during `/speckit.analyze`).
