# aidemy_seo

YouTube SEO analytics and optimisation for educational channels, built on real data:
real YouTube search demand, your own channel's numbers, and the titles of the videos that
already rank.

Sibling project of **aidemy_pub** (the lesson and video pipeline): aidemy_pub produces and
uploads, aidemy_seo decides *what to call it, when to post it and what is working*.

- Licence: **MIT** (see `LICENSE`) - free to use, change and share, including commercially.
- Python 3.10+. The core uses only the standard library; `requests` is optional (live data).

---

## Install

From the folder that contains `pub_pipeline` (e.g. `~/Documents/dev`):

```bash
cd aidemy_seo
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[http,dev]"
git init && git config core.hooksPath .githooks   # verify runs before every commit
scripts/verify.sh             # expected: verify: OK (105 tests, coverage >= 85%)
```

Next time: `cd ~/Documents/dev/aidemy_seo && . .venv/bin/activate`.

---

## Features and how to use them

Add `--json` right after `aidemy-seo` for machine-readable output (e.g. `aidemy-seo --json schedule ...`).

### 1. Keyword research - which words people really search

```bash
aidemy-seo keywords "Nutzen und Risiken ausgewählter transgener Organismen" \
    --short-name "Grüne und Rote Gentechnik"
```

Ranks the lesson's own keyword candidates by real YouTube search demand and names the best
keyword for the title.

- Source: YouTube's search autocomplete. Free, no API key, uses no API quota.
- Demand is 0-10 (how many real search completions start with the phrase). `?` means the
  lookup failed (offline), never "nobody searches".
- Only words from the lesson are candidates. "Grüne und Rote Gentechnik" becomes
  "Grüne Gentechnik", "Rote Gentechnik" and "Gentechnik". Generic words ("Nutzen",
  "Risiken") and side terms are never used.

### 2. Title check

```bash
aidemy-seo title "Transgene Organismen: Das musst du wissen! #Biologie #Klasse10" --keyword Gentechnik
```

Explainable score out of 100 with the exact issues: searched keyword first, keyword present,
hook (question or "du"), emotion word, not a shop label ("Kl. 6: ... Set"), length,
1-3 hashtags, no ALL CAPS, 10 words or fewer.

### 3. Title ideas

```bash
aidemy-seo title Gentechnik --generate --subject Biologie --grade "Klasse 10"
```

Ranked candidates from honest templates (no claims the video doesn't make), always within
66 characters. Titles that keep both `#Fach` and `#KlasseN` rank higher.

### 4. Description check

```bash
aidemy-seo description desc.txt --keyword Wahrnehmung --keyword "Ethik Klasse 6" --link-hint /material/
```

(`-` instead of a file name reads from stdin.) Checks: searched keywords in the first 200
characters, link in the first 4 lines, a direct product link (not only the author page),
3-5 hashtags, length, a call to subscribe or comment, short paragraphs.

### 5. Best posting times

```bash
aidemy-seo schedule ../pub_pipeline/state/youtube/stats.json
```

Best weekday + hour (Berlin time) by median views after 24 hours, from your own channel.
Slots with fewer than 3 videos are listed but marked "not enough data".
Options: `--metric views`, `--min-videos 5`, `--tz Europe/Berlin`.

### 6. Learn from your own channel

```bash
aidemy-seo learn ../pub_pipeline/state/youtube/stats.json --metric views_per_day --min-age 7 --max-age 90
```

For each title style (question, "du", emotion word, "einfach erklärt", "Das musst du wissen",
hashtags in title, numbers, under 50 characters) compares the median metric of videos with
and without it. It only reports "helps"/"hurts" once there are at least 5 videos on each
side (`--min-group`), otherwise it says "not enough data".

**Compare fairly by age.** Total `views` keep growing, so a 3-month-old title style "wins"
against last week's just by being older. Two tools fix that (spec:
`specs/schedule-and-learning.md`, decision: `docs/adr/0005-age-fair-views-per-day.md`):

| Option | What it does |
|---|---|
| `--metric views_per_day` | views / age in days, at least 1 day (a 2-hour-old Short with 50 views is 50/day, not 600). Always calculated, never read from the stats file. Other metrics: any field of the stats file, e.g. `views` (default) or `views_24h` |
| `--min-age DAYS` | only videos at least this many days old (inclusive) |
| `--max-age DAYS` | only videos at most this many days old (inclusive). Both limits work with every metric, must be finite and >= 0, and `--min-age` <= `--max-age` |
| `--now TIME` | the moment ages are measured from, ISO 8601: `2026-11-15`, `2026-11-15T12:00:00Z` or `2026-11-15T13:00:00+01:00` (no timezone = UTC). Default: now (UTC). Pin it to get the same result every day |

The age of a video is taken from `went_public_at`, then `published_at`, then
`publish_at` (like `schedule`). Videos without a usable publish time, published after
`--now`, or without the metric are left out - never given a made-up age - and the first
line of the output says how many and why. The same data
(`tests/fixtures/stats_age_confound.json`, old question titles vs. new ones) with both
metrics:

```text
$ aidemy-seo learn stats_age_confound.json
15 of 16 videos used (metric views); left out: 1 no views
hint: total views favour older videos - for a fair comparison use --metric views_per_day (or views_24h) and/or an age window (--min-age / --max-age)
question           with   6 (  925.0) without   9 (  390.0)  helps

$ aidemy-seo learn stats_age_confound.json --metric views_per_day --now 2026-11-15
12 of 16 videos used (metric views_per_day, ages at 2026-11-15 00:00 UTC); left out: 2 no publish time, 1 published after now, 1 no views_per_day
question           with   6 (   10.0) without   6 (   30.0)  hurts
```

On total views the old question titles seem to "help"; per day of age they earn a third of
what the new titles earn. Without `--metric views_per_day` or an age window the command
behaves as before and prints the `hint:` line. With `--json` the output is the same list of
findings as before (the coverage line is only in the text output).

`views_per_day` reduces the age bias but does not remove it: Shorts collect most of their
views in the first days, so very young videos still look better per day. Keep the window
narrow (e.g. `--min-age 7 --max-age 90`). For a clean answer, run an experiment (feature 11).

### 7. Compare with an external score (vidIQ)

```bash
aidemy-seo calibrate tests/fixtures/vidiq_scores_2026-11-12.csv
```

Average external score per title style. The CSV is `title;score`, one title per line - add
every vidIQ score you see. The checklist in feature 2 is not vidIQ's score (vidIQ's keyword
data is private); this is how the two are compared and the templates steered.

### 8. One aidemy_pub lesson

```bash
aidemy-seo lesson ../pub_pipeline/out/<...>/bundle.json
```

Best keyword and ranked titles for one lesson, straight from its `bundle.json`.

### 9. What the top creators do

```bash
export YOUTUBE_API_KEY=...            # read-only key, never commit it
aidemy-seo benchmark "Gentechnik einfach erklärt" --shorts
```

Title patterns of the top-ranking videos for a keyword: median length, share of questions,
numbers, "du", keyword first, hashtags, emoji, and the words used in the most-viewed titles.
Key: Google Cloud Console -> APIs & Services -> Credentials -> API key, restricted to
"YouTube Data API v3". Cost: about 101 of the 10,000 daily quota units per run.

### 10. Learn from other channels in your area (much more data)

```bash
export YOUTUBE_API_KEY=...
aidemy-seo channels --file examples/channels_de_school.txt --save channels.json
aidemy-seo channels --discover "Biologie Klasse 10" @simpleclub
aidemy-seo channels --load channels.json          # re-analyse later, no API calls
```

Runs the posting-time and title-style analysis on the Shorts of many related channels at once.
To compare a channel with 2 million subscribers fairly with a small one, every video is
scored against its own channel: `score = views / that channel's median`, so 1.0 = usual
for that channel, 2.0 = twice as good. Only Shorts (up to 3 minutes) from the last 7-180
days are used.

Output: best posting slots and hours (Berlin time), which title styles win across channels
(needs 10+ videos on each side), and a line per channel (subscribers, Shorts used, median
views, usual posting hours). Cost: about 5 quota units per channel (`--discover` adds 100).
`examples/channels_de_school.txt` is a starting list - the handles are not verified, any
that are not found are reported, edit the file freely.

### 11. Test title templates fairly (experiments)

`learn` looks back at titles you picked by hand, so it also measures *why* you picked them
(the question title went on the topic you expected to do well) and *when* they were posted.
An experiment removes both: before upload, a fixed hash picks the title template, all
templates are posted over the same weeks, and the report compares them on views per day
with a confidence interval. Spec: `specs/experiments.md`.

**1. Before each upload, assign a template:**

```bash
aidemy-seo experiment assign experiments.json --experiment hook-2026-11 \
    --key bio-kl10-gentechnik --keyword Gentechnik --subject Biologie --grade "Klasse 10" \
    --arm question --arm musst_du_wissen
```
```text
experiment hook-2026-11, key bio-kl10-gentechnik -> arm musst_du_wissen (new)
title: Gentechnik: Das musst du wissen! #Biologie #Klasse10
```

Use exactly this title. The arms are the 6 title templates:

| Arm | Template |
|---|---|
| `question` | {x} – kannst du es erklären? |
| `einfach_musst` | {x} einfach erklärt – das musst du wissen! |
| `einfach_endlich` | {x} einfach erklärt – endlich verstanden! |
| `warum` | Warum {x}? Einfach erklärt |
| `musst_du_wissen` | {x}: Das musst du wissen! |
| `endlich` | {x} – endlich verstanden! |

| Option (`assign`) | What it does |
|---|---|
| `LEDGER` | the experiment file (JSON). Created on the first assign; keep it - it is the only record of which video got which template |
| `--experiment NAME` | the experiment, e.g. `hook-2026-11` |
| `--key KEY` | a stable id of the video before it exists, e.g. the lesson slug. The template depends only on the experiment name and this key (sha256), never on the keyword or the time |
| `--keyword`, `--subject`, `--grade` | build the title, with the same `#Fach #KlasseN` tags as `title --generate` |
| `--arm NAME` | repeatable, only when the experiment starts (at least 2). Default: all 6. Fewer arms give a result sooner: every arm needs 5 published videos |
| `--now TIME` | the time recorded in the ledger (ISO 8601). Default: now |

Running `assign` again for the same key changes nothing and prints the stored title
(`already assigned`). The template is never re-drawn - not even when the title comes out
over 66 characters or with two `:` (you get a `warning:` instead), because picking again
would bring back the bias the experiment removes. Changing the arms of a running
experiment, or two keys with the same title, is refused. The ledger is written atomically
(a crash never leaves half a file), a new ledger is private to your user (mode 0600).

**2. After a few weeks, read the report:**

```bash
aidemy-seo experiment report experiments.json ../pub_pipeline/state/youtube/stats.json --experiment hook-2026-11
```
```text
16 of 17 assigned videos used (metric views_per_day, age >= 7 days, ages at 2026-11-15 00:00 UTC); left out: 1 not published yet or title changed
verdict: WINNER = question - beats every other arm (musst_du_wissen: ratio 2.818, 95% CI 2.5-3.1)
  (only trust this if you fixed the number of videos per arm in advance - stopping at the first 'winner' overstates the confidence)

arm              assigned published used   median   lift  note
musst_du_wissen        10         9    9    11.21   0.35  hurts
question                7         7    7    31.59   2.82  helps

not counted:
  bio-kl10-gentechnik (musst_du_wissen): not published yet or title changed - Gentechnik: Das musst du wissen! #Biologie #Klasse10
```

Videos are found in the stats file by their exact title (spaces don't matter, case does).
Videos that are not in the ledger are ignored; ledger entries without a video are listed
under `not counted`. The **verdict** is one of:

- `insufficient data` - an arm has fewer than `--min-group` (5) used videos; it says how many
  each arm still needs.
- `no winner yet` - the leader (highest median) has not yet beaten every other arm: the
  confidence interval of `median(leader) / median(other)` still includes 1.0. Keep posting.
- `winner` - the leader beats every other arm: every interval is above 1.0. With 3 or more
  arms each interval is made stricter (Bonferroni: 97.5% for 3 arms at `--confidence 0.95`),
  so more arms don't mean more lucky winners.

The `lift` column (arm vs. all other arms, "helps" >= 1.2, "hurts" <= 0.8) only describes
each arm; only the verdict names a winner.

| Option (`report`) | What it does |
|---|---|
| `LEDGER STATS_JSON` | the experiment file and the aidemy_pub stats file |
| `--experiment NAME` | which experiment |
| `--metric` | default `views_per_day` (see feature 6) |
| `--min-age` / `--max-age` | default: at least 7 days old (a Short's first days are noisy), no maximum |
| `--now TIME` | the moment ages are measured from. Default: now |
| `--min-group N` | used videos needed per arm before any verdict (default 5) |
| `--confidence C` | between 0 and 1, default 0.95 |
| `--seed N` | the interval is a bootstrap (2,000 resamples); same data + same seed = same interval (default 0) |

**JSON for both commands** - put `--json` right after `aidemy-seo`:

```bash
aidemy-seo --json experiment assign experiments.json --experiment hook-2026-11 --key bio-kl10-gentechnik --keyword Gentechnik
aidemy-seo --json experiment report experiments.json stats.json --experiment hook-2026-11
```

`assign` returns `{"experiment", "key", "arm", "template", "keyword", "title",
"assigned_at", "already_assigned", "warnings"}`. `report` returns (shortened):

```json
{
  "experiment": "hook-2026-11", "metric": "views_per_day", "min_age": 7.0, "max_age": null,
  "now": "2026-11-15T00:00:00+00:00", "confidence": 0.95, "seed": 0, "min_group": 5,
  "verdict": "winner", "winner": "question", "leader": "question",
  "comparisons": [{"arm": "question", "vs": "musst_du_wissen", "ratio": 2.818, "level": 0.95,
                   "ci_low": 2.5, "ci_high": 3.1}],
  "arms": [{"arm": "musst_du_wissen", "template": "{x}: Das musst du wissen!", "assigned": 10,
            "published": 9, "used": 9, "median": 11.21, "lift": 0.35, "verdict": "hurts"}, "..."],
  "unmatched": [{"key": "bio-kl10-gentechnik", "arm": "musst_du_wissen", "title": "...",
                 "reason": "not published yet or title changed"}],
  "assigned": 17, "used": 16, "left_out": {"not published yet or title changed": 1}
}
```

With `insufficient data`, `winner` and `leader` are `null` and `comparisons` is empty. An
infinite ratio (the other arm's median is 0) is written as the string `"inf"` - JSON has no
Infinity. Bad input (unknown arm, changed arms, a broken or missing ledger, an unknown
experiment, `--confidence 1.5`, a missing stats file, ...) stops with exit code 2 and a
one-line message; the ledger is never changed by a refused command.

**Rules for a fair result:**

1. Decide before you start how many videos per arm you will post (e.g. 10), and read the
   verdict then. Checking every day and stopping at the first `winner` makes a false winner
   more likely than 5%.
2. Assign before writing the title, and don't edit the title after upload - the report
   finds videos by title (an edited title is listed as `not counted`).
3. Don't skip a template because you don't like it for a topic - that is the bias the hash
   removes.

---

## Use from Python (how aidemy_pub calls it)

```python
from aidemy_seo.aidemy_pub import suggest_for_lesson
from aidemy_seo import audit_description, best_slots, feature_lift, score_title

s = suggest_for_lesson(bundle)        # {"keyword": ..., "keywords": [...], "titles": [...]}
title = s["titles"][0]["title"]

audit = audit_description(text, keywords=[s["keyword"]], link_hint="/material/")
print(audit.score, audit.issues)

# age-fair learning (feature 6)
from datetime import datetime, timezone
from aidemy_seo.aidemy_pub import load_channel_videos
from aidemy_seo.learn import videos_for_metric

now = datetime.now(timezone.utc)
videos = load_channel_videos("state/youtube/stats.json")
used, left_out = videos_for_metric(videos, metric="views_per_day", now=now, min_age=7, max_age=90)
findings = feature_lift(used, metric="views_per_day")

# experiments (feature 11)
from aidemy_seo.experiments import assign, load_ledger, report

a = assign("experiments.json", experiment="hook-2026-11", key=lesson_slug, keyword=s["keyword"],
           subject="Biologie", grade="Klasse 10", arms=["question", "musst_du_wissen"])
title = a.title                       # upload with exactly this title
r = report(load_ledger("experiments.json", must_exist=True), videos, experiment="hook-2026-11")
print(r.verdict, r.winner)            # r.to_json() = the --json output
```

---

## How to test

1. **Full local CI** (offline, real fixtures: a real Biologie Klasse 10 lesson, real vidIQ
   scores, a real description):
   ```bash
   scripts/verify.sh
   ```
2. **Live keyword data:** run feature 1. The "demand" column should show numbers. `?`
   everywhere means the machine cannot reach YouTube's autocomplete.
3. **Your channel:** run features 5 and 6 on `pub_pipeline/state/youtube/stats.json`.
   "not enough data" is the correct answer while the channel is young. Compare
   `learn` with and without `--metric views_per_day` to see how much age changes the picture.
4. **Experiments:** the integration test `test_experiment_assign_and_report_cli` runs the whole
   loop (assign 17 videos -> publish -> report). To try it by hand, assign into a scratch
   ledger (`/tmp/experiments.json`) and report against a copy of your stats file.

---

## Development workflow (for people and coding agents)

This repo is set up so an AI coding agent can work in it safely and correct itself:

| Piece | Where | What it does |
|---|---|---|
| Project context | `CLAUDE.md` | Rules, commands and layout every agent session reads first |
| Permissions + hooks | `.claude/settings.json` | Allows tests/lint, asks before commit/push/install, denies secrets, curl, `rm -rf`; runs `verify --fast` after every edit and the full verify when the agent stops |
| Skills | `.claude/skills/` | `spec-first-feature` (ticket -> spec -> tests -> code -> verify) and `verify` (fix loop) |
| Specs | `specs/*.md` | What each feature must do; every scenario names its test. `tests/test_specs.py` fails if a spec and the tests drift apart |
| Decisions | `docs/adr/` | Why: stdlib core, autocomplete as demand signal, cross-channel normalisation, MIT, age-fair views per day |
| Verification | `scripts/verify.sh` | Local CI: ruff lint + format, mypy, pytest with 85% coverage gate |
| Git hook | `.githooks/pre-commit` | Runs verify before every commit: `git config core.hooksPath .githooks` |
| CI | `.github/workflows/ci.yml` | Same verify on Python 3.10 / 3.12 / 3.13 for every push and PR |
| PR template | `.github/pull_request_template.md` | Spec, tests, and a line-by-line review checklist for secrets, cost, user data |
| Quality baseline | `docs/quality.md` | Tests, coverage and mutation score over time |

Tests: unit (offline, real fixtures), integration (every CLI command, in-process and as the
installed executable), live (`pytest -m live`, real APIs), mutation (`mutmut run`).

## Project layout

```
src/aidemy_seo/
  keywords.py      autocomplete demand, lesson keyword candidates, ranking
  titles.py        title checklist score, candidate generation, calibration
  descriptions.py  description audit
  schedule.py      best posting slots / hours
  learn.py         title-feature lift on your own videos; age-fair views_per_day + age window
  experiments.py   title template experiments: hash assignment, JSON ledger, bootstrap report
  benchmark.py     title patterns of top videos
  youtube_api.py   minimal read-only YouTube Data API client
  competitors.py   other channels: per-channel normalised posting times + title styles
  aidemy_pub.py    adapter for aidemy_pub (stats.json, bundle.json)
  cli.py           the `aidemy-seo` command
tests/             unit, integration (CLI end-to-end), live (-m live), spec<->test check
specs/  docs/adr/  docs/quality.md  scripts/verify.sh  .claude/  .githooks/  .github/
```

## Honest limits

- The title score is an explainable checklist, not vidIQ's score.
- Autocomplete demand is a 0-10 signal, not a search-volume number.
- `learn` and `schedule` need enough videos before they claim anything.
- `views_per_day` reduces the age bias but does not remove it (Shorts get most views early);
  use an age window, and an experiment for a clean answer.
- An experiment `winner` is only as trustworthy as the plan behind it: fix the number of
  videos per arm in advance. The interval comes from a bootstrap on few videos - it is
  a careful estimate, not a guarantee.

## Licence

MIT - see `LICENSE`.
