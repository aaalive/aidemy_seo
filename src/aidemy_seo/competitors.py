"""Learn from other channels in your area: posting times and title styles across many channels.

Public data has no "views after 24 h", and big channels have far more views than small ones.
To compare fairly, every video is scored against ITS OWN channel:

    ratio = views / median views of that channel's videos in the same window

so 2.0 means "twice as good as usual for that channel", whatever the channel size. Only
videos old enough to have settled and young enough to reflect today's algorithm are used
(default 7-180 days), Shorts only by default (<= 180 s). The same `best_slots()` and
`feature_lift()` as for your own channel then run on the pooled ratios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median

from .learn import feature_lift
from .schedule import best_hours, best_slots


@dataclass
class ChannelSummary:
    ref: str
    title: str
    subscribers: int
    videos_used: int
    median_views: float
    top_hours: list = field(default_factory=list)  # most used posting hours (local)


def _age_days(published_at: str, now: datetime) -> float | None:
    try:
        t = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return (now - t).total_seconds() / 86400


def normalise(
    channel_videos: dict[str, list],
    *,
    now: datetime | None = None,
    min_age_days: float = 7,
    max_age_days: float = 180,
    shorts_only: bool = True,
    max_short_s: int = 180,
    min_videos: int = 5,
) -> list[dict]:
    """{channel: [Video, ...]} -> pooled records {"title", "published_at", "ratio", "channel", "views"}."""
    now = now or datetime.now(timezone.utc)
    pooled = []
    for ch, vids in channel_videos.items():
        keep = []
        for v in vids:
            age = _age_days(v.published_at, now)
            if age is None or not (min_age_days <= age <= max_age_days):
                continue
            if shorts_only and not (0 < v.duration_s <= max_short_s):
                continue
            keep.append(v)
        if len(keep) < min_videos:
            continue
        med = median(v.views for v in keep) or 1
        pooled += [
            {
                "title": v.title,
                "published_at": v.published_at,
                "went_public_at": v.published_at,
                "kind": "short",
                "views": v.views,
                "ratio": round(v.views / med, 3),
                "channel": ch,
            }
            for v in keep
        ]
    return pooled


def analyse(
    channel_videos: dict[str, list],
    channel_info: dict[str, dict] | None = None,
    *,
    tz: str = "Europe/Berlin",
    now: datetime | None = None,
    **norm_kw,
) -> dict:
    pooled = normalise(channel_videos, now=now, **norm_kw)
    summaries = []
    for ch, info in (channel_info or {}).items():
        mine = [p for p in pooled if p["channel"] == ch]
        summaries.append(
            ChannelSummary(
                ch,
                (info or {}).get("title", ""),
                (info or {}).get("subscribers", 0),
                len(mine),
                median([p["views"] for p in mine]) if mine else 0.0,
                [h for h, _m, _n in sorted(best_hours(mine, tz=tz, metric="ratio"), key=lambda x: -x[2])[:3]],
            )
        )
    return {
        "videos": len(pooled),
        "channels": len({p["channel"] for p in pooled}),
        "slots": best_slots(pooled, tz=tz, metric="ratio", min_videos=5),
        "hours": best_hours(pooled, tz=tz, metric="ratio"),
        "title_styles": feature_lift(pooled, metric="ratio", min_group=10),
        "summaries": summaries,
    }
