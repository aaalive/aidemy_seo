# Quality baseline

Track these numbers over time; a PR should never make them worse.

| Date | Tests | Coverage | Mutation score (killed / killed+survived) | Notes |
|---|---|---|---|---|
| 2026-11-13 | 36 (+2 live) | 93.7% (gate 85%) | 55% (1585 / 2863) | first run |
| 2026-11-15 | 104 (+1 skipped, +2 live) | 96.88% (gate 85%) | not re-run (see below) | age-fair `learn` + `experiment assign/report` |
| 2026-11-18 | 261 (+2 live) | 98.43% (gate 85%) | not re-run; 85/85 planted bugs caught (see below) | `ab-pack`, `ab-results`, `series` (+ review changes), one-line CLI errors for every command, cleanup, grade ranges / school levels (series, ab-pack, title generator) |

## Surviving mutants by module (2026-11-13)
| Module | Survived | Priority |
|---|---|---|
| cli | 324 | low - mostly help/output text |
| youtube_api | 249 | low/medium - request parameter strings; pinned by `-m live` |
| titles | 169 | **high** - scoring weights and thresholds not pinned by tests |
| keywords | 123 | **high** - candidate filtering edge cases |
| descriptions | 88 | medium |
| schedule | 80 | medium |
| competitors | 77 | medium |
| aidemy_pub | 66 | medium |
| benchmark | 47 | low |
| learn | 42 | medium - verdict thresholds |
| text | 13 | low |

Next: raise titles + keywords first (`mutmut results`, `mutmut show <id>` per survivor).

## 2026-11-15: age-fair learning and title experiments

Specs: `specs/schedule-and-learning.md` (age-fair part), `specs/experiments.md`.
Decision: `docs/adr/0005-age-fair-views-per-day.md`.

### What was built
| Module | Change |
|---|---|
| `learn.py` | `views_per_day` (views / age, at least 1 day), inclusive age window, `now`; shared helpers `parse_time`, `age_days`, `check_age_window`, `with_age_metrics`, `videos_for_metric`, `coverage_line`. Named constants `SECONDS_PER_DAY`, `MIN_AGE_FOR_RATE_DAYS`, `HELPS_AT` (1.2), `HURTS_AT` (0.8). `feature_lift()` unchanged |
| `experiments.py` (new) | arm names for the 6 templates; `assign_arm` = sha256 of `json.dumps([experiment, key])`; JSON ledger (version 1, atomic write via temp file + `os.replace`, file mode kept); `report` with views per day, a percentile bootstrap CI (2,000 resamples, seeded) and the verdict winner / no winner yet / insufficient data (Bonferroni for 3+ arms) |
| `cli.py` | `learn --metric views_per_day --min-age --max-age --now`; `experiment assign`, `experiment report` (both with `--json`); argparse checks for ages (finite, >= 0), `--now`, `--confidence`, `--min-group`; `UsageError` -> exit 2 with a one-line message, no traceback |
| `titles.py` | refactor only: `MAX_TITLE_LEN` and `title_tags()` shared with experiments (behaviour unchanged, existing tests pass) |

Standard library only. One suppression was added: `# noqa: S311` on the seeded `random.Random`
in `experiments.seeded_rng` (statistics need a reproducible generator; nothing secret depends
on it). No `pragma: no cover`, no `type: ignore`. No existing test was changed or removed.

### Tests
| File | Tests | What |
|---|---|---|
| `tests/test_learn_age.py` (new) | 12 | age and one-day floor, left-out reasons, the age trap (helps -> hurts), inclusive window, input not changed, ISO parsing, invalid limits (incl. inf/nan) |
| `tests/test_experiments.py` (new) | 30 | pinned hash, PYTHONHASHSEED independence (subprocess), order/balance/independence, ledger (idempotent, changed arms, duplicate title, 7 kinds of broken file, atomic write on a simulated crash), report (age-fair, unmatched, min age), CI and verdicts (winner, no winner yet, Bonferroni, zero median -> "inf", ties, bad options) |
| `tests/test_integration_cli.py` | +25 (9 -> 34) | `learn` options end to end (10 incl. 7 bad-argument cases); full loop assign 17 -> publish -> report; 14 `experiment` error cases exit 2 with every file unchanged |
| `tests/fixtures/stats_age_confound.json` (new) | - | synthetic age trap + 4 edge cases (no date, bad date, future, no views) |

`tests/test_specs.py` passes: the 37 new `Test:` references (27 -> 64) all point to existing tests, and every new unit test is covered by a spec scenario.

### Coverage (2026-11-15)
| Module | Coverage |
|---|---|
| `learn.py`, `experiments.py` | 100% |
| `cli.py` | 96% (only old lines missed: `channels` network paths, `_default`, `__main__`) |
| Total | 96.88% (was 94.48% before this work) |

### Mutation testing
`mutmut run` was not re-run for this change (it was not installed in the verification
environment, and it writes a `mutants/` folder into the project). Instead, bugs were planted
by hand, one at a time, in a throwaway copy, and the tests run against each one:

| Area | Planted | Caught | Notes |
|---|---|---|---|
| `learn.py` age-fair code | 12 | 12 | 4 survived the first version of the tests (future boundary, stale stored `views_per_day`, min > max boundary, and a no-mutation test that passed for the wrong reason - it compared against shared fixture data other tests had already changed); the tests were fixed |
| `experiments.py` | 20 | 20 | ":" join instead of JSON, arm order, hash digits, no Bonferroni, `>=` vs `>`, tie-break, zero median, idempotency, duplicate titles, changed arms, temp file cleanup, file mode, title normalisation, duplicate stats titles, min group, percentile index, inf in JSON, long-title threshold, ledger version, lift threshold |
| the 2 fixes (day length, inf/nan) | 3 | 3 | |

Next: run `mutmut run` on `learn` and `experiments` and add them to the table above.

## 2026-11-18: title A/B packs, Test & Compare results, Shorts series

Specs: `specs/ab-testing.md`, `specs/series.md`. Decisions: `docs/adr/0007-title-ab-packs-fixed-margin-win-rate-weights.md`,
`docs/adr/0008-series-from-title-hashtags.md`.

### What was built
| Module | Change |
|---|---|
| `abtest.py` (new) | `ab-pack`: 3 titles per video from `TEMPLATES[1]/[0]/[3]` via `build_title` (66 chars), title hashtags without repeats (max 2), series hashtags (`#KlasseN`, `#Fach` of a series) never dropped, a variant that can't fit 66 chars is dropped with a warning (video kept while 2 titles fit), order by `--weights` from 5 decided tests; `ab-results`: exact `Decimal` shares, winner at margin >= 0.05, never evaluates a video on partial data, weights = wins / decided tests the variant was in, "not enough info" (null, keeps its default place) below 3 tests per variant (half up, 2 decimals) |
| `series.py` (new) | series "Fach Klasse N" from `#Fach #KlasseN` (2+ videos), the rest "not sorted" with a reason |
| `fileio.py` (new) | the batch CSV reader with the required columns as a parameter; `write_text_atomic` (the one atomic writer; new files get `new_file_mode` minus the umask, default 0666), `same_file` (input files are never overwritten); `CsvWarning.skipped_row` keyword-only |
| `batch.py` | refactor only: reads through `fileio.read_table` (behaviour and messages unchanged, all existing tests pass unchanged) |
| `titles.py` | `title_tags()` / new `grade_tag()`: a grade range ("Klasse 11-12" -> `#Klasse11-12`) or school level ("Q11" -> `#Q11`) is never turned into one `#KlasseN` - same rule as `series` (single grades unchanged, all existing tests pass unchanged) |
| `experiments.py` | refactor only: `save_ledger` writes through `fileio.write_text_atomic(..., new_file_mode=0o600)` - a new ledger stays private (all existing tests pass unchanged) |
| `cli.py` | `ab-pack`, `ab-results`, `series`; every error of every command is one line (files read via `fileio.read_input_*`, shape checks, `CommandFailed` exit 1 for failed API requests with the key hidden) (`OneLineErrorParser`, `PROG: error: MESSAGE (usage: PROG --help)`), exit 2, nothing written |

Standard library only, no new dependency. No `pragma: no cover`, no `type: ignore`. One
suppression: `import os  # noqa: F401` in `experiments.py`. The module no longer uses `os`, but
the existing test `test_ledger_write_is_atomic_and_readable` patches `experiments.os.replace` to
simulate a crash, and existing tests are not changed. The patch also hits the shared writer, so
the test still checks the real write. No existing test or fixture was changed.

### Tests
| File | Tests | What |
|---|---|---|
| `tests/test_abtest.py` (new) | 22 | templates/hashtags/66-char rule, series hashtags never dropped, v02-v04 keep question + why (search dropped with a warning), bad rows, weights order (min 5 decided) and validation, normal file permissions, input protection (path, `..`, symlink, hard link), crash while writing, share parsing, 0.05 boundary (float trap), half-up rounding, partial data never evaluated |
| `tests/test_series.py` (new) | 8 | subject/grade rules, grade ranges and school levels never guessed, real titles, grouping and sort, duplicate ids, JSON/text |
| `tests/test_title_tags.py` (new) | 17 | single grades unchanged; 6 range and 8 level spellings stay range / level and `series` reports them; unknown grade text gets no tag; `optimize_title`, `experiment assign` and `title --generate` keep them |
| `tests/test_fileio.py` (new) | 3 | `write_text_atomic` modes (0644 default, 0600 on request, existing mode kept, bytes as given), a new ledger is 0600 through the shared writer, `skipped_row` keyword-only |
| `tests/test_integration_errors.py` (new) | 53 | one test per command (19 test functions): missing file, folder, Latin-1, broken / wrong-shaped JSON, bad score, no API key, no `requests`, offline, timeout, HTTP 403 - always one line, key never printed; safety net; good input unchanged |
| `tests/test_integration_ab_series.py` (new) | 23 | the 3 commands end to end, results -> weights -> pack loop, 13 error cases, 6 one-line error checks (incl. `learn`, `experiment`) exit 2 with every file unchanged, installed executable |
| `tests/fixtures/ab_results.csv` (new) | - | 5 winners (= the minimum for weights), 2 inconclusive, exactly 0.05, percentages, 2-title tests (v02/v04 as ab-pack makes them), 1 variant only |

### Planted bugs (throwaway copy, one at a time, `PYTHONDONTWRITEBYTECODE=1`)
85 of 85 caught. Title generator: old first-number rule back, range cut to its first grade, levels not
recognised, en dash / "bis" / "und" missed, "5./6. Klasse" missed, "Jahrgangsstufe Q12" missed.
Grade ranges / levels: range cut to `#Klasse11` again, level taken as subject,
range counted as grade, range mapped to its first grade, `Q` + any digits (first survived: no test
pinned 1-2 digits - added), level regex too wide, unhelpful level reason, `ab-pack` cutting the range,
`ab-pack` dropping ranges/levels. One-line errors for every command: the reported `calibrate` crash back, a bad
score crashing, the API key printed (first survived: no test had an error text with the key -
added), long network message, no key check, no safety net, bundle / stats shape not checked,
network failure as exit 2, non-UTF-8 traceback, ledger folder crashing. Cleanup (shared writer, keyword-only flag): ledger mode not passed (new ledger
0644), `new_file_mode` ignored, `skipped_row` positional again, existing mode not kept, temp file
left after a crash. Fifth review (below 3 tests = unknown, not 0): unknown as 0 again, unknown
ranked last, all known ranked ignoring the unknown's place, `null` refused in the weights file,
"not enough info" not shown, a missing variant read as 0. Fourth review (3 tests per variant, one-line errors): minimum 2 / 4 instead of 3,
no minimum, reason not shown, argparse usage block back, handler errors with the usage block, no
usage pointer, wrong command name in the error. Third review (weight = wins / decided tests the variant was in): old denominator
(all decided tests), inconclusive tests counted, presence ignored, no evidence -> 1.0, `decided_with`
missing from JSON, old denominator in the text, 5-test minimum per variant instead of total,
banker's rounding. Second review (variant dropped instead of video skipped): need 3 titles again,
1-title video packed, any dropped variant skips the video, dropped variant not warned / not in
the report, 66 limit loosened, videos counted as rows / 3. First review: `#KlasseN` or the series `#Fach` droppable, series tags not
picked first, kept tags dropped anyway, weights applied below 5 / at 4 decided, old flat weights
format accepted, negative `decided`, new files 0600, existing mode not kept. First version: `>` instead of `>=`, float shares, 3 hashtags, no repeat check, lowest weight
first, banker's rounding, inconclusive counted as decided, broken row ignored, no share-sum check,
`--out` over the weights file, wrong template, output ignores the input delimiter, duplicate
video packed, hard link not detected, 1-video series, grade sorted as text, duplicate video
makes a fake series, `#Shorts` as subject.
