# Posting times and learning from your own channel

## Requirements
- Slots MUST be weekday + hour in the given timezone, ranked by median, Shorts only by default.
- A slot with fewer than min_videos MUST be marked "not enough data" and ranked below.
- A video without the chosen metric MUST be left out, never silently ranked by its total views
  (that favours older videos); a fallback metric is used only when asked (--fallback-metric).
  The CLI MUST say how many Shorts have the metric.
- feature_lift MUST NOT claim helps/hurts with fewer than min_group videos on each side.

### Age-fair learning (`learn --metric views_per_day --min-age --max-age --now`)
Total `views` grow with age, so a 3-month-old title style "wins" against last week's just by
being older. `learn` gets a derived metric and an age window so videos are compared fairly.

- Age MUST be `(now - publish time)` in days (float). Publish time is read like `schedule`:
  `went_public_at`, then `published_at`, then `publish_at`; a time without a timezone is UTC.
- `views_per_day` MUST be derived, never read from the stats file (a stored value is dropped):
  `views / max(age_days, 1.0)` (a video younger than one day counts as one day, so a 2-hour-old
  Short with 50 views is not "600 per day"). It is rounded to 2 decimals.
- A video MUST be left out of views_per_day when it has no `views`, no parseable publish
  time, or a publish time after `now`. It MUST NOT get a made-up age.
- `--min-age DAYS` / `--max-age DAYS` MUST keep only videos with
  `min_age <= age_days <= max_age` (inclusive, like the 7-180 day window in other-channels.md).
  They work with every metric, so `--metric views --min-age 30 --max-age 60` is also allowed.
  A video without a parseable publish time MUST be left out whenever an age limit is set.
- Defaults MUST keep today's behaviour: `--metric views`, no age limits. When the metric is
  total `views` and no age window is set, one hint line says that total views favour older
  videos (other metrics such as `views_24h` are already fixed-window, so no hint).
- `--now` MUST accept ISO 8601 (`2026-11-15`, `2026-11-15T12:00:00Z`,
  `2026-11-15T13:00:00+01:00`). The default is the current UTC time. Tests MUST always pass
  `now` so results don't change with the calendar.
- Invalid input MUST exit with argparse's usage error (exit code 2) and a clear message,
  never a traceback: an unparseable `--now`, an age that is negative or not finite (`inf`,
  `-inf`, `nan` - `float()` accepts them), or `--min-age` > `--max-age`. `check_age_window()`
  applies the same rule for Python callers.
- The text output MUST start with one coverage line: how many videos were used out of how
  many, the metric, the window and `now` when ages are used, and how many were left out for
  each reason ("no publish time" - missing or unparseable, "published after now", "outside the
  age window", "no <metric>"). This follows the `schedule` rule that the CLI says what it used.
- `--json` output MUST keep its current shape (a list of findings), so aidemy_pub callers
  don't break. The coverage line is in the text output only.
- `views_per_day` reduces age bias but does not remove it: Shorts get most of their views in
  the first days, so very young videos still look better per day. The spec accepts this and
  recommends narrowing the window (e.g. `--min-age 7 --max-age 90`). The README MUST say so.
- Library API (`learn.py`): `with_age_metrics(videos, *, now, min_age=None, max_age=None)`
  returns `(kept_videos, left_out_counts)`. Kept videos are copies with `age_days` and
  `views_per_day` added; the input list is not changed. `videos_for_metric(videos, *, metric,
  now, min_age, max_age)` adds the "no <metric>" count and passes videos through untouched when
  no age is needed. `parse_time()`, `check_age_window()` and `coverage_line()` are shared with
  the CLI (and later `experiment report`). `feature_lift()` itself is unchanged.

## Scenarios
- Given 3 Tuesday 15:00 Shorts and a long video, then Tue 15:00 ranks first with enough data
  and the long video is ignored. Test: tests/test_aidemy_seo.py::test_best_slots_ranks_by_median_and_flags_thin_data
- Given old Shorts with total views only and one with views_24h, then only that one is ranked.
  Test: tests/test_aidemy_seo.py::test_best_slots_never_falls_back_to_total_views_silently
- Given fallback_metric="views", then the old Shorts are ranked by total views.
  Test: tests/test_aidemy_seo.py::test_best_slots_fallback_only_when_asked
- Test: tests/test_aidemy_seo.py::test_best_hours
- Given 5 videos, then every feature says "not enough data".
  Test: tests/test_aidemy_seo.py::test_feature_lift_says_not_enough_data_on_young_channel
- Given 6 question titles at 200 views and 6 others at 50, then question "helps" with lift 4.0.
  Test: tests/test_aidemy_seo.py::test_feature_lift_finds_real_effect_with_enough_data

### Age-fair learning
- Given now = 2026-11-15T00:00Z and a Short published 2026-11-05T00:00Z with 300 views, then
  age_days = 10.0 and views_per_day = 30.0; given one published 6 hours ago with 50 views,
  then views_per_day = 50.0 (the one-day floor). A views_per_day stored in the file is ignored,
  also on a video without views (it gets none).
  Test: tests/test_learn_age.py::test_views_per_day_uses_age_with_one_day_floor
- Given tests/fixtures/stats_age_confound.json (e_nodate, e_baddate, e_future, e_noviews),
  then none of them is used for views_per_day and they are counted as 2 "no publish time",
  1 "published after now", 1 "no views_per_day". One hour after now is already "published
  after now"; published exactly at now is kept.
  Test: tests/test_learn_age.py::test_with_age_metrics_leaves_out_undatable_and_future_videos
- Given stats_age_confound.json: 6 question titles 90-95 days old at 10 views per day and
  6 other titles 10-15 days old at 30 per day, then on `views` question "helps" (lift 2.37,
  the age trap) and on `views_per_day` question "hurts" (10.0 vs 30.0, lift 0.33).
  Test: tests/test_learn_age.py::test_feature_lift_views_per_day_removes_age_advantage
- Given videos aged 3, 7, 30, 90 and 91 days and min_age=7, max_age=90, then exactly the
  7, 30 and 90 day videos are kept (both limits inclusive); min_age = max_age = 7 is a valid
  window and keeps the 7 day video.
  Test: tests/test_learn_age.py::test_age_window_is_inclusive
- Given the input list, when with_age_metrics runs, then the input dicts are unchanged.
  Test: tests/test_learn_age.py::test_with_age_metrics_does_not_mutate_input
- Given "2026-11-15", "...T12:00:00Z", "...T13:00:00+01:00" or a time without timezone,
  then all parse to the same UTC time (no timezone = UTC); "yesterday", "" and None give None.
  Test: tests/test_learn_age.py::test_parse_time_accepts_iso_forms_and_treats_naive_as_utc
- Given min_age -1, max_age -0.5, NaN, max_age inf, or min_age 30 or 7.5 > max_age 7, then a
  ValueError is raised.
  Test: tests/test_learn_age.py::test_age_window_rejects_negative_and_inverted_limits
- Given `learn STATS --metric views_per_day --now 2026-11-15`, then the first line reports
  "12 of 12 videos used" and question "helps"; `--json` is still a list of findings. On
  stats_age_confound.json question "helps" with the default metric and "hurts" with
  views_per_day.
  Test: tests/test_integration_cli.py::test_learn_views_per_day_cli
- Given `--min-age 7 --max-age 40 --now 2026-11-15` on the fixture (ages 33.3-44.4 days),
  then 7 of 12 videos are used (s5-s11) and the coverage line counts 5 as "outside the age
  window". One-sided windows are labelled "age >= 40 days" / "age <= 35.5 days".
  Test: tests/test_integration_cli.py::test_learn_age_window_cli
- Given `--now yesterday`, `--min-age -1`, `--min-age inf`, `--max-age=-inf`, `--max-age nan`,
  `--max-age many` or `--min-age 30 --max-age 7`, then the command exits with code 2 and a
  usage message, not a traceback.
  Test: tests/test_integration_cli.py::test_learn_rejects_bad_age_arguments
- Given `learn STATS` with no new options, then the output is the same as before plus the
  coverage line and the "total views favour older videos" hint.
  Test: tests/test_integration_cli.py::test_learn_default_keeps_behaviour_and_warns
