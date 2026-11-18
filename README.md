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
scripts/verify.sh             # expected: verify: OK (261 tests, coverage >= 85%)
```

Next time: `cd ~/Documents/dev/aidemy_seo && . .venv/bin/activate`.

---

## Features and how to use them

Add `--json` right after `aidemy-seo` for machine-readable output (e.g. `aidemy-seo --json schedule ...`).
Errors are one short line on stderr, never a Python traceback (`specs/cli-errors.md`): exit code 2
for input you can fix (`aidemy-seo calibrate: error: can't read calibration CSV x.csv: No such file or
directory (usage: aidemy-seo calibrate --help)`), exit code 1 when a YouTube API request fails. The
API key is never printed.

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
66 characters. Titles that keep both `#Fach` and `#KlasseN` rank higher. A grade range or school
level stays as it is (`--grade "Klasse 11-12"` gives `#Klasse11-12`, `--grade Q11` gives `#Q11`),
never one made-up grade.

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

### 12. Check many videos at once (batch CSV)

```bash
aidemy-seo analyze-batch videos.csv --min-score 60 --json
```

Reads a CSV (UTF-8; `,`, `;` or tab, detected from the header) with the columns `title`,
`description`, `tags` (separated by `|`) and an optional `video_id`. Offline, 0 API units.

- Score 0-100 per row, with a reason for every lost point:
  - **title length** (30): 40-65 characters, minus 1 point per character outside.
  - **shared words** (30): the share of the title's topic words that are also in the
    description. Hashtags and template words ("musst", "wissen", "einfach erklärt") don't count.
  - **tags** (40): 20 for 5-15 unique tags + 20 for a total under 500 characters.
- **Duplicate titles** are listed as pairs of lines (same title apart from case, umlauts and
  spaces).
- Other columns are ignored. A row with the wrong number of fields or no title is skipped
  with a warning naming its line. An empty description or empty tags is scored, not skipped.
- `--min-score N` lists only rows with at least N points. The summary says how many are hidden.
  Warnings and duplicates still cover every row. `--json` works before or after the command.
- This score is its own rubric. It is not the `title` check (35-60 characters without
  hashtags) and not vidIQ.

Don't commit real channel exports.

### 13. Title A/B tests for YouTube "Test & Compare"

YouTube Studio tests up to 3 titles on the **same** video and reports each title's share of the
watch time. Topic, week and age are the same for every title, so the test is fair. Offline, 0 API
units. Spec: `specs/ab-testing.md` · decision: `docs/adr/0007-title-ab-packs-fixed-margin-win-rate-weights.md`.

**Step 1 - write the titles** (CSV with `video_id`, `title` = the current title, `keyword`):

```bash
aidemy-seo ab-pack tests/fixtures/titles_to_fix.csv --out ab_pack.csv
aidemy-seo ab-pack tests/fixtures/titles_to_fix.csv --out ab_pack.csv --weights ab_weights.json   # after step 2
```
```text
wrote 27 titles for 10 of 10 videos to ab_pack.csv (0 skipped, 3 variants dropped)
order: why 0.75, search 0.25, question 0.20 (highest weight first, from ab_weights.json, 5 decided tests)
TITLES
video_id      variant   length  title
v01           why           44  Warum Worttrennung? Einfach erklärt #Deutsch
v01           search        60  Worttrennung einfach erklärt – das musst du wissen! #Deutsch
v01           question      46  Worttrennung – kannst du es erklären? #Deutsch
v02           why           52  Warum Raubtiere? Einfach erklärt #Biologie #Klasse11
v02           question      54  Raubtiere – kannst du es erklären? #Biologie #Klasse11
...
  line 3: search variant dropped - the search title is 68 characters with #Biologie #Klasse11 (max 66) - series hashtags are never dropped; testing why, question
```

| Rule | What happens |
|---|---|
| Variants | `search` = {x} einfach erklärt – das musst du wissen! · `question` = {x} – kannst du es erklären? · `why` = Warum {x}? Einfach erklärt ({x} = keyword) |
| Length | at most 66 characters, a title is never cut |
| Hashtags | from the current title, each once, at most 2. Grade tags (`#Klasse11`, `#Klasse11-12`, `#Q11`) and the `#Fach` of a series are never dropped, so the video stays in its series (feature 14) |
| Too long | only that variant is dropped (with a warning) and the video is tested with 2 titles. Skipped only if fewer than 2 fit |
| Order | search, question, why. With `--weights` from **5+ decided tests**: highest weight first; a variant with "not enough info" keeps its place |
| Output | `video_id, variant, title, length`, same delimiter as the input, normal file permissions |
| Bad rows | skipped with a warning naming the line (no `video_id` / keyword / title, repeated `video_id`, wrong number of fields) |

**Step 2 - read the results** (CSV with `video_id`, `variant`, `watch_time_share` from Studio; adding a
`watch_time_share` column to the `ab-pack` file works too):

```bash
aidemy-seo ab-results tests/fixtures/ab_results.csv --weights ab_weights.json
```
```text
8 videos in tests/fixtures/ab_results.csv: 5 winners, 2 inconclusive, 1 not evaluated (winner = top share - second share >= 0.05)
TESTS
video_id      result        top       share  second    share  margin
v02           winner        why       0.580  question  0.420   0.160
v04           inconclusive  why       0.520  question  0.480   0.040
v05           winner        search    0.450  question  0.400   0.050
v06           winner        why       0.455  search    0.335   0.120
v07           inconclusive  question  0.520  why       0.480   0.040
v08           winner        why       0.550  search    0.250   0.300
v10           winner        question  0.620  search    0.380   0.240
NOT EVALUATED
  v09 (line 14): only 1 variant (search) - a test compares 2 or 3
WARNINGS
  (none)
WEIGHTS (wins / decided tests the variant was in, from 3 tests on; 5 decided tests, written to ab_weights.json)
  search    0.25  (1 of 4)
  question  0.20  (1 of 5)
  why       0.75  (3 of 4)
```

| Rule | What happens |
|---|---|
| Winner | top share - second share >= **0.05**, otherwise inconclusive (compared exactly: 0.45 vs 0.40 is a winner) |
| Shares | `0.42`, `0,42` or `42%` |
| Weight | wins ÷ decided tests **the variant was in** (a test without the variant is no loss), 2 decimals |
| Too few tests | a variant needs **3** decided tests, otherwise "not enough info" (`null` in the file), not 0. `ab-pack` uses the weights from **5** decided tests in total |
| Not evaluated | a broken row, a variant twice, only 1 variant, or shares adding up to more than 1.01 (100% + rounding) - never guessed |
| Weights file | `{"decided": 5, "weights": {"search": 0.25, "question": 0.2, "why": 0.75}}`, the `--weights` input of step 1 |

**Input files are never overwritten:** an `--out` / `--weights` that is an input file (also via `./`,
a symlink or a hard link) is refused. Outputs are written atomically.

### 14. Shorts series (playlists) from #Fach + #KlasseN

```bash
aidemy-seo series tests/fixtures/titles_to_fix.csv
```
```text
2 series in tests/fixtures/titles_to_fix.csv: 5 of 10 videos in a series, 5 not sorted, 0 skipped
SERIES
Biologie Klasse 11 (3 videos)
  line   3  v02           Warum es immer weniger Raubtiere gibt 🦁 #Biologie #Klasse11
  line   4  v03           Neobiota & Selbstregulation in Ökosystemen : Das musst du wissen! #Biologie #Klasse11
  line   7  v06           Atmung & Gärung: Das musst du wissen! #Biologie #Klasse11
Ethik Klasse 5 (2 videos)
  line   5  v04           Warum wir nicht alleine leben koennen #Ethik #Klasse5
...
NOT SORTED
  line   2  v01           Die Worttrennung, die in jeder Klassenarbeit vorkommt 📚 #Deutsch  - no #KlasseN hashtag
  ...
```

| Rule | What happens |
|---|---|
| Input | CSV with `title` (`video_id` optional) - the `ab-pack` and `analyze-batch` CSVs work as they are. Writes no file |
| Series | same `#Fach` + same `#KlasseN`, 2 or more videos -> "Fach Klasse N" (case and umlauts don't matter) |
| Subject | the first hashtag that is no grade tag, no school level and not `#Shorts` |
| Not sorted | every other video, with the reason: no `#KlasseN`, 2 grades, no subject, only video of its group |
| Never guessed | a grade range (`#Klasse11-12`) or a school level (`#Q11`, `#Oberstufe`, `#SekII`, `#Abitur`) is not turned into a grade: without a `#KlasseN` the video is not sorted, with the reason. A level is never the subject |

Spec: `specs/series.md` · decision: `docs/adr/0008-series-from-title-hashtags.md`.

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
5. **A/B packs and series:** `tests/test_integration_ab_series.py` runs the whole loop
   (`ab-results` on `tests/fixtures/ab_results.csv` -> weights -> `ab-pack --weights`) and `series`,
   and checks that no input file changes. By hand: run features 13 and 14 on the fixtures, with
   `--out` / `--weights` in a scratch folder.

---

## Development workflow (for people and coding agents)

This repo is set up so an AI coding agent can work in it safely and correct itself:

| Piece | Where | What it does |
|---|---|---|
| Project context | `CLAUDE.md` | Rules, commands and layout every agent session reads first |
| Permissions + hooks | `.claude/settings.json` | Allows tests/lint, asks before commit/push/install, denies secrets, curl, `rm -rf`; runs `verify --fast` after every edit and the full verify when the agent stops |
| Skills | `.claude/skills/` | `spec-first-feature` (ticket -> spec -> tests -> code -> verify) and `verify` (fix loop) |
| Specs | `specs/*.md` | What each feature must do; every scenario names its test. `tests/test_specs.py` fails if a spec and the tests drift apart |
| Decisions | `docs/adr/` | Why: stdlib core, autocomplete as demand signal, cross-channel normalisation, MIT, age-fair views per day, batch rubric, title A/B packs, series from hashtags |
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
  batch.py         batch CSV analysis: per-row score, duplicate titles, ranking
  abtest.py        title A/B packs (search/question/why) + Test & Compare results -> variant weights
  series.py        Shorts series from #Fach + #KlasseN title hashtags
  fileio.py        shared CSV reader (batch, abtest, series), atomic file write (abtest, experiment ledger), same-file check
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
- The batch CSV word match uses 6-letter prefixes, so "Nahrungsnetze" and "Nahrungsketten"
  count as the same word. A topic that is also a hook word ("Wahrheit", "Mythos") doesn't count.
  The tag length adds up the tag characters only. YouTube also counts commas and quotes, so a
  total just under 500 can still be too long. Only exact duplicate titles are found.
- The A/B winner rule (top - second >= 0.05) is a fixed threshold, not a significance test:
  Studio's results have no view counts, so a small video can win by chance. 3 tests per variant
  and 5 in total are small samples - read `(wins of tests)` next to every weight.
- A long keyword plus the series hashtags can leave no room for the `search` title (v02-v04 in
  the example): that video tests question + why only, so `search` collects tests more slowly.
- `series` trusts the first subject hashtag (`#Bio` and `#Biologie` are two series) and knows a
  fixed list of school levels (`#Kursstufe` or `#J1` in first place would be read as a subject).
  It suggests playlists; it does not create them.

## Licence

MIT - see `LICENSE`.
