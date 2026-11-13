"""Best posting times from your own channel's real numbers.

Input: one record per video with when it went public and how it did after a fixed window
(``views_24h`` is the fairest comparison; ``views`` is used when nothing else exists).
Groups by weekday + hour (local time), ranks by median, and says how sure it is: a slot
with fewer than `min_videos` uploads is reported but marked "not enough data".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from zoneinfo import ZoneInfo

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class Slot:
    weekday: str
    hour: int
    videos: int
    median_views: float
    mean_views: float
    enough_data: bool

    @property
    def label(self) -> str:
        return f"{self.weekday} {self.hour:02d}:00"


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def best_slots(
    videos: list[dict],
    *,
    tz: str = "Europe/Berlin",
    metric: str = "views_24h",
    min_videos: int = 3,
    shorts_only: bool = True,
) -> list[Slot]:
    zone = ZoneInfo(tz)
    groups: dict[tuple[int, int], list[float]] = {}
    for v in videos:
        if shorts_only and "short" not in str(v.get("kind", "short")):
            continue
        when = _parse(v.get("went_public_at") or v.get("published_at") or v.get("publish_at") or "")
        val = v.get(metric)
        if val is None and metric != "views":
            val = v.get("views")
        if when is None or val is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        loc = when.astimezone(zone)
        groups.setdefault((loc.weekday(), loc.hour), []).append(float(val))
    slots = [
        Slot(
            WEEKDAYS[d], h, len(vals), round(median(vals), 1), round(sum(vals) / len(vals), 1), len(vals) >= min_videos
        )
        for (d, h), vals in groups.items()
    ]
    slots.sort(key=lambda s: (s.enough_data, s.median_views, s.videos), reverse=True)
    return slots


def best_hours(videos: list[dict], **kw) -> list[tuple[int, float, int]]:
    """Weekday-independent view: (hour, median, n), best first - useful with little data."""
    tz = kw.pop("tz", "Europe/Berlin")
    metric = kw.pop("metric", "views_24h")
    zone = ZoneInfo(tz)
    groups: dict[int, list[float]] = {}
    for v in videos:
        when = _parse(v.get("went_public_at") or v.get("published_at") or "")
        val = v.get(metric, v.get("views"))
        if when is None or val is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        groups.setdefault(when.astimezone(zone).hour, []).append(float(val))
    return sorted(
        ((h, round(median(v), 1), len(v)) for h, v in groups.items()), key=lambda x: (x[1], x[2]), reverse=True
    )
