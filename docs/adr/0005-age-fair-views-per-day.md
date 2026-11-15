# 0005 - Age-fair learning: views per day inside an age window, experiments for a clean answer

- Status: accepted
- Date: 2026-11-15

## Context
`aidemy-seo learn` compared title styles by total `views`. Total views keep growing, so
older videos win just by being older. Example (`tests/fixtures/stats_age_confound.json`):
question titles posted 90-95 days ago at 10 views per day have ~925 total views, and newer
titles posted 10-15 days ago at 30 views per day have ~375. On total views, "question"
**helps** (lift 2.37) - but per day it earns a third as much, so it actually **hurts**
(lift 0.33). `views_24h` would be fair, but most videos don't have it: on 2026-11-13 only
5 of 78 videos in aidemy_pub's stats.json had it.

ADR 0003 rejected views per day for comparing *other* channels, because there the channel
size dominates. On our *own* channel all videos come from one channel, so size is not a
factor and age is the main bias left.

## Options
1. Keep total views (default), add a warning only.
2. Only use `views_24h` - fair, but it leaves out almost every video.
3. Model the view curve (fit a decay per video and compare predicted views at day N). That
   needs many data points per video; stats.json has one snapshot.
4. `views_per_day = views / max(age_days, 1)`, plus an optional age window
   (`--min-age` / `--max-age`), with `now` as a parameter so results can be reproduced.
5. Randomised experiments: assign the title template by hash before upload, so age and topic
   spread evenly across templates by design.

## Decision
Option 4 for `learn`, and option 5 as a separate command (`experiment assign/report`,
`specs/experiments.md`), which reuses option 4 for its metric.

- `views_per_day` is always calculated from `views` and the publish time, never read from
  the stats file. The one-day minimum stops a 2-hour-old Short counting as "600 per day".
- Videos without a usable publish time, or published after `now`, are left out and
  counted by reason on the first output line - they never get a made-up age.
- The age window is inclusive and works with every metric; limits must be finite and >= 0.
- `now` defaults to the current UTC time. `--now` makes results reproducible, and every
  test pins it.
- Backwards compatible: `learn` still defaults to `--metric views` (with a `hint:` line),
  and its `--json` output keeps the same shape, so aidemy_pub callers don't break.
- The experiment report defaults to `views_per_day` and `--min-age 7`.

## Consequences
+ The age trap above is caught: both metrics are shown side by side in the README, and a
  test checks that the verdict flips.
+ Standard library only (`datetime`, `math`). One shared code path (`learn.videos_for_metric`)
  for `learn` and `experiment report`.
- Views per day is still biased towards young videos, because Shorts get most of their
  views in the first days. An age window reduces this; it doesn't remove it. Only
  experiments (option 5) fully remove the age and topic bias.
- Results depend on `now`. Without `--now`, running the same command tomorrow gives
  different numbers - by design, but surprising.
- Option 3 is still possible later, if aidemy_pub starts keeping a view history per video.
