# Feature Specification: Daily Calorie & Macro Total Tracking

**Feature Branch**: `002-daily-total-tracking`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "If the user requests the total of the meals' calories, send them the sum total logged so far, no matter what time of day they ask. At 00:00, start a new sum for the next day."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask for today's running total on demand (Priority: P1)

At any point during the day, a user can send a message asking for their total calories so far, and the bot replies with the sum of everything logged that day up to that moment — whether it's the middle of the night, right after breakfast, or last thing before bed.

**Why this priority**: This is the direct, user-facing behavior being requested — a user wants to be able to check in on their eating at any moment, not only see totals as a side effect of logging a meal. It's the reason this feature has value on its own, independent of any future proactive summary.

**Independent Test**: Can be fully tested by logging one or more meals, then sending a total-request message at an arbitrary time and verifying the reply states the correct sum of everything logged so far that calendar day.

**Acceptance Scenarios**:

1. **Given** a user has logged two meals earlier today, **When** they ask for their total, **Then** the bot replies with the combined calories and macros of both meals.
2. **Given** a user has logged zero meals today, **When** they ask for their total, **Then** the bot replies with a zero/no-meals-yet total rather than an error or silence.
3. **Given** a user asks for their total, **When** the bot computes the reply, **Then** it always reflects meals logged up to the moment of the request, regardless of what time of day the request is made.

---

### User Story 2 - Running total always matches logged meals (Priority: P2)

As a user logs multiple meals throughout the day, each on-demand total request reflects the sum of every meal logged so far that day — no missed entries, no double-counting.

**Why this priority**: An on-demand total (User Story 1) is only trustworthy if the underlying sum is always correct. This depends on User Story 1 existing as the delivery mechanism but is separately verifiable against the data itself.

**Independent Test**: Can be fully tested by logging several food photos in a day and verifying a total request after each one reflects the sum of all logged estimates so far that day.

**Acceptance Scenarios**:

1. **Given** a user has logged two meals, **When** they log a third and then ask for their total, **Then** the reply reflects all three logged entries.
2. **Given** a user's meal photo could not be identified as food, **When** they next ask for their total, **Then** that unidentified photo is excluded from the sum.
3. **Given** a user logs a photo that gets combined into an already-open meal (per the existing 10-minute grouping window), **When** they ask for their total, **Then** the combined meal counts once, not twice.

---

### User Story 3 - Daily total resets at 00:00 (Priority: P3)

Each user's running total starts fresh at 00:00 every day, so a request made just after midnight only reflects the new day's meals — yesterday's eating never carries over.

**Why this priority**: Without a correct reset boundary, "today's total" would silently include prior days and become meaningless. This is separately verifiable from User Stories 1 and 2, and lower priority because it only matters at the day boundary rather than on every request.

**Independent Test**: Can be fully tested by logging a meal before 00:00, requesting the total again after 00:00 has passed, and verifying the total resets to reflect only meals logged in the new day.

**Acceptance Scenarios**:

1. **Given** a user logged meals yesterday and none yet today, **When** they ask for their total after 00:00, **Then** the reply reflects only today's meals (zero, if none yet), not yesterday's.
2. **Given** it is a few minutes before 00:00, **When** a user logs a meal, **Then** that meal counts toward the day in progress, not the day about to start.

---

### Edge Cases

- What happens if a user logs a meal, then a later photo of the same meal (grouped within the existing logging window) is added — does the total double-count? (No; the total reflects one combined entry, consistent with how the meal itself is logged — see User Story 2, Acceptance Scenario 3.)
- What happens to a meal logged in the final minutes before 00:00? (Attributed to the calendar day in progress at the moment it is logged, per User Story 3, Acceptance Scenario 2.)
- What happens if a user asks for their total using different phrasing than expected, or in a different language? (Best-effort recognition of a total-request message in the user's language; if not recognized, the bot does not reply, consistent with this bot not being a general-purpose chat.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST recognize when an incoming user message is a request for their daily calorie/macro total, in the user's language.
- **FR-002**: When a user requests their total, System MUST reply with the sum of estimated calories and macros (protein, carbohydrates, fat) for every meal that user has logged so far in the current calendar day, regardless of what time of day the request is made.
- **FR-003**: System MUST maintain running totals of estimated calories, protein, carbohydrates, and fat for the current calendar day, per user.
- **FR-004**: The running daily total, at any point in time, MUST equal the sum of that user's individually logged meal entries for the current calendar day — no drift, no double-counting, no missed entries.
- **FR-005**: System MUST reset each user's running daily total at 00:00 every day, so a request made after 00:00 reflects only the new day's meals.
- **FR-006**: System MUST present daily total calories and macros as ranges, never as false-precision exact numbers, consistent with how individual meal estimates are presented.
- **FR-007**: System MUST exclude meal photos that could not be identified as food from the running daily total.
- **FR-008**: System MUST make the current running daily total available to be referenced by other bot features that report on a user's eating for the day.
- **FR-009**: A user message that does not match a recognized total-request phrasing MUST NOT receive a total reply — this feature is not a general-purpose chat.

### Key Entities *(include if feature involves data)*

- **Daily Total**: The aggregated sum of a user's logged meal entries for a given calendar day — total calories and total protein/carbs/fat — scoped to one user and one calendar day, reset at 00:00.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user asking for their total at any time of day receives a reply that always equals the sum of that day's individually logged estimates so far (100% accuracy, no drift).
- **SC-002**: 100% of users see their running daily total reset to zero at 00:00 each day.
- **SC-003**: A newly logged meal is reflected in the next total request within the same response cycle — no separate delay or follow-up needed.
- **SC-004**: Days with zero logged meals correctly show a zero total in reply to a request, rather than an error or missing value.

## Assumptions

- This feature builds on the existing photo-based meal logging capability (feature `001-photo-calorie-tracking`), which produces the individual logged meal entries this feature aggregates; it does not duplicate that logging pipeline.
- The daily reset boundary is a single fixed 00:00 clock time, not per-user local time zone — the system does not currently track each user's time zone. Per-user local-time reset is a reasonable future enhancement but out of scope here.
- Macro totals (protein/carbs/fat) are tracked in addition to calories, matching what is already reported per individual meal.
- Correcting or editing a previously logged meal entry after it has contributed to the daily total is out of scope for this feature.
- Surfacing the running total proactively (e.g., an end-of-day summary message) is a separate, future feature; this feature covers the on-demand, user-requested total, not a new proactive push message.
- Recognizing a total-request message is best-effort phrase/keyword matching in the user's language (Hebrew or English, per coach-persona), not open-ended natural-language understanding.
