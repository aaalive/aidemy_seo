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
scripts/verify.sh             # expected: verify: OK (38 tests, coverage >= 85%)
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
aidemy-seo learn ../pub_pipeline/state/youtube/stats.json
```

For each title style (question, "du", emotion word, "einfach erklärt", "Das musst du wissen",
hashtags in title, numbers, under 50 characters) compares median views with and without it.
It only reports "helps"/"hurts" once there are at least 5 videos on each side
(`--min-group`), otherwise it says "not enough data". Use `--metric views_24h` for a fair
comparison (total views favour older videos).

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

---

## Use from Python (how aidemy_pub calls it)

```python
from aidemy_seo.aidemy_pub import suggest_for_lesson
from aidemy_seo import audit_description, best_slots, feature_lift, score_title

s = suggest_for_lesson(bundle)        # {"keyword": ..., "keywords": [...], "titles": [...]}
title = s["titles"][0]["title"]

audit = audit_description(text, keywords=[s["keyword"]], link_hint="/material/")
print(audit.score, audit.issues)
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
   "not enough data" is the correct answer while the channel is young.

---

## Development workflow (for people and coding agents)

This repo is set up so an AI coding agent can work in it safely and correct itself:

| Piece | Where | What it does |
|---|---|---|
| Project context | `CLAUDE.md` | Rules, commands and layout every agent session reads first |
| Permissions + hooks | `.claude/settings.json` | Allows tests/lint, asks before commit/push/install, denies secrets, curl, `rm -rf`; runs `verify --fast` after every edit and the full verify when the agent stops |
| Skills | `.claude/skills/` | `spec-first-feature` (ticket -> spec -> tests -> code -> verify) and `verify` (fix loop) |
| Specs | `specs/*.md` | What each feature must do; every scenario names its test. `tests/test_specs.py` fails if a spec and the tests drift apart |
| Decisions | `docs/adr/` | Why: stdlib core, autocomplete as demand signal, cross-channel normalisation, MIT |
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
  learn.py         title-feature lift on your own videos
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

## Licence

MIT - see `LICENSE`.
