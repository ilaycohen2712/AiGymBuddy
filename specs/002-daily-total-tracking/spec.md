# Feature Specification: Daily Calorie & Macro Total Tracking

**Feature Branch**: `002-daily-total-tracking`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "Track a running daily total of calories and macros (protein, carbs, fat) as a user logs meals throughout the day via WhatsApp, resetting at the start of each new calendar day in the user's local time zone."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See an up-to-date running total after each meal (Priority: P1)

As a user logs multiple meals throughout the day, the bot keeps a running total of estimated calories and macros (protein, carbs, fat) consumed so far that day, updated immediately as each new meal is logged.

**Why this priority**: This turns individual meal replies into a coherent daily picture. Without it, each meal reply is an isolated data point with no sense of progress toward the day's eating — the core value of tracking rather than one-off logging.

**Independent Test**: Can be fully tested by logging several food photos in a day and verifying the running total after each one reflects the sum of all logged estimates so far that day.

**Acceptance Scenarios**:

1. **Given** a user has logged two meals earlier in the day, **When** they log a third meal, **Then** the system's running daily total (calories and macros) reflects all three logged entries.
2. **Given** a user has logged zero meals today, **When** their running total is checked, **Then** it reflects zero calories and zero macros rather than an error or missing state.
3. **Given** a user's meal photo could not be identified as food, **When** the running total is next computed, **Then** that unidentified photo is excluded from the total.

---

### User Story 2 - Daily total resets on a new day (Priority: P2)

Each user's running total starts fresh at the beginning of every new calendar day, determined by that user's own local time zone, so yesterday's eating never bleeds into today's total.

**Why this priority**: Without a correct reset boundary, the running total becomes meaningless as a "today" figure and any feature built on top of it (e.g., a future daily summary) would be wrong. This depends on User Story 1 existing but is separately verifiable.

**Independent Test**: Can be fully tested by logging meals on one calendar day, advancing past midnight in the user's local time zone, and verifying the running total starts at zero for the new day while the prior day's logged entries remain retrievable in history.

**Acceptance Scenarios**:

1. **Given** a new calendar day has started for the user, **When** they log their first meal of that day, **Then** the running daily total starts fresh and does not include the prior day's entries.
2. **Given** two users in different time zones, **When** it becomes midnight in one user's time zone but not the other's, **Then** only the first user's running total resets.

---

### Edge Cases

- What happens to a meal logged in the final minutes before a user's local midnight — does it count toward the ending day or the new one? (Attributed to the calendar day in progress, in the user's local time zone, at the moment it is logged.)
- What happens if a user logs a meal, then a later photo of the same meal (grouped within the existing logging window) is added — does the total double-count? (No; the total reflects one combined entry, consistent with how the meal itself is logged.)
- What happens if a user's time zone is unknown or not yet established? (Out of scope for this feature — assumes time zone is already known from onboarding, per Assumptions.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain a running total of estimated calories logged for the current calendar day, per user.
- **FR-002**: System MUST maintain running totals of estimated protein, carbohydrates, and fat logged for the current calendar day, per user, alongside the calorie total.
- **FR-003**: System MUST update the running daily total immediately whenever a new meal entry is logged or an existing meal entry is combined with a new photo.
- **FR-004**: System MUST reset each user's running daily total at the start of a new calendar day, determined by that user's local time zone.
- **FR-005**: The running daily total, at any point in time, MUST equal the sum of that user's individually logged meal entries for the current calendar day — no drift, no double-counting, no missed entries.
- **FR-006**: System MUST present daily total calories and macros as ranges, never as false-precision exact numbers, consistent with how individual meal estimates are presented.
- **FR-007**: System MUST exclude meal photos that could not be identified as food from the running daily total.
- **FR-008**: System MUST make the current running daily total available to be referenced by other bot features that report on a user's eating for the day.

### Key Entities *(include if feature involves data)*

- **Daily Total**: The aggregated sum of a user's logged meal entries for a given calendar day — total calories and total protein/carbs/fat — scoped to one user and one calendar day, reset at that user's local-time day boundary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user's running daily total, at any point in the day, always equals the sum of that day's individually logged estimates (100% accuracy, no drift).
- **SC-002**: 100% of users see their running daily total reset to zero at the start of a new calendar day in their own local time zone.
- **SC-003**: A newly logged meal is reflected in the running daily total within the same response the user receives for that meal (no separate delay or follow-up needed).
- **SC-004**: Days with zero logged meals correctly show a zero total rather than an error or missing value.

## Assumptions

- This feature builds on the existing photo-based meal logging capability (feature `001-photo-calorie-tracking`), which produces the individual logged meal entries this feature aggregates; it does not duplicate that logging pipeline.
- Each user has a single, known time zone (established during onboarding) used to determine the daily reset boundary.
- Macro totals (protein/carbs/fat) are tracked in addition to calories, matching what is already reported per individual meal.
- Correcting or editing a previously logged meal entry after it has contributed to the daily total is out of scope for this feature.
- Surfacing the running total proactively (e.g., an end-of-day summary message) is a separate, future feature; this feature covers maintaining and making available the total itself, not a new proactive message.
