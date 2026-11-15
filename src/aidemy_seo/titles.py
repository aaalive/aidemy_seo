"""Title scoring and optimisation.

`score_title()` is an explainable checklist modelled on what YouTube-SEO tools check (vidIQ,
TubeBuddy): length, keyword up front, a hook (question / direct address / emotion), a clear
topic, no label-like listing title, hashtags. It is NOT vidIQ's score - their keyword
database is not public. Calibrate it against the real scores you see (`calibrate()`), and
learn from your own channel's views with `aidemy_seo.learn`.

`optimize_title()` builds candidates from honest templates around the best keyword and
returns them ranked. Templates never claim a fact the video does not contain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import fold, hashtags, strip_hashtags, words

EMOTION_WORDS = {
    "endlich",
    "einfach",
    "wirklich",
    "geheimnis",
    "fehler",
    "irrtum",
    "trick",
    "unglaublich",
    "überraschend",
    "uberraschend",
    "wichtig",
    "sofort",
    "schnell",
    "verstehen",
    "verstanden",
    "musst",
    "wissen",
    "klar",
    "achtung",
    "falle",
    "mythos",
    "wahrheit",
    "simple",
    "easy",
    "secret",
    "mistake",
    "finally",
    "really",
}
DIRECT_ADDRESS = {"du", "dir", "dich", "dein", "deine", "deinen", "you", "your"}
QUESTION_WORDS = {
    "warum",
    "wieso",
    "weshalb",
    "wie",
    "was",
    "wer",
    "welche",
    "welcher",
    "kannst",
    "schaffst",
    "weisst",
    "why",
    "how",
    "what",
    "can",
}
LISTING_RE = re.compile(
    r"\b(Kl\.?\s*\d+|Klasse\s*\d+\s*:|Arbeitsblatt|Lernzettel|Set|Paket|Material|"
    r"Klassenarbeit(?:en)?|PDF)\b",
    re.I,
)

MAX_TITLE_LEN = 66  # YouTube shows about this much of a Short's title

TEMPLATES = (
    "{x} – kannst du es erklären?",
    "{x} einfach erklärt – das musst du wissen!",
    "{x} einfach erklärt – endlich verstanden!",
    "Warum {x}? Einfach erklärt",
    "{x}: Das musst du wissen!",
    "{x} – endlich verstanden!",
)


@dataclass
class TitleScore:
    title: str
    total: float  # 0-100
    checks: dict = field(default_factory=dict)  # name -> (passed, weight, note)

    @property
    def issues(self) -> list[str]:
        return [f"{k}: {v[2]}" for k, v in self.checks.items() if not v[0]]


def score_title(title: str, keyword: str = "", *, max_len: int = MAX_TITLE_LEN, ideal: tuple = (35, 60)) -> TitleScore:
    """Explainable 0-100 score. `keyword` = the phrase people search for (optional)."""
    core = strip_hashtags(title)
    ws = set(words(core))
    n = len(title)
    checks: dict = {}

    def add(name, ok, weight, note):
        checks[name] = (bool(ok), weight, note)

    add(
        "length",
        ideal[0] <= len(core) <= ideal[1] and n <= max_len,
        15,
        f"{len(core)} characters without hashtags (aim {ideal[0]}-{ideal[1]}, total <= {max_len})",
    )
    if keyword:
        first = fold(keyword.split(" & ")[0])
        add("keyword_first", fold(core).startswith(first), 20, f"start with the searched keyword '{keyword}'")
        add("keyword_present", all(w in ws for w in words(keyword.split(" & ")[0])), 10, f"contains '{keyword}'")
    add(
        "hook",
        "?" in core or ws & QUESTION_WORDS or ws & DIRECT_ADDRESS,
        15,
        "a question or direct address ('du', 'kannst du ...?')",
    )
    add("emotion", ws & EMOTION_WORDS or "!" in core, 10, "an honest emotional word ('endlich', 'einfach', '!')")
    add("not_a_listing", not LISTING_RE.search(core), 15, "reads like a hook, not a shop label ('Kl. 6: ... Set')")
    tags = hashtags(title)
    add("hashtags", 1 <= len(tags) <= 3, 5, "1-3 hashtags (subject, grade)")
    add("no_caps_shouting", not re.search(r"\b[A-ZÄÖÜ]{5,}\b", core), 5, "no ALL-CAPS words")
    add("readable", len(core.split()) <= 10, 5, "10 words or fewer")
    total_w = sum(w for _ok, w, _n in checks.values())
    got = sum(w for ok, w, _n in checks.values() if ok)
    return TitleScore(title, round(100.0 * got / total_w, 1), checks)


def title_tags(subject: str = "", grade: str = "") -> list[str]:
    """The hashtags every title ends with: #Fach and #KlasseN ("Klasse 10" -> "#Klasse10")."""
    tags = []
    if subject:
        tags.append("#" + re.sub(r"[^\wäöüÄÖÜß]", "", subject))
    m = re.search(r"\d+", grade or "")
    if m:
        tags.append(f"#Klasse{m.group(0)}")
    return tags


def build_title(keyword: str, template: str, tags: list[str], max_len: int = MAX_TITLE_LEN) -> str:
    hook = template.format(x=keyword)
    while tags and len(hook) + 1 + len(" ".join(tags)) > max_len:
        tags = tags[:-1]
    return (hook + (" " + " ".join(tags) if tags else "")).strip()


def optimize_title(
    keyword: str,
    *,
    subject: str = "",
    grade: str = "",
    max_len: int = MAX_TITLE_LEN,
    templates: tuple = TEMPLATES,
    weights: dict | None = None,
) -> list[TitleScore]:
    """Ranked title candidates for `keyword`. `weights` (template -> bonus 0-1) comes from
    calibration / learning; without it the checklist alone ranks them."""
    tags = title_tags(subject, grade)
    out = []
    for x in dict.fromkeys([keyword, keyword.split(" & ")[0]]):
        for tpl in templates:
            if ":" in x and "{x}:" in tpl:
                continue
            t = build_title(x, tpl, list(tags), max_len)
            if len(t) > max_len:
                continue
            s = score_title(t, keyword)
            kept_all = all(tag in t for tag in tags)
            s.checks["all_hashtags"] = (kept_all, 0, "subject and grade hashtags both fit")
            if not kept_all:
                s.total = round(s.total - 15.0, 1)  # a shorter template that keeps #Fach #KlasseN wins
            if weights:
                s.total = round(s.total + 10.0 * weights.get(tpl, 0.0), 1)
            s.checks["template"] = (True, 0, tpl)
            out.append(s)
    seen, ranked = set(), []
    for s in sorted(out, key=lambda s: s.total, reverse=True):
        if s.title not in seen:
            seen.add(s.title)
            ranked.append(s)
    return ranked


def calibrate(observed: list[tuple[str, float]]) -> dict:
    """Which title shapes score best with an external tool (e.g. vidIQ scores you saw).
    Returns {"by_shape": {shape: mean score}, "n": ...}. Shapes: question, must_know,
    einfach_erklaert, label, other."""

    def shape(t: str) -> str:
        c = fold(strip_hashtags(t))
        if "?" in c:
            return "question"
        if "einfach erklart" in c:
            return "einfach_erklaert"
        if "musst du wissen" in c:
            return "must_know"
        if not re.search(r"[!?]", c):
            return "label"
        return "other"

    groups: dict[str, list[float]] = {}
    for title, sc in observed:
        groups.setdefault(shape(title), []).append(float(sc))
    return {
        "by_shape": {k: round(sum(v) / len(v), 1) for k, v in sorted(groups.items())},
        "n": {k: len(v) for k, v in groups.items()},
    }
