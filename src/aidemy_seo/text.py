"""Small text helpers shared by every module (German-first, works for any Latin-script language)."""

from __future__ import annotations

import re
import unicodedata

_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "Ä": "a", "Ö": "o", "Ü": "u"})

STOPWORDS = {
    # German
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einer",
    "eines",
    "einem",
    "einen",
    "und",
    "oder",
    "aber",
    "von",
    "vom",
    "zu",
    "zum",
    "zur",
    "im",
    "in",
    "am",
    "an",
    "auf",
    "aus",
    "bei",
    "mit",
    "nach",
    "für",
    "fur",
    "über",
    "uber",
    "unter",
    "durch",
    "ist",
    "sind",
    "wie",
    "was",
    "wer",
    "warum",
    "du",
    "dein",
    "deine",
    "dich",
    "dir",
    "es",
    "sie",
    "er",
    "wir",
    "ihr",
    "nicht",
    "auch",
    "so",
    "u",
    "a",
    "klasse",
    "kl",
    # English
    "the",
    "and",
    "or",
    "of",
    "to",
    "on",
    "for",
    "with",
    "is",
    "are",
    "how",
    "what",
    "why",
    "you",
    "your",
}

HASHTAG_RE = re.compile(r"(?<![\w/&?=])#[\wäöüÄÖÜß]+")
URL_RE = re.compile(r"https?://\S+")


def fold(text: str) -> str:
    """Lower-case, umlauts folded (ä->a, ß->ss), accents removed."""
    t = unicodedata.normalize("NFKD", (text or "").translate(_FOLD).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def content_words(text: str, min_len: int = 3) -> list[str]:
    return [w for w in words(text) if len(w) >= min_len and w not in STOPWORDS]


def stems(text: str, n: int = 6) -> set[str]:
    """Crude prefix stems - enough to match 'Sinnestäuschung' with 'Sinnestäuschungen'."""
    return {w[:n] for w in content_words(text, 4)}


def strip_hashtags(text: str) -> str:
    return re.sub(r"\s{2,}", " ", HASHTAG_RE.sub("", text or "")).strip()


def hashtags(text: str) -> list[str]:
    return HASHTAG_RE.findall(text or "")
