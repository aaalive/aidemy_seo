"""Keyword research: which words people really search for on YouTube.

Free source, no API key and no Data API quota: YouTube's own search-autocomplete endpoint
(``suggestqueries.google.com`` with ``ds=yt``). For a phrase it returns up to ~10 real
search completions. How many of them START with the phrase is a usable demand signal:
niche curriculum words get 0-2, everyday search terms 8-10.

Every network call goes through a ``fetch`` callable, so tests and offline runs inject
recorded responses, and a failed lookup is reported as -1 ("unknown"), never 0.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .text import fold, stems

AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"

# fetch(url, params) -> parsed JSON (or raises)
Fetch = Callable[[str, dict], object]

GENERIC_WORDS = {
    "nutzen", "risiken", "bedeutung", "grundlagen", "merkmale", "moglichkeiten", "formen", "arten",
    "beispiele", "einfuhrung", "uberblick", "vergleich", "ursachen", "folgen", "aufbau", "funktion",
    "entwicklung", "probleme", "chancen", "gefahren", "eigenschaften", "methoden", "regeln", "begriffe",
    "definition", "bedingungen", "aufgaben", "ubungen", "wirklichkeit", "material", "arbeitsblatt",
}


def requests_fetch(url: str, params: dict, timeout: float = 3.0) -> object:
    import requests  # optional dependency: pip install aidemy-seo[http]
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return json.loads(r.text)


@dataclass
class Autocomplete:
    """YouTube autocomplete with an in-memory cache."""
    fetch: Fetch = requests_fetch
    lang: str = "de"
    region: str = "DE"
    _cache: dict = field(default_factory=dict)

    def suggestions(self, phrase: str) -> Optional[list[str]]:
        key = (fold(phrase).strip(), self.lang, self.region)
        if key in self._cache:
            return self._cache[key]
        try:
            data = self.fetch(AUTOCOMPLETE_URL, {"client": "firefox", "ds": "yt", "hl": self.lang,
                                                 "gl": self.region, "q": phrase})
        except Exception:  # noqa: BLE001 - offline / blocked: unknown, not zero
            return None
        sugg = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else None
        if sugg is not None:
            sugg = [str(s) for s in sugg]
            self._cache[key] = sugg
        return sugg

    def demand(self, phrase: str) -> int:
        """0-10: suggestions that start with the phrase. -1 = lookup failed."""
        sugg = self.suggestions(phrase)
        if sugg is None:
            return -1
        p = fold(phrase).strip()
        return sum(1 for s in sugg if fold(s).strip().startswith(p))

    def related(self, phrase: str, limit: int = 10) -> list[str]:
        """Real search phrasings that contain the phrase's own words (drift filtered out)."""
        sugg = self.suggestions(phrase) or []
        own = stems(phrase) or {fold(phrase)[:6]}
        out = [s for s in sugg if stems(s) & own and fold(s) != fold(phrase)]
        return out[:limit]


@dataclass
class Keyword:
    phrase: str
    demand: int            # 0-10, -1 unknown
    main: bool             # named in the topic itself / its short name
    score: float = 0.0


_SPLIT = re.compile(r"\s*(?:,|;|:|–|—|\s-\s|\(|\)|/|\bsowie\b)\s*")


def candidates(topic: str, *, short_name: str = "", key_terms: Iterable[str] = (),
               max_words: int = 3) -> list[tuple[str, bool]]:
    """Keyword candidates for a lesson, ``(phrase, is_main)``.

    Only words that belong to the lesson: a candidate's stems must all appear in the topic or
    its short name, so a popular side term ("Sachverhalt") never leads a title. "A und B C"
    names that share a head noun ("Grüne und Rote Gentechnik") give "A C", "B C" and the head
    "C" ("Gentechnik"), never the bare adjective "A" ("Grüne")."""
    topic = re.sub(r"\s+u\.\s*a\.?\s*$|…$", "", (topic or "").strip())
    central = stems(topic) | stems(short_name)
    raw: list[tuple[str, bool]] = []
    main_clause = _SPLIT.split(topic)[0].strip() if topic else ""
    for part in (main_clause, short_name):
        if not part:
            continue
        raw.append((part, True))
        pieces = [x for x in re.split(r"\s+(?:&|und|and)\s+", part) if x]
        if len(pieces) >= 2 and len(pieces[-1].split()) == 2 and all(len(x.split()) == 1 for x in pieces[:-1]):
            head = pieces[-1].split()[-1]
            pieces = [f"{x} {head}" for x in pieces[:-1]] + [pieces[-1]]
            if len(head) >= 6:
                raw.append((head, True))
        raw += [(x, True) for x in pieces]
    raw += [(x, False) for x in _SPLIT.split(topic)[1:]]
    raw += [(str(t), False) for t in key_terms if t]
    out, seen = [], set()
    for phrase, main in raw:
        phrase = re.sub(r"[®™]", "", " ".join(phrase.split())).strip(" .,-–")
        ws = phrase.split()
        if not phrase or len(phrase) < 4 or len(phrase) > 32 or len(ws) > max_words:
            continue
        if not re.fullmatch(r"[\wäöüÄÖÜß\- ]+", phrase):
            continue
        if len(ws) == 1 and fold(phrase) in GENERIC_WORDS:
            continue
        if fold(ws[-1]) in ("und", "oder", "der", "die", "das", "von", "zur", "zum"):
            continue
        s = stems(phrase)
        if not s or not s <= central:
            continue
        if fold(phrase) in seen:
            continue
        seen.add(fold(phrase))
        out.append((phrase, main))
    return out


def rank(cands: list[tuple[str, bool]], demand: Callable[[str], int], *, main_bonus: float = 3.0) -> list[Keyword]:
    """Score = search demand (+ bonus for the lesson's main topic). Unknown demand sorts last."""
    out = []
    for phrase, main in cands:
        d = demand(phrase)
        score = (d + (main_bonus if main else 0.0)) if d >= 0 else -1.0
        out.append(Keyword(phrase, d, main, score))
    out.sort(key=lambda k: (k.score, -len(k.phrase)), reverse=True)
    return out


def best_title_keyword(ranked: list[Keyword], *, pair_min_demand: int = 3) -> str:
    """The top keyword, plus the runner-up as "A & B" when both are searched and distinct.
    "" when no lookup succeeded (caller keeps its own default)."""
    known = [k for k in ranked if k.demand >= 0]
    if not known or known[0].demand <= 0:
        return ""
    best = known[0]
    for k in known[1:]:
        if k.demand >= pair_min_demand and not (stems(k.phrase) & stems(best.phrase)):
            return f"{best.phrase} & {k.phrase}"
    return best.phrase
