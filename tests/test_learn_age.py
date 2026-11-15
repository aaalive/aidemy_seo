"""Age-fair learning (specs/schedule-and-learning.md): views_per_day, the age window and `now`.

Every test pins `now`, so results never change with the calendar."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aidemy_seo import feature_lift
from aidemy_seo.learn import (
    AFTER_NOW,
    NO_PUBLISH_TIME,
    OUTSIDE_WINDOW,
    parse_time,
    videos_for_metric,
    with_age_metrics,
)

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
CONFOUND = json.loads((FIX / "stats_age_confound.json").read_text(encoding="utf-8"))["videos"]


def aged(days: float, views: float | None = 100, **extra) -> dict:
    when = (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"kind": "short", "title": f"{days} days", "went_public_at": when, "views": views, **extra}


def test_views_per_day_uses_age_with_one_day_floor():
    ten_days = {"title": "A", "went_public_at": "2026-11-05T00:00:00Z", "views": 300}
    six_hours = {"title": "B", "went_public_at": "2026-11-14T18:00:00Z", "views": 50}
    # a views_per_day stored in the stats file is never trusted - it is always derived
    stale = {"title": "C", "published_at": "2026-11-05T00:00:00Z", "views": 300, "views_per_day": 999}
    stale_no_views = {"title": "D", "went_public_at": "2026-11-05T00:00:00Z", "views_per_day": 999}
    kept, left = with_age_metrics([ten_days, six_hours, stale, stale_no_views], now=NOW)
    assert left == {}
    assert kept[0]["age_days"] == 10.0 and kept[0]["views_per_day"] == 30.0
    assert kept[1]["age_days"] == 0.25 and kept[1]["views_per_day"] == 50.0  # not 200/day: one-day floor
    assert kept[2]["views_per_day"] == 30.0  # published_at is the second field read, like schedule
    assert "views_per_day" not in kept[3]  # no views -> no views_per_day, whatever the file says


def test_with_age_metrics_leaves_out_undatable_and_future_videos():
    kept, left = with_age_metrics(CONFOUND, now=NOW)
    ids = {v["video_id"] for v in kept}
    assert not ids & {"e_nodate", "e_baddate", "e_future"}  # never given a made-up age
    assert left == {NO_PUBLISH_TIME: 2, AFTER_NOW: 1}
    assert with_age_metrics([aged(-1 / 24)], now=NOW)[1] == {AFTER_NOW: 1}  # one hour in the future
    assert len(with_age_metrics([aged(0)], now=NOW)[0]) == 1  # published exactly at `now` is kept
    no_views = next(v for v in kept if v["video_id"] == "e_noviews")
    assert "views_per_day" not in no_views  # dated, but nothing to divide

    used, left = videos_for_metric(CONFOUND, metric="views_per_day", now=NOW)
    assert len(used) == 12 and "e_noviews" not in {v["video_id"] for v in used}
    assert left == {NO_PUBLISH_TIME: 2, AFTER_NOW: 1, "no views_per_day": 1}  # every one counted, by reason


def test_feature_lift_views_per_day_removes_age_advantage():
    # the age trap: on total views the OLD question titles look 2.4x better ...
    used, _ = videos_for_metric(CONFOUND, metric="views", now=NOW)
    raw = next(f for f in feature_lift(used, metric="views") if f.feature == "question")
    assert raw.verdict == "helps" and raw.lift == 2.37
    # ... per day of age they earn a third of what the new titles earn
    used, _ = videos_for_metric(CONFOUND, metric="views_per_day", now=NOW)
    fair = next(f for f in feature_lift(used, metric="views_per_day") if f.feature == "question")
    assert fair.verdict == "hurts" and (fair.with_median, fair.without_median, fair.lift) == (10.0, 30.0, 0.33)


def test_age_window_is_inclusive():
    vids = [aged(d) for d in (3, 7, 30, 90, 91)]
    kept, left = with_age_metrics(vids, now=NOW, min_age=7, max_age=90)
    assert [v["age_days"] for v in kept] == [7.0, 30.0, 90.0]
    assert left == {OUTSIDE_WINDOW: 2}
    assert len(with_age_metrics(vids, now=NOW, min_age=7, max_age=7)[0]) == 1  # min == max is a valid window
    # one-sided windows, and the window also works with the plain views metric
    assert len(videos_for_metric(vids, metric="views", now=NOW, min_age=30)[0]) == 3
    assert len(videos_for_metric(vids, metric="views", now=NOW, max_age=7)[0]) == 2
    # a video without a publish time can't be inside any window
    used, left = videos_for_metric([*vids, {"title": "x", "views": 5}], metric="views", now=NOW, min_age=0)
    assert len(used) == 5 and left == {NO_PUBLISH_TIME: 1}


def test_with_age_metrics_does_not_mutate_input():
    # a fresh read - the module-level CONFOUND is shared with other tests, so it can't prove anything
    videos = json.loads((FIX / "stats_age_confound.json").read_text(encoding="utf-8"))["videos"]
    before = copy.deepcopy(videos)
    with_age_metrics(videos, now=NOW, min_age=1, max_age=100)
    videos_for_metric(videos, metric="views_per_day", now=NOW)
    assert videos == before
    assert all("age_days" not in v and "views_per_day" not in v for v in videos)


def test_parse_time_accepts_iso_forms_and_treats_naive_as_utc():
    utc_noon = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    assert parse_time("2026-11-15") == datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert parse_time("2026-11-15T12:00:00Z") == utc_noon
    assert parse_time("2026-11-15T13:00:00+01:00") == utc_noon
    assert parse_time("2026-11-15T12:00:00") == utc_noon  # no timezone = UTC, like schedule
    assert parse_time(" 2026-11-15T12:00:00Z ") == utc_noon
    assert all(parse_time(x) is None for x in ("yesterday", "", "  ", None, 20261115))
    # a naive `now` is read as UTC as well
    assert with_age_metrics([aged(10)], now=NOW.replace(tzinfo=None))[0][0]["age_days"] == 10.0


@pytest.mark.parametrize(
    ("min_age", "max_age"),
    [(-1, None), (None, -0.5), (float("nan"), None), (None, float("inf")), (30, 7), (7.5, 7)],
    ids=str,
)
def test_age_window_rejects_negative_and_inverted_limits(min_age, max_age):
    with pytest.raises(ValueError, match="age"):
        with_age_metrics([aged(10)], now=NOW, min_age=min_age, max_age=max_age)
