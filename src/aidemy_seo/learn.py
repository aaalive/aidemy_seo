"""Learn from your own channel: which title features go with more views.

Deliberately simple and honest: for each binary feature, compare the median views of videos
WITH it against videos WITHOUT it, and only call it a finding when both groups have at least
`min_group` videos. With a young channel most features will say "not enough data" - that is
the correct answer, not a bug.

Age-fair comparison: total `views` grow with age, so an old title style "wins" just by being
old. `views_per_day` (views / age in days, at least one day) and an age window
(`min_age`/`max_age`) compare videos fairly - see specs/schedule-and-learning.md. It reduces
the age bias but does not remove it: Shorts collect most views in their first days, so keep
the window narrow.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median

from .text import fold, hashtags, strip_hashtags, words
from .titles import DIRECT_ADDRESS, EMOTION_WORDS, QUESTION_WORDS

HELPS_AT = 1.2  # lift at or above this = "helps"
HURTS_AT = 0.8  # lift at or below this = "hurts"; in between = "no clear effect"

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
            verdict = (
                "helps" if lift and lift >= HELPS_AT else "hurts" if lift and lift <= HURTS_AT else "no clear effect"
            )
        else:
            my = median(yes) if yes else 0.0
            mn = median(no) if no else 0.0
            lift, verdict = None, f"not enough data (need {min_group} videos on each side)"
        out.append(Finding(name, len(yes), len(no), round(my, 1), round(mn, 1), lift, verdict))
    out.sort(key=lambda x: (x.lift is not None, x.lift or 0), reverse=True)
    return out


# ---------------------------------------------------------------- age-fair metrics
VIEWS_PER_DAY = "views_per_day"
SECONDS_PER_DAY = 24 * 60 * 60
MIN_AGE_FOR_RATE_DAYS = 1.0  # views_per_day divides by at least one day: a 2-hour-old Short is not "600 per day"
PUBLISH_FIELDS = ("went_public_at", "published_at", "publish_at")  # same order as schedule.best_slots
NO_PUBLISH_TIME = "no publish time"
AFTER_NOW = "published after now"
OUTSIDE_WINDOW = "outside the age window"


def parse_time(value: object) -> datetime | None:
    """ISO 8601 text -> timezone-aware datetime (no timezone = UTC); None when it can't be parsed."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def age_days(video: dict, now: datetime) -> float | None:
    """Days from the video's publish time to `now` (negative = published after now); None = unknown."""
    when = parse_time(next((video[f] for f in PUBLISH_FIELDS if video.get(f)), None))
    return None if when is None else (now - when).total_seconds() / SECONDS_PER_DAY


def check_age_window(min_age: float | None, max_age: float | None) -> None:
    for limit in (min_age, max_age):
        if limit is not None and not (math.isfinite(limit) and limit >= 0):
            raise ValueError(f"age limits must be a finite number of days >= 0, got {limit}")
    if min_age is not None and max_age is not None and min_age > max_age:
        raise ValueError(f"min age {min_age:g} days is larger than max age {max_age:g} days - no video can match")


def with_age_metrics(
    videos: list[dict], *, now: datetime, min_age: float | None = None, max_age: float | None = None
) -> tuple[list[dict], dict[str, int]]:
    """(kept videos, left-out count per reason). Kept videos are COPIES with `age_days` and - when
    they have `views` - `views_per_day` added; both limits are inclusive. The input is not changed."""
    check_age_window(min_age, max_age)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    kept: list[dict] = []
    left: dict[str, int] = {}
    for v in videos:
        age = age_days(v, now)
        if age is None:
            reason = NO_PUBLISH_TIME  # never a made-up age
        elif age < 0:
            reason = AFTER_NOW
        elif (min_age is not None and age < min_age) or (max_age is not None and age > max_age):
            reason = OUTSIDE_WINDOW
        else:
            row = dict(v, age_days=round(age, 2))
            row.pop(VIEWS_PER_DAY, None)  # always derived here, never read from the stats file
            if v.get("views") is not None:
                row[VIEWS_PER_DAY] = round(float(v["views"]) / max(age, MIN_AGE_FOR_RATE_DAYS), 2)
            kept.append(row)
            continue
        left[reason] = left.get(reason, 0) + 1
    return kept, left


def uses_age(metric: str, min_age: float | None = None, max_age: float | None = None) -> bool:
    return metric == VIEWS_PER_DAY or min_age is not None or max_age is not None


def videos_for_metric(
    videos: list[dict],
    *,
    metric: str = "views",
    now: datetime | None = None,
    min_age: float | None = None,
    max_age: float | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """The videos feature_lift should compare on `metric`, and how many were left out, by reason.
    Without views_per_day or an age window the videos pass through unchanged (today's behaviour)."""
    if uses_age(metric, min_age, max_age):
        rows, left = with_age_metrics(videos, now=now or datetime.now(timezone.utc), min_age=min_age, max_age=max_age)
    else:
        rows, left = list(videos), {}
    used = [r for r in rows if r.get(metric) is not None]
    if len(used) < len(rows):
        left[f"no {metric}"] = len(rows) - len(used)
    return used, left


def coverage_line(
    total: int,
    used: int,
    left_out: dict[str, int],
    *,
    metric: str,
    now: datetime | None = None,
    min_age: float | None = None,
    max_age: float | None = None,
    what: str = "videos",
) -> str:
    """One line saying what the comparison is based on - printed above every `learn` result."""
    ctx = [f"metric {metric}"]
    if min_age is not None and max_age is not None:
        ctx.append(f"age {min_age:g}-{max_age:g} days")
    elif min_age is not None:
        ctx.append(f"age >= {min_age:g} days")
    elif max_age is not None:
        ctx.append(f"age <= {max_age:g} days")
    if now is not None:
        ctx.append(f"ages at {now.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC")
    line = f"{used} of {total} {what} used ({', '.join(ctx)})"
    if left_out:
        line += "; left out: " + ", ".join(f"{n} {why}" for why, n in left_out.items())
    return line
