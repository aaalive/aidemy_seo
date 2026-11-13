"""Other-channel analysis. Fake API responses in the real YouTube Data API v3 shape; no network."""

import json
from datetime import datetime, timedelta, timezone

from aidemy_seo.cli import main
from aidemy_seo.competitors import analyse, normalise
from aidemy_seo.youtube_api import Video, YouTubeAPI, _channel_lookup_params

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def v(i, title, views, days_ago, hour_utc=17, dur=45):
    t = (NOW - timedelta(days=days_ago)).replace(hour=hour_utc, minute=0)
    return Video(f"v{i}", title, "C", t.strftime("%Y-%m-%dT%H:%M:%SZ"), views, 0, 0, dur, [])


def test_ratio_makes_big_and_small_channels_comparable():
    big = [v(i, f"Big {i}", 100_000, 10 + i) for i in range(5)] + [v(9, "Big hit?", 300_000, 20)]
    small = [v(20 + i, f"Small {i}", 100, 10 + i) for i in range(5)] + [v(29, "Small hit?", 300, 20)]
    pooled = normalise({"big": big, "small": small}, now=NOW)
    hits = [p for p in pooled if "hit" in p["title"]]
    assert {p["ratio"] for p in hits} == {3.0}  # same relative success, whatever the size


def test_filters_age_long_videos_and_tiny_channels():
    vids = [v(i, f"T{i}", 100, 30) for i in range(5)] + [
        v(10, "too new", 999, 2),
        v(11, "too old", 999, 400),
        v(12, "long video", 999, 30, dur=900),
    ]
    pooled = normalise({"c": vids, "tiny": [v(50, "x", 1, 30)]}, now=NOW)
    titles = {p["title"] for p in pooled}
    assert "too new" not in titles and "too old" not in titles and "long video" not in titles
    assert all(p["channel"] == "c" for p in pooled)  # a channel with < 5 usable Shorts is skipped


def test_question_titles_win_across_channels_and_best_hour_found():
    chans = {}
    for c in range(3):
        vids = [v(c * 100 + i, f"Was ist Thema {i}?", 300, 10 + i, hour_utc=17) for i in range(6)]
        vids += [v(c * 100 + 50 + i, f"Thema {i} Merksatz", 100, 10 + i, hour_utc=7) for i in range(6)]
        chans[f"ch{c}"] = vids
    res = analyse(chans, now=NOW)
    q = next(f for f in res["title_styles"] if f.feature == "question")
    assert q.verdict == "helps" and res["channels"] == 3
    assert res["hours"][0][0] == 18  # 17:00 UTC = 18:00 Berlin in November


def test_channel_lookup_params():
    assert _channel_lookup_params("@simpleclub") == {"forHandle": "@simpleclub"}
    assert _channel_lookup_params("simpleclub") == {"forHandle": "@simpleclub"}
    assert _channel_lookup_params("https://www.youtube.com/channel/UC1234567890123456789012") == {
        "id": "UC1234567890123456789012"
    }


def test_channel_videos_pages_through_uploads():
    pages = {
        None: {"items": [{"contentDetails": {"videoId": f"a{i}"}} for i in range(50)], "nextPageToken": "p2"},
        "p2": {"items": [{"contentDetails": {"videoId": f"b{i}"}} for i in range(10)]},
    }

    def fetch(url, params):
        if url.endswith("/channels"):
            return {
                "items": [
                    {
                        "id": "UCx",
                        "snippet": {"title": "Chan"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UUx"}},
                        "statistics": {"subscriberCount": "1000"},
                    }
                ]
            }
        if url.endswith("/playlistItems"):
            return pages[params.get("pageToken")]
        ids = params["id"].split(",")
        return {
            "items": [
                {
                    "id": i,
                    "snippet": {"title": i, "publishedAt": "2026-10-01T17:00:00Z"},
                    "statistics": {"viewCount": "5"},
                    "contentDetails": {"duration": "PT40S"},
                }
                for i in ids
            ]
        }

    ch, vids = YouTubeAPI(api_key="k", fetch=fetch).channel_videos("@chan", limit=200)
    assert ch["subscribers"] == 1000 and len(vids) == 60


def test_cli_channels_offline_from_saved_file(tmp_path, capsys):
    data = {
        "ch": {
            "info": {"title": "ch", "subscribers": 10},
            "videos": [vars(v(i, f"Was ist {i}?", 100 + i, 20 + i)) for i in range(6)],
        }
    }
    f = tmp_path / "raw.json"
    f.write_text(json.dumps(data))
    assert main(["channels", "--load", str(f), "--max-age-days", "100000"]) == 0
    out = capsys.readouterr().out
    assert "BEST POSTING SLOTS" in out and "TITLE STYLES" in out
