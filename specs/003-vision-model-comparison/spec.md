# Feature Specification: Vision Model Abstraction & Comparison

**Feature Branch**: `003-vision-model-comparison`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "Abstract the vision/LLM model the bot uses to analyze food photos behind a swappable interface, so we can run different models against the same photos and compare their calorie, fat, protein, and carb estimates for research purposes — deciding which model to actually use in production based on accuracy."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare multiple models on the same photos (Priority: P1)

A team member researching analysis accuracy wants to run the same set of food photos through two or more candidate vision models and see each model's calorie and macro (protein/carbs/fat) estimates side by side, so they can judge which model performs best before deciding what powers the live bot.

**Why this priority**: This is the core research capability the feature exists for — without the ability to run several models against the same inputs and see their results together, there is nothing to compare and no basis for a production decision.

**Independent Test**: Can be fully tested by selecting two or more candidate models and a set of food photos, running the comparison, and verifying the output contains each model's calorie range and macro ranges for every photo, without touching the live bot.

**Acceptance Scenarios**:

1. **Given** a set of labeled food photos and two or more candidate models, **When** a team member runs a comparison, **Then** the output shows each model's calorie range and macro ranges (protein/carbs/fat) for every photo, grouped so results are easy to compare model-to-model.
2. **Given** one of the candidate models fails to return a usable result for a photo, **When** the comparison completes, **Then** that failure is recorded against that model for that photo, and the other models' results for the same photo are unaffected.
3. **Given** a comparison run is in progress, **When** a live user sends a food photo to the bot at the same time, **Then** the live user's request is analyzed and answered using the currently configured production model, unaffected by the comparison run.

---

### User Story 2 - Score model accuracy against known answers (Priority: P2)

A team member wants each candidate model's estimates scored against the existing labeled food-photo fixtures (known correct calorie/macro values), so the comparison produces an evidence-based accuracy ranking rather than just raw numbers to eyeball.

**Why this priority**: Side-by-side numbers alone (User Story 1) are useful but slow to interpret at scale; a per-model accuracy score turns the comparison into an actual basis for a production decision. It depends on User Story 1 producing per-model results but is separately verifiable.

**Independent Test**: Can be fully tested by running a comparison across the full labeled fixture set and verifying each participating model receives an aggregate accuracy score (e.g., average deviation from the known correct values) for calories and for each macro.

**Acceptance Scenarios**:

1. **Given** a comparison run across the labeled fixture set, **When** it completes, **Then** each candidate model has an aggregate accuracy score for calories and for each macro (protein/carbs/fat), computed against the fixtures' known correct values.
2. **Given** a fixture photo has no known correct value on file, **When** scoring is computed, **Then** that photo's results are still shown for reference but excluded from the accuracy score.
3. **Given** a model's response for a photo failed or could not be parsed, **When** scoring is computed, **Then** that photo is excluded from the model's accuracy score rather than counted as a zero or ignored silently without record.

---

### User Story 3 - Switch the live bot to a different model (Priority: P3)

Once research identifies a better-performing model, a team member wants to switch the model that powers the live bot's calorie/macro analysis for real users, without reworking how photos are received, meals are grouped, or replies are sent.

**Why this priority**: This is the payoff of the research — an accuracy comparison that can never be acted on has no value. It depends on the abstraction that User Stories 1 and 2 are built on, and is the deliberate, separate step that turns a research finding into a production change.

**Independent Test**: Can be fully tested by designating a different, already-compared model as the one used for live analysis, then sending a live food photo and verifying it is answered using that newly designated model, with meal grouping, replies, and daily totals behaving exactly as before.

**Acceptance Scenarios**:

1. **Given** a team member has decided on a new model based on comparison results, **When** they designate it as the live model, **Then** subsequent live user photos are analyzed using that model, with no other change in bot behavior.
2. **Given** the live model has just been switched, **When** the switch is reviewed later, **Then** it is possible to tell which model produced any given past live estimate.
3. **Given** a comparison run has completed, **When** no team member has taken the deliberate step to switch models, **Then** the live bot continues using the same model it was using before, unaffected by the comparison's existence.

---

### Edge Cases

- What happens when a candidate model returns a response that doesn't match the expected calorie/macro schema? (Recorded as a failure for that model/photo, excluded from accuracy scoring, and does not stop the comparison for other models or photos.)
- What happens when models disagree significantly on the same photo? (All results are still shown side by side — the feature surfaces disagreement rather than auto-resolving it.)
- What happens if a comparison run is interrupted partway through? (Results already produced remain available; the run is not silently treated as complete.)
- How is a live user protected from an in-progress or newly-added but not-yet-decided-on model? (Live analysis always uses only the currently designated production model; comparison candidates never serve live traffic implicitly.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST be able to analyze the same food photo using two or more different candidate models independently within a single comparison run.
- **FR-002**: System MUST capture, per candidate model per photo, an estimated calorie range and macro ranges (protein, carbohydrates, fat), using the same result structure already used for live bot estimates.
- **FR-003**: System MUST present comparison results grouped so that all candidate models' estimates for the same photo can be reviewed together.
- **FR-004**: System MUST score each candidate model's aggregate accuracy (e.g., deviation from known correct values) across the labeled food-photo fixtures, separately for calories and for each macro.
- **FR-005**: System MUST exclude a candidate model's failed or schema-invalid response for a given photo from that model's accuracy score, while still recording the failure for review.
- **FR-006**: System MUST NOT allow a comparison run to affect the model used to answer live users' food photos.
- **FR-007**: System MUST allow a team member to designate which single model is used for live user analysis, as a deliberate, explicit action separate from running a comparison.
- **FR-008**: System MUST make it possible to determine which model produced any given live user's past calorie/macro estimate.
- **FR-009**: System MUST continue serving live users with the previously designated model, unaffected, when a comparison run is created, in progress, or completed without a deliberate switch.
- **FR-010**: System MUST NOT include medical advice or prescriptive diet instructions in any comparison output, consistent with the bot's existing safety rules.

### Key Entities *(include if feature involves data)*

- **Model Candidate**: An analysis model available to be run against food photos, identified by name/version; may be used for research comparison, for live production serving, or both.
- **Comparison Run**: A single research execution of one or more Model Candidates against a set of food photos, producing one Model Result per candidate per photo.
- **Model Result**: One candidate model's outcome for one photo within a Comparison Run — calorie range, macro ranges, and success/failure status.
- **Accuracy Score**: An aggregated measure of how closely a Model Candidate's results matched known correct values across a set of photos with ground truth, per nutrient (calories, protein, carbs, fat).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A team member can compare at least two candidate models' calorie and macro estimates across the full labeled fixture set in a single research run.
- **SC-002**: Every candidate model in a comparison run receives an aggregate accuracy score against known correct values for calories and for each macro.
- **SC-003**: 100% of live users' bot behavior (reply content, timing, and accuracy presentation as ranges) is unaffected while a comparison run is in progress.
- **SC-004**: A team member can switch which model serves live users in a single deliberate action, without any change to meal-logging, grouping, or reply behavior.
- **SC-005**: For any live user estimate produced after this feature ships, a team member can identify which model produced it.
- **SC-006**: A failed or invalid response from one candidate model never prevents the comparison from completing for the remaining candidate models and photos.

## Assumptions

- This feature is for internal team/researcher use to inform a production decision; it does not add any new WhatsApp end-user-facing behavior.
- The existing labeled food-photo fixtures (used today for calorie-accuracy regression testing) serve as the ground truth for accuracy scoring; growing that fixture set further is out of scope for this feature.
- This is an offline research and decision tool, not live traffic-splitting: the live bot always serves all users from one single designated model at a time. Simultaneously running multiple models against real users (A/B testing in production) is out of scope for this feature.
- Comparison runs are triggered manually by a team member; no automatic or scheduled comparison is required for the MVP.
- Only vision/LLM-based analysis models are in scope for comparison; non-model approaches (e.g., manual nutrition database lookup) are out of scope.
- The constitution's requirement that users see ranges rather than exact numbers governs live bot replies; internal comparison output reviewed by the team is for research purposes and is not shown to end users.
