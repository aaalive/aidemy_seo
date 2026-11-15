# Quality baseline

Track these numbers over time; a PR should never make them worse.

| Date | Tests | Coverage | Mutation score (killed / killed+survived) | Notes |
|---|---|---|---|---|
| 2026-11-13 | 36 (+2 live) | 93.7% (gate 85%) | 55% (1585 / 2863) | first run |
| 2026-11-15 | 104 (+1 skipped, +2 live) | 96.88% (gate 85%) | not re-run (see below) | age-fair `learn` + `experiment assign/report` |

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
