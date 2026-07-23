from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from zoneinfo import available_timezones

import anthropic
import phonenumbers
from timezonefinder import TimezoneFinder

from app.config import settings

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "timezone_extraction.md"
_EXTRACTION_MODEL = "claude-haiku-4-5"

_client: anthropic.AsyncAnthropic | None = None
_client_lock = asyncio.Lock()

# Loads its coordinate-boundary data once at import time; cheap, synchronous,
# CPU-only lookups thereafter (no network, no API key — research.md #3).
_finder = TimezoneFinder()

# A representative single IANA zone per country region, used only as a
# starting default before a user ever shares their location or mentions a
# place (research.md #2). Deliberately not exhaustive — countries spanning
# multiple time zones (e.g. US, Russia, Australia) get one reasonable
# representative rather than none; anything unlisted falls back to UTC.
_REGION_DEFAULT_TIMEZONE: dict[str, str] = {
    "IL": "Asia/Jerusalem",
    "US": "America/New_York",
    "CA": "America/Toronto",
    "GB": "Europe/London",
    "IE": "Europe/Dublin",
    "FR": "Europe/Paris",
    "DE": "Europe/Berlin",
    "ES": "Europe/Madrid",
    "IT": "Europe/Rome",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "CH": "Europe/Zurich",
    "AT": "Europe/Vienna",
    "PT": "Europe/Lisbon",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "PL": "Europe/Warsaw",
    "GR": "Europe/Athens",
    "TR": "Europe/Istanbul",
    "RU": "Europe/Moscow",
    "UA": "Europe/Kyiv",
    "EG": "Africa/Cairo",
    "ZA": "Africa/Johannesburg",
    "AE": "Asia/Dubai",
    "SA": "Asia/Riyadh",
    "IN": "Asia/Kolkata",
    "PK": "Asia/Karachi",
    "CN": "Asia/Shanghai",
    "JP": "Asia/Tokyo",
    "KR": "Asia/Seoul",
    "SG": "Asia/Singapore",
    "TH": "Asia/Bangkok",
    "ID": "Asia/Jakarta",
    "PH": "Asia/Manila",
    "VN": "Asia/Ho_Chi_Minh",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
    "BR": "America/Sao_Paulo",
    "MX": "America/Mexico_City",
    "AR": "America/Argentina/Buenos_Aires",
}

DEFAULT_TIMEZONE = "UTC"


def derive_default_timezone(wa_phone: str) -> str:
    """Best-effort initial time zone from a WhatsApp phone number's country
    calling code, before onboarding (or User Story 4) ever establishes a real
    value. Falls back to UTC for an unparseable number or an unmapped region
    — never raises."""
    try:
        parsed = phonenumbers.parse(f"+{wa_phone}")
    except phonenumbers.NumberParseException:
        return DEFAULT_TIMEZONE

    region = phonenumbers.region_code_for_number(parsed)
    return _REGION_DEFAULT_TIMEZONE.get(region, DEFAULT_TIMEZONE)


def timezone_from_location(latitude: float, longitude: float) -> str | None:
    """Offline lat/lng → IANA time zone (spec 002-daily-total-tracking, User
    Story 4, FR-011). Ocean coordinates still resolve to a legitimate
    nautical `Etc/GMT+N` zone — only out-of-range coordinates (a malformed
    WhatsApp location payload) or a result that somehow doesn't validate as
    a real IANA name return None, so callers can leave the stored time zone
    unchanged (FR-013) rather than guess."""
    try:
        tz = _finder.timezone_at(lat=latitude, lng=longitude)
    except ValueError:
        return None
    if tz is None or tz not in available_timezones():
        return None
    return tz


async def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # re-check: another task may have won the race
                _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _load_prompt() -> str:
    return PROMPT_PATH.read_text()


async def extract_timezone_from_text(text: str) -> str | None:
    """Best-effort extraction of a place the user says they're currently in,
    mapped to an IANA time zone (spec 002-daily-total-tracking, User Story
    4, FR-012), via a small/cheap model — a simple text-classification task,
    distinct from the Sonnet-class vision model used for photo analysis
    (research.md #4). Returns None if no place is mentioned, it's ambiguous,
    or the model's answer doesn't validate as a real IANA zone (FR-013) —
    callers must leave the stored time zone unchanged in that case, never
    guess on top of a None."""
    client = await _get_client()
    response = await client.messages.create(
        model=_EXTRACTION_MODEL,
        max_tokens=64,
        system=_load_prompt(),
        messages=[{"role": "user", "content": text}],
    )
    reply = "".join(block.text for block in response.content if block.type == "text").strip()
    if reply == "NONE" or reply not in available_timezones():
        return None
    return reply
