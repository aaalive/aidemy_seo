"""Minimal YouTube Data API v3 client (API key only - read-only public data).

Used to look at what already ranks for a keyword: the top videos of the big channels.
Quota: search.list = 100 units, videos.list = 1 unit per 50 ids (default 10,000/day), so one
`top_videos()` call costs ~101 units. Get a key in Google Cloud Console -> APIs & Services
-> Credentials, then `export YOUTUBE_API_KEY=...`. Never commit the key.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

API = "https://www.googleapis.com/youtube/v3"


@dataclass
class Video:
    video_id: str
    title: str
    channel: str
    published_at: str
    views: int
    likes: int
    comments: int
    duration_s: int
    tags: list
    description: str = ""


def _duration(iso: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


class YouTubeAPI:
    def __init__(self, api_key: str | None = None, fetch: Callable[[str, dict], object] | None = None):
        self.key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
        self.fetch = fetch  # None = live HTTP via keywords.requests_fetch, resolved at call time

    def _get(self, path: str, **params: Any) -> dict:
        if not self.key:
            raise RuntimeError("no YouTube API key - set YOUTUBE_API_KEY (read-only key is enough)")
        from . import keywords

        res = (self.fetch or keywords.requests_fetch)(f"{API}/{path}", {**params, "key": self.key})
        return res if isinstance(res, dict) else {}

    def top_videos(
        self,
        query: str,
        *,
        region: str = "DE",
        lang: str = "de",
        n: int = 25,
        shorts: bool = False,
        order: str = "relevance",
    ) -> list[Video]:
        res = self._get(
            "search",
            part="id",
            q=query,
            type="video",
            maxResults=min(n, 50),
            order=order,
            regionCode=region,
            relevanceLanguage=lang,
            **({"videoDuration": "short"} if shorts else {}),
        )
        ids = [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]
        return self.videos(ids)

    def videos(self, ids: list[str]) -> list[Video]:
        out = []
        for i in range(0, len(ids), 50):
            res = self._get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i : i + 50]))
            for it in res.get("items", []):
                sn, st = it.get("snippet", {}), it.get("statistics", {})
                out.append(
                    Video(
                        it["id"],
                        sn.get("title", ""),
                        sn.get("channelTitle", ""),
                        sn.get("publishedAt", ""),
                        int(st.get("viewCount", 0) or 0),
                        int(st.get("likeCount", 0) or 0),
                        int(st.get("commentCount", 0) or 0),
                        _duration(it.get("contentDetails", {}).get("duration", "")),
                        sn.get("tags", []) or [],
                        sn.get("description", ""),
                    )
                )
        return out

    def channel(self, ref: str) -> dict | None:
        """{'id', 'title', 'uploads', 'subscribers'} for a handle, channel id or URL. 1 unit."""
        res = self._get("channels", part="snippet,contentDetails,statistics", **_channel_lookup_params(ref))
        items = res.get("items") or []
        if not items:
            return None
        it = items[0]
        return {
            "id": it["id"],
            "title": it.get("snippet", {}).get("title", ""),
            "uploads": it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
            "subscribers": int(it.get("statistics", {}).get("subscriberCount", 0) or 0),
        }

    def channel_videos(self, ref: str, *, limit: int = 200) -> tuple[dict | None, list[Video]]:
        """The channel's latest `limit` uploads with full stats. ~1 unit per 50 videos (x2)."""
        ch = self.channel(ref)
        if not ch or not ch["uploads"]:
            return ch, []
        ids: list[str] = []
        token: str | None = None
        while len(ids) < limit:
            res = self._get(
                "playlistItems",
                part="contentDetails",
                playlistId=ch["uploads"],
                maxResults=50,
                **({"pageToken": token} if token else {}),
            )
            ids += [
                it["contentDetails"]["videoId"]
                for it in res.get("items", [])
                if it.get("contentDetails", {}).get("videoId")
            ]
            token = res.get("nextPageToken")
            if not token:
                break
        return ch, self.videos(ids[:limit])

    def find_channels(self, query: str, *, n: int = 10, region: str = "DE", lang: str = "de") -> list[dict]:
        """Channels that YouTube search returns for a topic (100 units)."""
        res = self._get(
            "search",
            part="snippet",
            q=query,
            type="channel",
            maxResults=min(n, 50),
            regionCode=region,
            relevanceLanguage=lang,
        )
        return [
            {"id": it["id"]["channelId"], "title": it.get("snippet", {}).get("channelTitle", "")}
            for it in res.get("items", [])
            if it.get("id", {}).get("channelId")
        ]


# ---------------------------------------------------------------- other channels (2026-11-13)
def _channel_lookup_params(ref: str) -> dict:
    """'@simpleclub' / 'simpleclub' -> forHandle, 'UC...' -> id, a channel URL -> either."""
    ref = (ref or "").strip().rstrip("/")
    if "youtube.com/" in ref:
        ref = ref.split("youtube.com/", 1)[1]
        ref = ref.split("channel/", 1)[1] if ref.startswith("channel/") else ref
    if ref.startswith("UC") and len(ref) == 24:
        return {"id": ref}
    return {"forHandle": ref if ref.startswith("@") else "@" + ref}
