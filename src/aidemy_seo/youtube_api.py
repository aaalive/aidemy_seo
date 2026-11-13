"""Minimal YouTube Data API v3 client (API key only - read-only public data).

Used to look at what already ranks for a keyword: the top videos of the big channels.
Quota: search.list = 100 units, videos.list = 1 unit per 50 ids (default 10,000/day), so one
`top_videos()` call costs ~101 units. Get a key in Google Cloud Console -> APIs & Services
-> Credentials, then `export YOUTUBE_API_KEY=...`. Never commit the key.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

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
    def __init__(self, api_key: Optional[str] = None, fetch: Optional[Callable[[str, dict], object]] = None):
        self.key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
        if fetch is None:
            from .keywords import requests_fetch
            fetch = requests_fetch
        self.fetch = fetch

    def _get(self, path: str, **params) -> dict:
        if not self.key:
            raise RuntimeError("no YouTube API key - set YOUTUBE_API_KEY (read-only key is enough)")
        return self.fetch(f"{API}/{path}", {**params, "key": self.key})

    def top_videos(self, query: str, *, region: str = "DE", lang: str = "de", n: int = 25,
                   shorts: bool = False, order: str = "relevance") -> list[Video]:
        res = self._get("search", part="id", q=query, type="video", maxResults=min(n, 50), order=order,
                        regionCode=region, relevanceLanguage=lang,
                        **({"videoDuration": "short"} if shorts else {}))
        ids = [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]
        return self.videos(ids)

    def videos(self, ids: list[str]) -> list[Video]:
        out = []
        for i in range(0, len(ids), 50):
            res = self._get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
            for it in res.get("items", []):
                sn, st = it.get("snippet", {}), it.get("statistics", {})
                out.append(Video(it["id"], sn.get("title", ""), sn.get("channelTitle", ""),
                                 sn.get("publishedAt", ""), int(st.get("viewCount", 0) or 0),
                                 int(st.get("likeCount", 0) or 0), int(st.get("commentCount", 0) or 0),
                                 _duration(it.get("contentDetails", {}).get("duration", "")),
                                 sn.get("tags", []) or [], sn.get("description", "")))
        return out
