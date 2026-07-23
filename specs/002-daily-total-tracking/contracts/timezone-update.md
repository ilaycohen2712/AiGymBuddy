# Contract: Time zone updates (location share or text place-mention)

Covers User Story 4 — keeping a user's stored time zone current as they travel.

## Trigger A: WhatsApp location share

`POST /webhook` — inbound message type `location` (latitude/longitude, optional name/address). New message type for this codebase — see research.md #7.

### Behavior

1. Resolve/create the user (existing `get_or_create_user_id`); dedupe by `wa_message_id` (existing convention).
2. Reverse-geocode the shared coordinates to an IANA time zone (`timezonefinder`, offline).
3. If a valid zone is found: update `users.time_zone`; reply with a short confirmation (e.g. "Got it — set your time zone based on your location."). This is a deliberate, explicit user action, so it gets an explicit confirmation, unlike the silent text-mention path below.
4. If reverse-geocoding fails to produce a valid zone (e.g. coordinates over open ocean): leave `users.time_zone` unchanged; reply with a brief message noting the location couldn't be used — never silently fail with no reply, consistent with this codebase's "never leave the user with silence" convention for recognized message types.
5. Record the message (existing convention).

## Trigger B: Text mentioning a place

`POST /webhook` — inbound message type `text`, processed independently of (and in addition to) the total-request check in daily-total-query.md — a single message could in principle do both.

### Behavior

1. Run the place-mention extraction prompt (`app/prompts/timezone_extraction.md`, Haiku-class model) against the message body.
2. If it returns a place mapped to a time zone, and that value passes `zoneinfo.available_timezones()` validation: update `users.time_zone`. No dedicated confirmation reply for this path — it rides along with whatever reply (if any) the message already produces (e.g. a total-request reply, or no reply at all if nothing else matched).
3. If it returns nothing, or an ambiguous/unrecognized place, or fails validation: leave `users.time_zone` unchanged. No error is surfaced to the user for this — an unrecognized place mention is not a user-facing failure (FR-013).

## Postconditions (both triggers)

- A change to `users.time_zone` only affects the reset boundary for meals logged *after* the change — it never rewrites which date bucket an already-logged meal's contribution landed in (FR-014; see data-model.md's "written once, at write time" design).
- An ambiguous or unrecognized signal never produces an incorrect time-zone value — the safe outcome is always "unchanged," never a guess (FR-013).
