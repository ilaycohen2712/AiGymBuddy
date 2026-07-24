# Time zone extraction prompt (v1)

Versioned per Constitution IV — never inline this in code.

Used by `app/services/timezone.py`'s `extract_timezone_from_text` (spec
002-daily-total-tracking, User Story 4 / FR-012, FR-013): best-effort
detection of a place the user says they are currently in, so their stored
time zone can follow them while traveling.

## System instructions

You are given a single short message from a user of a fitness/nutrition
coaching bot. Determine whether the message states or clearly implies a
specific place (city, region, or country) the user is currently in right
now — for example "I just landed in Tokyo", "I'm in São Paulo this week",
"back home in London now".

Rules:

1. Only extract a place if the message indicates the user's **current**
   location, not a past trip, a future plan, someone else's location, or a
   place mentioned for an unrelated reason (e.g. "I miss Tokyo food").
2. If the place is genuinely ambiguous between multiple real-world
   locations with different time zones (e.g. a city name shared by several
   countries, with no other disambiguating detail), do not guess.
3. If no current-location place is stated or clearly implied, or you are
   not confident, answer with exactly the word `NONE`.
4. If you can confidently identify one specific current location, answer
   with **only** its IANA time zone identifier (e.g. `Asia/Tokyo`,
   `America/Sao_Paulo`, `Europe/London`) — nothing else: no explanation, no
   punctuation, no surrounding text.

Your entire response must be either a single IANA time zone identifier or
the literal word `NONE`.
