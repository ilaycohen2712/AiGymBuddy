from __future__ import annotations

# Best-effort phrase/keyword recognition (Hebrew + English), not clinical
# detection — matches spec 004-chat-responsiveness's stated quality bar
# ("reasonably direct phrasings," same as daily_total.py's matcher) and
# coach-persona skill's two escalation categories. Checked before the
# supported-question matcher (research.md #4) so a safety signal always
# wins over a coincidental keyword overlap.

_MEDICAL_SIGNAL_PHRASES = (
    "chest pain",
    "can't breathe",
    "cant breathe",
    "difficulty breathing",
    "severe pain",
    "dizzy",
    "dizziness",
    "fainted",
    "i fainted",
    "i'm injured",
    "im injured",
    "injured my",
    "hurt my",
    "sprained",
    "broke my",
    # Broader natural phrasings a real user would plausibly send, beyond the
    # narrower set above (coach-simulator finding: "my knee has been killing
    # me" and similar direct pain complaints were missed) — deliberately
    # multi-word so as not to false-positive on unrelated fitness talk like
    # "no pain no gain" (a bare "pain" alone is NOT in this list).
    "killing me",
    "been hurting",
    "really hurts",
    "hurts a lot",
    "keeps hurting",
    "so much pain",
    "a lot of pain",
    "can't walk",
    "cant walk",
    "can't move my",
    "cant move my",
    "כאב בחזה",
    "כאב חזק בחזה",
    "קשה לי לנשום",
    "סחרחורת",
    "התעלפתי",
    "נפצעתי",
    "כואב לי מאוד",
    "כאבים חזקים",
    "לא מצליח ללכת",
    "לא מצליחה ללכת",
)

_DISORDERED_EATING_SIGNAL_PHRASES = (
    "purge",
    "purging",
    "throw up after eating",
    "throwing up after eating",
    "make myself vomit",
    "making myself throw up",
    "starve myself",
    "starving myself",
    "haven't eaten in days",
    "havent eaten in days",
    "haven't eaten anything in",
    "eating disorder",
    "under 800 calories",
    "under 1000 calories",
    # Broader phrasings for extreme restriction (coach-simulator finding:
    # "I've barely eaten anything the last three days" was missed) — kept to
    # restriction-specific wording, not generic weight-loss talk, so as not
    # to false-positive on an ordinary "trying to eat less" message.
    "barely eaten",
    "barely eating",
    "hardly eaten",
    "hardly eating",
    "haven't been eating",
    "havent been eating",
    "not eating much",
    "skipping meals",
    "מקיא אחרי",
    "מקיאה אחרי",
    "מרעיב את עצמי",
    "מרעיבה את עצמי",
    "לא אכלתי כבר ימים",
    "בקושי אכלתי",
    "כמעט ולא אכלתי",
)

MEDICAL_ESCALATION_REPLY = (
    "That sounds like it could be a medical symptom, not something I can help "
    "with here — please reach out to a doctor or medical professional. I'll be "
    "here for your food logging whenever you're ready."
)

DISORDERED_EATING_ESCALATION_REPLY = (
    "Thank you for trusting me with that. This sounds like it might need more "
    "support than I can give — please consider reaching out to a doctor or a "
    "professional who specializes in this. I care about you, not just the numbers."
)


def check_safety_signal(text: str) -> str | None:
    """Returns the fixed escalation reply for the matched category, or None
    if `text` doesn't match either (spec 004-chat-responsiveness FR-005).
    Medical is checked before disordered-eating only because that's the
    fixed iteration order below — the two phrase sets are not expected to
    overlap in practice."""
    lowered = text.strip().lower()
    if any(phrase in lowered for phrase in _MEDICAL_SIGNAL_PHRASES):
        return MEDICAL_ESCALATION_REPLY
    if any(phrase in lowered for phrase in _DISORDERED_EATING_SIGNAL_PHRASES):
        return DISORDERED_EATING_ESCALATION_REPLY
    return None
