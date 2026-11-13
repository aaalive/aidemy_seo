"""What the top videos for a keyword do: title patterns of the channels that already win.

Works on any list of (title, views) pairs - from `YouTubeAPI.top_videos()`, a CSV export,
or your own channel - so the analysis itself needs no network and is easy to test.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from .text import content_words, fold, hashtags, strip_hashtags, words
from .titles import DIRECT_ADDRESS, QUESTION_WORDS


@dataclass
class Patterns:
    n: int
    median_len: float
    share_question: float
    share_number: float
    share_direct_address: float
    share_keyword_first: float
    share_hashtag: float
    share_emoji: float
    top_words: list = field(default_factory=list)
    weighted_top_words: list = field(default_factory=list)   # weighted by views

    def summary(self) -> list[str]:
        p = lambda x: f"{round(100 * x)}%"  # noqa: E731
        return [f"{self.n} titles, median length {self.median_len:.0f} characters",
                f"questions {p(self.share_question)}, numbers {p(self.share_number)}, "
                f"'du/you' {p(self.share_direct_address)}, keyword first {p(self.share_keyword_first)}",
                f"hashtags in title {p(self.share_hashtag)}, emoji {p(self.share_emoji)}",
                "most used words: " + ", ".join(w for w, _ in self.top_words[:12]),
                "words in the most-viewed titles: " + ", ".join(w for w, _ in self.weighted_top_words[:12])]


def _has_emoji(t: str) -> bool:
    return any(ord(c) >= 0x1F300 or 0x2600 <= ord(c) <= 0x27BF for c in t)


def title_patterns(items: list[tuple[str, float]], keyword: str = "") -> Patterns:
    n = len(items) or 1
    kw = fold(keyword)
    words_count, weighted = Counter(), Counter()
    q = num = du = first = tag = emo = 0
    lens = []
    for title, views in items:
        core = strip_hashtags(title)
        ws = set(words(core))
        lens.append(len(core))
        q += "?" in core or bool(ws & QUESTION_WORDS)
        num += any(ch.isdigit() for ch in core)
        du += bool(ws & DIRECT_ADDRESS)
        first += bool(kw) and fold(core).startswith(kw)
        tag += bool(hashtags(title))
        emo += _has_emoji(title)
        cw = set(content_words(core))
        words_count.update(cw)
        for w in cw:
            weighted[w] += float(views or 0)
    return Patterns(len(items), median(lens) if lens else 0, q / n, num / n, du / n, first / n, tag / n, emo / n,
                    words_count.most_common(25), weighted.most_common(25))
