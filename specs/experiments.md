# Title template experiments

`learn` can only look back at titles that were chosen by hand, so it also picks up
the reasons they were chosen (a "question" title went on the topic you already expected to
do well) and when they were posted. An experiment removes both: before upload, each new
video is assigned a title template by a fixed hash instead of by choice. All arms are then
posted over the same weeks, so age and topic spread evenly across them, and the report compares
arms with the age-fair metric from schedule-and-learning.md.

Commands: `aidemy-seo experiment assign ...` and `aidemy-seo experiment report ...`.
Module: `src/aidemy_seo/experiments.py` (standard library only: `hashlib`, `json`, `os`,
`tempfile`, `datetime`, `statistics`, `random`, `math`).

## Requirements

### Arms
- Every template in `titles.TEMPLATES` MUST have exactly one stable arm name:
  `question` = "{x} – kannst du es erklären?", `einfach_musst` = "{x} einfach erklärt – das
  musst du wissen!", `einfach_endlich` = "{x} einfach erklärt – endlich verstanden!",
  `warum` = "Warum {x}? Einfach erklärt", `musst_du_wissen` = "{x}: Das musst du wissen!",
  `endlich` = "{x} – endlich verstanden!".
- An experiment MUST have at least 2 arms and MUST NOT repeat an arm. With no `--arm` on the
  first assign, all 6 templates are used. Fewer arms reach a result faster: each arm needs
  `--min-group` published videos.

### Deterministic assignment (hashlib)
- `assign_arm(experiment, key, arms)` MUST be
  `digest = hashlib.sha256(json.dumps([experiment, key], ensure_ascii=False).encode("utf-8"))`,
  `sorted(arms)[int(digest.hexdigest()[:16], 16) % len(arms)]`.
  - `hashlib`, not `hash()`: Python randomises `hash()` for strings on every run
    (PYTHONHASHSEED), so the same lesson could get a different arm tomorrow.
  - `json.dumps([...])` MUST be used instead of joining the strings with ":", so that
    `("a:b", "c")` and `("a", "b:c")` don't give the same hash.
  - Arms are sorted first, so `--arm a --arm b` and `--arm b --arm a` give the same result.
  - Using the experiment name in the hash keeps experiments independent: one lesson can land
    in different arms in different experiments.
- `key` identifies the video before it exists (e.g. the aidemy_pub lesson slug). It MUST be
  stripped of surrounding whitespace and MUST NOT be empty; it is case-sensitive.
- The arm MUST NOT depend on the keyword, the title, the time or anything else the user can
  change. Assignment MUST NOT re-draw an arm when the title comes out badly: a title over 66
  characters, or a second ":" from a "{x}:" template, is a warning in the output. The arm
  stays the same. (Re-drawing would bring back the bias this is meant to remove.)
- The title MUST be built with `titles.build_title(keyword, template, tags)` and the same
  `#Fach #KlasseN` tags as `optimize_title` (`--subject`, `--grade`). Both use the shared
  `titles.title_tags()` and `titles.MAX_TITLE_LEN` (66), so they can't drift apart.

### JSON ledger
- The ledger is one JSON file given as a path (e.g. `experiments.json`). It contains everything
  needed to recreate the report, and stores each arm's template text, so later edits to
  `TEMPLATES` don't change past experiments:
  ```json
  {"version": 1,
   "experiments": {
     "hook-2026-11": {
       "created_at": "2026-11-15T09:00:00+00:00",
       "arms": {"musst_du_wissen": "{x}: Das musst du wissen!",
                "question": "{x} – kannst du es erklären?"},
       "assignments": {
         "bio-kl10-gentechnik": {
           "arm": "musst_du_wissen", "keyword": "Gentechnik",
           "title": "Gentechnik: Das musst du wissen! #Biologie #Klasse10",
           "assigned_at": "2026-11-15T09:00:00+00:00"}}}}}
  ```
- A missing ledger file MUST be treated as empty and created on the first assign.
- Assign MUST be idempotent: assigning an existing key again returns the stored entry
  unchanged (same arm, title and `assigned_at`), even with a different `--keyword`. It is
  reported as "already assigned".
- The arms of an existing experiment MUST NOT change. `--arm` values that differ from the
  stored set are an error. (Changing arms would reshuffle every earlier assignment.)
- Two keys in one experiment MUST NOT get the same title (the report matches by title).
  A duplicate is an error.
- Writes MUST be atomic: write a temp file in the same folder, then `os.replace`. A failed
  or refused assign MUST leave the existing file byte-for-byte unchanged and no temp file
  behind. Output is UTF-8, `ensure_ascii=False`, `indent=2`, `sort_keys=True` (readable,
  stable diffs). An existing ledger keeps its file mode; a new one is private (0600), because
  it holds channel plans. Since 2026-11-18 the write goes through the shared
  `fileio.write_text_atomic(..., new_file_mode=0o600)`, the same code as the A/B outputs, which
  use normal permissions instead.
- A ledger that is not valid JSON, has a `version` other than 1, or a missing or wrong
  structure MUST be a clear error, never overwritten.
- `--now` (ISO 8601, same parsing as `learn`) sets `created_at` / `assigned_at`, so tests
  are deterministic. Default: current UTC time.

### Report
- `experiment report LEDGER STATS_JSON --experiment NAME` matches ledger entries to videos
  in the stats file by title. Titles are compared after collapsing whitespace, with case
  kept. Stats videos that are not in the ledger MUST be ignored (they weren't assigned).
- Ledger entries with no matching video MUST be listed as "not published yet or title
  changed". They MUST NOT be dropped without being listed. An entry whose title matches
  more than one stats video (e.g. a re-upload) MUST NOT be counted either. It is listed as
  "title matches N videos in the stats file".
- `experiment report` MUST NOT create a ledger: a missing ledger file is an error. A missing
  or unreadable stats file is an error too (exit 2, no traceback).
- Metric and age window follow schedule-and-learning.md (`with_age_metrics`). Report
  defaults: `--metric views_per_day`, `--min-age 7` (a Short's first days are noisy), no
  `--max-age`, `--min-group 5`, `--now` = current UTC time.
- Per arm the report MUST show: assigned, published (matched), used (in the window and with
  the metric), and the median of the metric.
- Every arm MUST also get a `lift` against the pooled videos of all other arms
  (`arm median / median of the rest`; if the rest's median is 0, the same `inf` / 1.0 rule as
  the CI below), using the `learn` thresholds (`learn.HELPS_AT`, `learn.HURTS_AT`): "helps" >= 1.2,
  "hurts" <= 0.8, otherwise "no clear effect". A verdict requires >= min_group used videos
  in the arm AND in the rest. Otherwise `lift` is None and the verdict is
  "not enough data (need N per arm)". This lift is a description only: it MUST NOT name
  a winner. Only the confidence-interval verdict below does that.
- The first text line MUST say how many assigned videos were used and the window, like `learn`.

### Confidence interval and verdict
Besides the per-arm lift, the report gives ONE verdict for the whole experiment:
`"winner"`, `"no winner yet"` or `"insufficient data"`, with the confidence intervals
that back it up.

- **insufficient data**: at least one arm has fewer than `--min-group` used videos. No CI is
  computed, `winner` is None, and the text names the arms that are short and how many
  videos each still needs.
- Otherwise the **leader** is the arm with the highest median. A tie goes to the arm name
  that comes first alphabetically, so the leader is deterministic.
- For the leader against EVERY other arm, the report MUST compute a bootstrap CI for the
  ratio `median(leader) / median(other)`:
  - `rng = experiments.seeded_rng(seed)` (a `random.Random`), with one rng per report and
    comparisons in arm-name order;
    `R = 2000` resamples. Each resample draws `len(arm)` values with replacement from each
    arm (`rng.choices`) and computes the ratio of the two medians.
  - If the other arm's resampled median is 0, the ratio is `math.inf` when the leader's
    median is > 0, and 1.0 when both are 0.
  - Percentile method: sort the R ratios and take `lo = r[floor(R * a / 2)]` and
    `hi = r[ceil(R * (1 - a / 2)) - 1]`, with `a = 1 - level`.
  - Bonferroni: with k arms the leader is compared k-1 times, so each comparison uses
    `level = 1 - (1 - confidence) / (k - 1)`. With 2 arms that is simply `confidence`.
    Otherwise, the more arms there are, the more likely a winner is declared by chance.
- **winner**: every comparison has `lo > 1.0`, checked on the unrounded bound. The leader
  beats every other arm at the adjusted level, and the report names the leader as the
  winner. The text adds that this is only trustworthy if the number of videos per arm was
  fixed in advance.
- **no winner yet**: enough data, but at least one interval includes 1.0. The text names
  the leader, the arm it has not yet beaten, and that arm's interval.
- Options: `--confidence` (default 0.95, must be strictly between 0 and 1), `--seed`
  (default 0) and `--min-group` (default 5, at least 1).
  The same inputs and seed MUST give the same intervals and verdict. Tests MUST check
  properties (deterministic, `lo <= ratio <= hi`, the verdict), NOT exact interval numbers,
  so they pass on every Python version in CI (3.10 / 3.12 / 3.13).
- An infinite bound MUST be written as the string `"inf"` in `--json` (plain `json.dumps`
  would write `Infinity`, which is not valid JSON) and as `inf` in the text.
- Known limit (the README MUST say this): looking at the report every day and stopping as
  soon as it says "winner" makes a false winner more likely than 1 - confidence. Decide the
  number of videos per arm in advance, or treat an early "winner" as provisional.
- `--json` MUST return `{"experiment", "metric", "min_age", "max_age", "now", "confidence",
  "seed", "verdict", "winner", "leader", "comparisons": [{"arm", "vs", "ratio", "level",
  "ci_low", "ci_high"}], "arms": [...], "unmatched": [...]}`, plus `"min_group"`,
  `"assigned"`, `"used"` and `"left_out"` (counts by reason, like `learn`). In the
  "insufficient data" case `winner` and `leader` are null and `comparisons` is empty.
- An unknown experiment name MUST be an error that lists the experiments in the ledger.

### CLI errors
- Bad input MUST exit with code 2 and a one-line message on stderr (since 2026-11-18 the only
  line: `PROG: error: MESSAGE (usage: PROG --help)`, no usage block),
  no traceback, ledger unchanged. This covers: an unknown arm, fewer than 2 arms, changed
  arms, a duplicate title, an empty key or keyword, a bad or missing ledger, an unknown
  experiment, a bad `--now` or age value (incl. `inf`/`nan`), `--confidence` not strictly
  between 0 and 1, `--min-group` < 1, and a missing or unreadable stats file.

## Scenarios

### Arms and assignment
- Given `titles.TEMPLATES`, then every template has exactly one arm name and every name maps
  back to it. Test: tests/test_experiments.py::test_every_template_has_one_arm_name
- Given experiment "hook-2026-11", key "bio-kl10-gentechnik" and arms question +
  musst_du_wissen, then the arm is "musst_du_wissen" (sha256 prefix 3e1ea3cee164415a), on
  every call. Test: tests/test_experiments.py::test_assign_arm_is_deterministic_and_pinned
- Given the same inputs in two Python processes with different PYTHONHASHSEED, then both
  return the same arm. Test: tests/test_experiments.py::test_assign_arm_ignores_pythonhashseed
- Given arms in a different order, then the arm is the same.
  Test: tests/test_experiments.py::test_assign_arm_order_of_arms_does_not_matter
- Given 600 keys "lesson-0".."lesson-599" and 3 arms, then every arm gets 160-240 of them.
  Test: tests/test_experiments.py::test_assign_arm_is_roughly_balanced
- Given the same key in "hook-2026-11" and "hook-2026-12", then the arm is "musst_du_wissen"
  in one and "question" in the other. Over 200 keys the two experiments disagree at least
  once. Test: tests/test_experiments.py::test_experiments_are_independent
- Given an empty key, one arm, a repeated arm or an unknown arm name, then assign raises.
  Test: tests/test_experiments.py::test_assign_rejects_bad_key_and_arms
- Given a keyword so long that the title is over 66 characters, or a keyword with ":" on a
  "{x}:" arm, then the arm is the hashed one and a warning is returned.
  Test: tests/test_experiments.py::test_assign_never_redraws_for_long_or_colon_titles

### Ledger
- Given no ledger file, when a key is assigned twice (the second time with another
  keyword), then the file exists, holds one entry and both calls return the same arm, title
  and assigned_at. Test: tests/test_experiments.py::test_ledger_assign_is_idempotent_and_persists
- Given an experiment created with arms question + warum, when assign is called with arms
  question + endlich, then it raises and the file is byte-for-byte unchanged.
  Test: tests/test_experiments.py::test_ledger_rejects_changed_arms
- Given two keys that would produce the same title, then the second assign raises and the
  file is unchanged. Test: tests/test_experiments.py::test_ledger_rejects_duplicate_title
- Given a ledger that is not JSON, or has version 2, then loading raises and the file is not
  overwritten. Test: tests/test_experiments.py::test_ledger_bad_file_is_an_error_and_untouched
- Given a successful assign, then no temp file is left in the folder and the JSON is
  sorted, indented and keeps "ä" unescaped.
  Test: tests/test_experiments.py::test_ledger_write_is_atomic_and_readable
- Given umask 022 and a new ledger, then its mode is 0600 (the A/B outputs would be 0644), and
  `save_ledger` calls `fileio.write_text_atomic` with `new_file_mode=0o600`.
  Test: tests/test_fileio.py::test_new_ledger_is_private_through_the_shared_writer

### Report
- Given 2 arms with 3 published videos each, then both arms say "not enough data (need 5
  per arm)" with lift None, and the verdict is "insufficient data" with winner None and no
  comparisons. Test: tests/test_experiments.py::test_report_insufficient_data_per_arm
- Given now = 2026-11-15, arm question with 6 videos 10 days old at 300 views (30 per day)
  and arm musst_du_wissen with 6 videos 90 days old at 900 views (10 per day), then with
  views_per_day question "helps" (lift 3.0) and musst_du_wissen "hurts", and the verdict
  is "winner" = question. With `metric="views"` the verdicts flip and the winner is
  musst_du_wissen (the age trap this feature exists for).
  Test: tests/test_experiments.py::test_report_is_age_fair
- Given a ledger entry with no matching title, one whose title matches 2 stats videos, and
  a stats video not in the ledger, then both entries are listed under unmatched with their
  reason and the other video is not counted in any arm.
  Test: tests/test_experiments.py::test_report_lists_unmatched_and_ignores_unassigned_videos
- Given a video 3 days old, then it is published but not used (default --min-age 7).
  Test: tests/test_experiments.py::test_report_default_min_age_skips_fresh_videos

### Confidence interval and verdict
- Given two samples and seed 0, then the bootstrap CI is the same on every call, contains
  the observed ratio, and is wider at 0.99 than at 0.95.
  Test: tests/test_experiments.py::test_bootstrap_ci_is_deterministic_and_contains_ratio
- Given question at [22, 25, 28, 30, 31, 33, 36, 40] and musst_du_wissen at
  [8, 9, 10, 10, 11, 12, 13, 15] views per day, then the verdict is "winner" = question with
  ci_low > 1.0. Test: tests/test_experiments.py::test_report_clear_difference_is_a_winner
- Given question at [10, 14, 18, 22, 26, 30] and musst_du_wissen at [9, 13, 17, 21, 25, 29],
  then the verdict is "no winner yet", the leader is question and its interval includes
  1.0. Test: tests/test_experiments.py::test_report_overlapping_arms_is_no_winner_yet
- Given 3 arms where the leader clearly beats musst_du_wissen but not warum (close medians),
  then the verdict is "no winner yet", each comparison uses level 0.975 (Bonferroni), and
  the text names warum as the arm not yet beaten.
  Test: tests/test_experiments.py::test_report_winner_must_beat_every_arm_with_bonferroni
- Given an arm whose views_per_day are all 0, then the report does not crash, ci_high is
  "inf" in JSON, and the JSON passes `json.loads`.
  Test: tests/test_experiments.py::test_report_zero_median_gives_inf_bound_and_valid_json
- Given two arms with equal medians (also both all 0), then the leader is the
  alphabetically first arm name and the verdict is "no winner yet".
  Test: tests/test_experiments.py::test_report_tie_picks_leader_by_name_and_no_winner
- Given an unknown experiment, confidence 0 / 1 / 1.5 / NaN, min_group 0, min_age > max_age,
  or a missing ledger with must_exist, then report / load_ledger raise a clear error.
  Test: tests/test_experiments.py::test_report_rejects_bad_options

### CLI
- Given `experiment assign LEDGER --experiment hook-2026-11 --key bio-kl10-gentechnik
  --keyword Gentechnik --subject Biologie --grade "Klasse 10" --arm question --arm
  musst_du_wissen --now 2026-11-15T09:00:00Z`, then the output names arm musst_du_wissen and
  the title "Gentechnik: Das musst du wissen! #Biologie #Klasse10". Then
  `experiment report LEDGER STATS --experiment hook-2026-11 --now ...` prints the verdict
  line, and `--json` works for both. With 16 more lessons assigned through the CLI and
  published with ~30 views per day on question and ~10 on musst_du_wissen, the report says
  "16 of 17 assigned videos used" and "WINNER = question"; with `--min-group 10` it says
  "insufficient data". Test: tests/test_integration_cli.py::test_experiment_assign_and_report_cli
- Given changed arms, an unknown arm, an empty key, a broken ledger, an unknown experiment,
  `--confidence 1.5` / `high` / `nan`, `--min-group 0` / `2.5`, `--min-age inf`, a bad `--now`,
  a missing stats file
  or a missing ledger, then exit code 2, one message on stderr, no traceback, and no file
  in the folder changed.
  Test: tests/test_integration_cli.py::test_experiment_cli_errors_exit_2
