"""Learn from your own channel: which title features go with more views.

Deliberately simple and honest: for each binary feature, compare the median views of videos
WITH it against videos WITHOUT it, and only call it a finding when both groups have at least
`min_group` videos. With a young channel most features will say "not enough data" - that is
the correct answer, not a bug.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from statistics import median

from .text import fold, hashtags, strip_hashtags, words
from .titles import DIRECT_ADDRESS, EMOTION_WORDS, QUESTION_WORDS

FEATURES: dict[str, Callable[[str], bool]] = {
    "question": lambda t: "?" in strip_hashtags(t) or bool(set(words(t)) & QUESTION_WORDS),
    "direct_address": lambda t: bool(set(words(t)) & DIRECT_ADDRESS),
    "emotion_word": lambda t: bool(set(words(t)) & EMOTION_WORDS) or "!" in t,
    "einfach_erklaert": lambda t: "einfach erklart" in fold(t),
    "musst_du_wissen": lambda t: "musst du wissen" in fold(t),
    "hashtags_in_title": lambda t: bool(hashtags(t)),
    "number": lambda t: any(c.isdigit() for c in strip_hashtags(t)),
    "short_under_50": lambda t: len(strip_hashtags(t)) < 50,
}


@dataclass
class Finding:
    feature: str
    with_n: int
    without_n: int
    with_median: float
    without_median: float
    lift: float | None  # with / without, None when not enough data
    verdict: str


def feature_lift(videos: list[dict], *, metric: str = "views", min_group: int = 5) -> list[Finding]:
    rows = [(str(v.get("title", "")), float(v[metric])) for v in videos if v.get(metric) is not None]
    out = []
    for name, f in FEATURES.items():
        yes = [m for t, m in rows if f(t)]
        no = [m for t, m in rows if not f(t)]
        if len(yes) >= min_group and len(no) >= min_group:
            my, mn = median(yes), median(no)
            lift = round(my / mn, 2) if mn > 0 else None
            verdict = "helps" if lift and lift >= 1.2 else "hurts" if lift and lift <= 0.8 else "no clear effect"
        else:
            my = median(yes) if yes else 0.0
            mn = median(no) if no else 0.0
            lift, verdict = None, f"not enough data (need {min_group} videos on each side)"
        out.append(Finding(name, len(yes), len(no), round(my, 1), round(mn, 1), lift, verdict))
    out.sort(key=lambda x: (x.lift is not None, x.lift or 0), reverse=True)
    return out
