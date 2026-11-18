# Title A/B tests (YouTube "Test & Compare")

Status: **implemented** (`src/aidemy_seo/abtest.py`, tests in `tests/test_abtest.py` and
`tests/test_integration_ab_series.py`). Decision: ADR 0007.

Need: YouTube Studio's **Test & Compare** tests up to 3 titles on the *same* video and
reports each title's share of the watch time. That removes the topic and age bias
`learn` has, and it needs no waiting for 5 videos per arm like `experiment`. Two steps were
missing: writing 3 good titles for many videos at once, and learning from the results which
title style wins, so the next pack puts that style first.
Real example: the titles in `tests/fixtures/titles_to_fix.csv` (her channel, with a keyword per
video) and the results shape in `tests/fixtures/ab_results.csv`.

Commands:
- `aidemy-seo ab-pack PATH_TO_CSV --out PATH_TO_FILE [--weights PATH_TO_JSON]`
- `aidemy-seo ab-results PATH_TO_CSV --weights PATH_TO_JSON`

Module: `src/aidemy_seo/abtest.py`. Standard library only (`csv`, `json`, `decimal`), no new
dependency. It reuses `titles.TEMPLATES`, `titles.build_title`, `titles.MAX_TITLE_LEN`,
`text.hashtags`, `text.fold` and the CSV reader from the batch analysis (moved to
`src/aidemy_seo/fileio.py`, unchanged behaviour). Cost: **0 API units**, no network.

## Requirements

### Variants (the same 3 for every video)
| Variant | Template (`titles.TEMPLATES` index) | Why |
|---|---|---|
| `search` | `{x} einfach erklärt – das musst du wissen!` (1) | the words people type into search |
| `question` | `{x} – kannst du es erklären?` (0) | a question hook |
| `why` | `Warum {x}? Einfach erklärt` (3) | a "why" hook |

- `{x}` is the row's `keyword` (spaces collapsed). The templates MUST come from
  `titles.TEMPLATES`, not from a copy, so they can't drift apart.
- Every title MUST be built with `titles.build_title` and MUST be at most 66 characters.
- **Hashtags:** taken from the row's current `title`. Each hashtag is used once (compared after
  `text.fold`, so case and umlauts are ignored and the first spelling is kept), in title order,
  **at most 2**. `#Biologie #biologie #Klasse9 #Zellbiologie` gives `#Biologie #Klasse9`. A
  title without hashtags gives titles without hashtags.
- **Grade tags are never dropped or changed:** `#KlasseN`, a range `#Klasse11-12` (kept as
  written, never cut to `#Klasse11`) and a level (`#Q11`, `#Oberstufe`), see specs/series.md. They
  are picked for the 2 slots after the series hashtags.
- **The series hashtags are never dropped** (2026-11-18, requested after v03 lost `#Klasse11`).
  Every `#KlasseN` is a series hashtag. In a series title (`series.series_key`:
  one `#Fach` + one `#KlasseN`), so is its `#Fach`. A new title without either one would take
  the video out of its series (specs/series.md). The series hashtags are picked first for the 2
  slots, so `#Shorts #Biologie #Klasse9` gives `#Biologie #Klasse9`, not `#Shorts #Biologie`.
- When a title is over 66 characters, the other hashtags are dropped from the end. A title is
  never cut, and **the 66 limit always holds**.
- **A variant that still doesn't fit is dropped on its own (2026-11-18). The video is not
  skipped.** It keeps the variants that fit, because 2 titles are still a valid Test & Compare
  test. Each dropped variant gives a warning on the video's line (not a skipped row). Example:
  `search variant dropped - the search title is 67 characters with #Biologie #Klasse11 (max
  66) - series hashtags are never dropped; testing question, why`. Without series hashtags, the
  reason is `... even without hashtags (max 66)` (a keyword longer than 27 characters for
  `search`). On the real fixture this drops the search title of v02, v03 and v04 (67-68
  characters), and they are tested with question + why.
- Only when **fewer than 2** variants fit (`MIN_TITLES`) is the video skipped: one title is no
  test. The warning names every reason: `skipped - a test needs at least 2 titles, only 1 fits
  66 characters: the search title is 81 characters ...; the question title is 67 characters
  ... - use a shorter keyword`.

### `ab-pack`
- Input CSV: UTF-8 (BOM allowed), delimiter `,` `;` or tab found from the header (same
  reader and the same file-level errors as `analyze-batch`). Required columns: `video_id`,
  `title`, `keyword`. Other columns are ignored with one warning.
- A row is skipped with a warning naming its line when: it has the wrong number of fields,
  `video_id` is empty, the `video_id` was already on an earlier line, `title` is empty,
  `keyword` is empty, or fewer than 2 variants fit 66 characters (see above). Fully blank lines
  are ignored.
- Output CSV (`--out`): header `video_id,variant,title,length`, then 3 rows per video (2 when
  a variant was dropped). The remaining 2 keep the order (default or weights). Videos
  keep the input order. `length` = characters of the title (Unicode code points, hashtags
  included). The output uses the input's delimiter and, if the input had one, its BOM, so
  it opens the same way the input did.
- Order of the 3 rows per video: without `--weights`, `search, question, why`. With
  `--weights` from **at least 5 decided tests** (`MIN_DECIDED`), **highest weight first**. Equal
  weights keep the default order (stable sort). A variant with **not enough info** (weight
  `null`) is not ranked: it keeps its **default place**, and the variants with a weight are
  ranked highest first in the other places. Example: `search null, question 0.2, why 0.6` gives
  `search, why, question`, not `why, question, search`. With fewer than 5 decided tests, the default
  order is used and the text says why: `order: search, question, why (default - only 4 decided
  tests in w.json, the weights count from 5)`. 1-4 tests are too few to trust a style.
- `--weights` JSON: `{"decided": 5, "weights": {"search": 0.2, "question": 0.2, "why": 0.6}}`
  (the file `ab-results` writes). A weight can be `null` (not enough info), and a missing
  variant means the same. These stop the command
  (exit 2), so a typo is never silently ignored:
  - other or missing top-level keys (e.g. a flat `{"why": 1}` without `decided`);
  - `decided` that is not a whole number >= 0;
  - an unknown variant (e.g. the typo `qestion`);
  - a weight that is not a finite number (`"high"`, `true`, `NaN`);
  - a missing or unreadable file.
- Text output: a summary line (`wrote 27 titles for 10 of 10 videos to pack.csv (0 skipped, 3
  variants dropped)`), the order used (with the weights and the decided tests), the `TITLES` table and
  `WARNINGS` (`(none)` when empty).
- `--json`: `{"file", "out", "order", "weights", "weights_file", "decided", "weights_applied",
  "videos", "packed", "skipped", "dropped": [{"line", "video_id", "variant", "reason"}], "rows":
  [{"video_id", "variant", "title", "length"}],
  "warnings": [{"line", "message"}]}`. Without `--weights`, `weights`, `weights_file` and
  `decided` are `null` and `weights_applied` is `false`.

### `ab-results`
- Input CSV: same reader. Required columns: `video_id`, `variant`, `watch_time_share`.
  `title` and `length` are accepted without a warning, so the `ab-pack` file with a share
  column added works as is. Any other column is ignored with a warning.
- `variant` MUST be `search`, `question` or `why` (case does not matter).
- `watch_time_share`: a share from 0 to 1 (`0.42`), a German decimal comma (`0,42`) or a
  percentage (`42%`, `42,5 %`). It is parsed as an exact `Decimal`, so `0.45 - 0.40` is exactly
  `0.05` (with floats it is `0.0499…` and the winner would be lost). A number over 1 without
  `%` (`45`) is an error, not 45%. Empty, not a number, `nan`, `inf`, below 0 or above 1 is an
  error.
- A bad row (wrong number of fields, empty `video_id`, unknown variant, bad share) is skipped
  with a warning naming its line.
- **A video is never evaluated on partial data.** It is listed under `NOT EVALUATED` with
  the reason when:
  1. one of its rows was skipped (the skipped variant could be the real winner). For a row
     with the wrong number of fields, the video is taken from its `video_id` field when the
     row has one;
  2. a variant appears twice;
  3. it has only 1 variant (Test & Compare compares 2 or 3);
  4. its shares add up to more than 1.01 (100% plus 1% for YouTube's rounding), which usually
     means a percentage and a share were mixed.
- **Winner rule:** sort the shares of a video from high to low. If
  `top - second >= 0.05`, the top variant is the **winner**. Otherwise the test is
  **inconclusive** (this includes a tie at the top).
- **Weights:** for each variant, `wins / decided tests the variant was in` (2026-11-18).
  - Decided tests are the tests with a winner. Inconclusive and not-evaluated videos don't count.
  - A test without the variant (e.g. the search title was dropped for length, v02-v04) does
    **not** count against it: it could not win there.
  - Example: search is in a1-a3 and wins 2. Why wins a3 and a4 (a4 is question + why).
    Then search is 2/3 = 0.67, not 2/4, and why is 2/4 = 0.5.
  - **A variant needs at least 3 decided tests (`MIN_TESTS_PER_VARIANT`)** before its weight
    counts (2026-11-18). Below that it is **unknown, not a loser**: the weight is `null` in the
    file (`None` in Python), not 0. 2 wins in 2 tests must not count as 1.0, and must not count
    as 0.0 either, which would rank the variant last. The text says `search    not enough info
    (2 of 2 - needs 3 tests)`. A variant that was in no decided test shows `not enough info
    (0 of 0 - needs 3 tests)`. 0 wins in 3 or more tests is a real `0.00`.
  - Rounded to **2 decimals**, half up (`1/8 = 0.125 -> 0.13`, not Python's `round` -> 0.12).
  - All 3 variants are always written.
- The 5-test minimum is about the **total** decided tests, as before. With fewer than 5, the
  text says `only 4 decided tests - ab-pack keeps the default order until 5 are decided`.
- `--weights PATH` is **written** (atomically, JSON with indent 2:
  `{"decided": N, "weights": {...}}`, the weights in the order `search, question, why`). It is
  the `--weights` input of the next `ab-pack`. The weights are always written, also with fewer
  than 5 decided tests. `ab-pack` decides whether they count, so nothing is lost while the tests
  add up.
- Text output: a summary line (`8 videos in ab_results.csv: 5 winners, 2 inconclusive, 1 not
  evaluated (winner = top share - second share >= 0.05)`), then the sections `TESTS` (top,
  second, margin), `NOT EVALUATED`, `WARNINGS` and `WEIGHTS`.
- `--json`: `{"file", "weights_file", "videos", "decided", "inconclusive", "tests":
  [{"video_id", "result", "winner", "margin", "shares": {variant: share}}], "not_evaluated":
  [{"video_id", "reason"}], "wins", "decided_with", "weights", "warnings"}`. `decided_with` = the
  decided tests each variant was in (the denominator of its weight). `winner` is `null` when the test is
  inconclusive.

### Input files are never overwritten
- `ab-pack` MUST refuse (exit 2, nothing written) an `--out` that is the input CSV or the
  `--weights` file. `ab-results` MUST refuse a `--weights` that is its input CSV. "Is" means
  the same file however it is written: the same resolved path (`./x.csv`, `sub/../x.csv`, a
  symlink) or the same file on disk (a hard link, or another letter case on a
  case-insensitive disk).
- An `--out` that is a directory, or in a folder that does not exist, is an error (exit 2).
- Outputs are written atomically (temp file next to the target, then `os.replace`), so a crash
  leaves the old file intact and no temp file. A new file gets normal permissions, like any
  file the user creates (0666 minus the umask, usually 0644 - 2026-11-18, not "only the user").
  An existing file keeps its mode. The input files are only read.
- All errors: exit code 2, **exactly one line** on stderr, no traceback, nothing on stdout:
  `aidemy-seo ab-pack: error: MESSAGE (usage: aidemy-seo ab-pack --help)`. There is no usage
  block before it (2026-11-18). This holds for every command, see specs/cli-errors.md. `--help`
  still shows the full usage.

### Shared helpers (`fileio.py`)
- `write_text_atomic(path, text, *, new_file_mode=0o666)` is the one atomic writer: the A/B
  outputs and the experiment ledger (`new_file_mode=0o600`) both use it. A new file gets
  `new_file_mode` minus the umask, and an existing file keeps its mode. Line ends are written
  as given (`\n`), and no temp file is left.
- `CsvWarning(line, message, *, skipped_row=False)`: `skipped_row` is keyword-only, so every
  caller writes `skipped_row=True` and a bare `True` is refused.

## Decisions (interpretation of the request, 2026-11-18)
1. "3 title alternatives per row with a keyword: search, question and why (templates 1, 0,
   3)" means `TEMPLATES[1]` = search, `TEMPLATES[0]` = question, `TEMPLATES[3]` = why, in
   that default order.
2. "Tags: title hashtags, should not repeat itself, maximum 2" means the hashtags of the
   current title, without repeats, at most 2, with the series hashtags picked first.
3. A title that can't fit 66 characters is never cut. Only that variant is dropped, with a
   warning, and the video is tested with the other 2 (requested, 2026-11-18). A video is only
   skipped when fewer than 2 titles fit.
4. "Decided tests" means tests with a winner. Inconclusive tests count for no variant.
   Confirmed.
5. Shares are accepted as fractions or percentages, and parsed exactly. Confirmed.
6. The output CSV uses the input's delimiter. Confirmed. New files get normal permissions,
   not 0600 (changed on request, 2026-11-18).
7. `#KlasseN` is never dropped (requested, 2026-11-18). Since a series needs `#Fach` as well,
   the `#Fach` of a series title is never dropped either. When a variant can't fit 66
   characters with them, that variant is dropped (see 3).
8. Weights change the order only from 5 decided tests on (requested, 2026-11-18). The count
   is stored in the weights file, so `ab-pack` can check it.
9. Weight = wins / decided tests **the variant was in**, not / all decided tests (requested,
   2026-11-18). With variants dropped for length, the old rule counted a test the variant could
   not win as a loss. The 5-test minimum stays on the total.
10. A variant needs at least 3 decided tests before its weight counts (requested, 2026-11-18).
    Below 3 it is "not enough info" (`null`), not 0: unknown is not a loser. In `ab-pack` it
    keeps its default place (requested the same day, replacing "weight 0").
11. Errors are one line, without the usage block, for every command (requested, 2026-11-18).
    The line ends with `(usage: PROG --help)`: it says where the usage is, and it keeps the
    existing tests that look for `usage:` valid.

## Scenarios

### ab-pack
- Given the keyword "Mitose" and the title "Mitose: Das musst du wissen! #Biologie #Klasse9",
  then the 3 titles are exactly `build_title` of templates 1, 0 and 3 with `#Biologie
  #Klasse9`, all at most 66 characters.
  Test: tests/test_abtest.py::test_pack_titles_use_search_question_why_templates
- Given the real title "🔥🔥 Mitose einfach erklärt!!! #Biologie #biologie #Klasse9
  #Zellbiologie", then the hashtags are `#Biologie #Klasse9` (no repeat, at most 2), and no
  title has `#Zellbiologie`. Given a title without hashtags, then the titles have none.
  Test: tests/test_abtest.py::test_pack_hashtags_unique_and_at_most_two
- Series hashtags are picked first and kept:
  - Given `#Shorts #Biologie #Klasse9`, then `#Biologie #Klasse9`. Given `#Shorts
    #YouTubeShorts #Klasse5`, then `#Klasse5` is kept.
  - Given the real v06 "Atmung", then 65 characters with both hashtags. Exactly 66 characters
    with both fit.
  - Given `#Klasse5 #Shorts` and a long keyword, then only `#Shorts` is dropped.
  - Every packed title of the real fixture has the same `series_key` as its video's current
    title.
  Test: tests/test_abtest.py::test_pack_never_drops_series_hashtags
- **Must catch:** given `#Biologie #Klasse11-12`, then the new titles carry `#Klasse11-12`, never
  `#Klasse11`, which would change the video's grade. The search title (68 characters with both)
  drops `#Biologie`, which is not a series hashtag here, and keeps the range. Given `#Shorts #Q11`,
  then `#Q11` is kept and `#Shorts` is dropped first. Given `#Oberstufe #Biologie #Klasse11`, then
  the 2 slots go to `#Biologie #Klasse11`.
  Test: tests/test_abtest.py::test_pack_keeps_grade_ranges_and_levels
- **Must catch (real v02-v04):** "Raubtiere" / "Neobiota" with `#Biologie #Klasse11` and
  "alleine leben" with `#Ethik #Klasse5` make search titles of 68 / 67 / 68 characters.
  - Only the search variant is dropped, with a warning on lines 3 / 4 / 5 (not a skipped row).
  - The video keeps question + why, both with their series hashtags and at most 66
    characters. It does NOT get a title without `#KlasseN`, and it is NOT skipped.
  - The pack has 27 titles for 10 of 10 videos, and the report lists the 3 dropped variants.
  - With the order why, search, question, the 2 remaining titles come as why, question.
  Test: tests/test_abtest.py::test_pack_drops_only_the_variant_that_does_not_fit_v02_v04
- Given "Neobiota" with `#Biologie #Zellbiologie` (not a series title), then the search title
  drops `#Zellbiologie` to fit. Given a keyword that makes exactly 66 characters, then it
  fits. One character more drops the search variant ("67 characters even without hashtags").
  Given the 42-character keyword "Neobiota & Selbstregulation in Ökosystemen", then only
  `why` fits, so the video is skipped (fewer than 2).
  Test: tests/test_abtest.py::test_pack_drops_hashtags_to_fit_66_and_skips_when_fewer_than_2_titles_fit
- Given `tests/fixtures/titles_to_fix.csv`, then 27 rows (7 videos × 3 + v02-v04 × 2) in input
  order with `length == len(title)`. The warnings are "ignored columns: description, tags" and
  the 3 dropped search variants. Given rows with no video_id, a repeated video_id, no keyword,
  no title, or the wrong number of fields, or only 1 fitting title, then each is skipped with
  its line and only the good video is packed.
  Test: tests/test_abtest.py::test_make_pack_rows_columns_and_warnings
- Given weights `{"search": 0.2, "question": 0.2, "why": 0.6}` from 5 decided tests, then
  every video's rows come in the order why, search, question, and the videos keep the input
  order. Equal weights keep the default order.
  Test: tests/test_abtest.py::test_pack_order_follows_weights
- Given weights from 4 decided tests (or 0), then the default order, with the reason in the
  text. The weights are still in the JSON. Given 5, then highest weight first (boundary).
  Test: tests/test_abtest.py::test_pack_weights_need_5_decided_tests
- Given `{"decided": 7, "weights": {"why": 1}}`, then search and question are 0. Given
  broken JSON, a list, the old flat format without `decided`, extra keys, `decided` 4.5 / -1
  / true, the typo `qestion`, `"high"`, `true`, `NaN` or a missing file, then an error.
  Test: tests/test_abtest.py::test_load_weights_rejects_bad_files
- Given a `;` input with a BOM, then the output is `;` with a BOM and the input is unchanged.
  Given `--out` equal to the input (the same path, `sub/../in.csv`, a symlink, a hard link),
  equal to the weights file, a directory, or in a missing folder, then an error. No input
  changes and no stray file is left.
  Test: tests/test_abtest.py::test_ab_pack_writes_csv_like_input_and_never_overwrites_inputs
- Given umask 022, then a new pack CSV and a new weights file are 0644 (not 0600). With umask
  002, then 0664. Given an existing 0600 file, then it stays 0600.
  Test: tests/test_abtest.py::test_outputs_get_normal_permissions
- Given a crash between writing and replacing, then the old output is intact and no temp file
  is left. Test: tests/test_abtest.py::test_ab_pack_crash_while_writing_keeps_the_old_output
- Given umask 022, then `write_text_atomic` makes 0644 by default and 0600 with
  `new_file_mode=0o600`. Given an existing 0640 file, then it stays 0640. The text is written
  byte for byte, and no temp file is left.
  Test: tests/test_fileio.py::test_write_text_atomic_modes
- Given `CsvWarning(3, "...", True)`, then a TypeError. `skipped_row=True` works, and the default
  is False. Test: tests/test_fileio.py::test_csv_warning_skipped_row_is_keyword_only

### ab-results
- Given `0.42`, ` 0,42 `, `42%`, `42,5 %`, `0`, `1`, `100%`, then exact shares. Given ``,
  `%`, `abc`, `nan`, `inf`, `45`, `-0.1`, `101%`, then an error with the reason.
  Test: tests/test_abtest.py::test_parse_share_accepts_fractions_commas_and_percent
- Given 0.45 / 0.40 / 0.15, then search wins with a margin of exactly 0.05 (the float trap).
  Given 0.449 / 0.40, a 0.52 / 0.48 two-title test, or a tie at the top, then inconclusive.
  Test: tests/test_abtest.py::test_decide_winner_margin_boundary
- Given 1 and 2 wins of 3, then 0.33 and 0.67. Given 1 of 8, then 0.13 (half up). Given 0
  decided tests, then all 0.0. Test: tests/test_abtest.py::test_compute_weights_rounding
- **Must catch:** search is in a1-a3 and wins a1 + a2. Why wins a3 and a4 (question + why,
  search dropped), and a5 is inconclusive. Then search is 0.67 (2 of 3, not 2 of 4), why 0.5
  (2 of 4) and question 0.0 (0 of 4). The text shows `(2 of 3)` and the JSON `decided_with`.
  The real fixture gives `decided_with` search 4, question 5, why 4.
  Test: tests/test_abtest.py::test_weights_count_only_tests_the_variant_was_in
- **Must catch:** search wins 2 of 2 tests and why wins 3 of 5.
  - Search gets `None` / "not enough info" (below 3 tests), not 1.0 and not 0.0. The text says
    `not enough info  (2 of 2 - needs 3 tests)`, and the JSON weight is `null`.
  - Exactly 3 tests count: 2 of 3 gives 0.67.
  - A variant in no decided test shows `(0 of 0 - needs 3 tests)`.
  - `compute_weights` applies the same minimum, and 0 wins in 3 tests is a real 0.0.
  Test: tests/test_abtest.py::test_weights_need_3_tests_per_variant
- **Must catch:** with `search null, question 0.2, why 0.6`, the order is `search, why,
  question`. Search keeps its default first place and is not ranked last. A real `0.0` is
  ranked last. An unknown question or why keeps its place too, and all unknown gives the
  default order.
  - End to end: ab-results writes `"search": null`. ab-pack then orders v01 search, why,
    question and v02 why, question (search was dropped there). The order line says `search (not
    enough info)` and "not enough info keeps the default place".
  Test: tests/test_abtest.py::test_unknown_variant_keeps_its_default_place
- Given `tests/fixtures/ab_results.csv` (v02 and v04 are 2-title tests, as ab-pack makes them),
  then:
  - the winners are v02 why, v05 search (margin exactly 0.05), v06 why (percentages), v08 why
    and v10 question (a 2-title test);
  - v04 and v07 are inconclusive, and v09 (1 variant) is not evaluated;
  - 5 decided tests give the weights search 0.25 (1 of 4: v02 had no search title), question
    0.2 (1 of 5), why 0.75 (3 of 4: v10 had no why title);
  - the JSON has exactly the keys above.
  Test: tests/test_abtest.py::test_read_results_fixture
- Given a video whose third row has the share "lots", then it is not evaluated, although its
  2 other rows are valid. The same applies to a row with the wrong number of fields, an
  unknown variant, a variant twice, and shares adding up to 1.15. Given `Search` / `WHY`,
  then they are valid. Given an ab-pack file with a share column, then only `notes` is an
  ignored column (nearest legitimate case).
  Test: tests/test_abtest.py::test_read_results_never_guesses_a_video
- Given the fixture, then the weights file is `{"decided": 5, "weights": {"search": 0.25,
  "question": 0.2, "why": 0.75}}`, `load_weights` reads it back, and the input is unchanged.
  Given `--weights` equal to the input CSV, then an error and the input is unchanged. Given only
  inconclusive tests, then all weights are 0 (`decided` 0) and the text says ab-pack keeps the
  default order.
  Test: tests/test_abtest.py::test_ab_results_writes_weights_and_never_overwrites_input

### CLI
- `ab-pack` on the fixture writes 28 CSV lines for 10 videos. v02-v04 have question + why,
  with a "search variant dropped" warning. `ab-results` on the results fixture, then `ab-pack --weights`, puts
  `why` first. A weights file with 4 decided tests keeps the default order. The inputs are
  unchanged.
  Test: tests/test_integration_ab_series.py::test_ab_pack_cli_default_and_weights
- `ab-results` text and `--json` on the fixture. Test: tests/test_integration_ab_series.py::test_ab_results_cli_fixture
- A missing `--out` / `--weights`, an output equal to an input, a missing, broken or old-format
  file, or missing columns give exit 2, one message, nothing on stdout and no file changed.
  Test: tests/test_integration_ab_series.py::test_ab_and_series_cli_errors_exit_2
- The installed executable runs `ab-pack`. Test: tests/test_integration_ab_series.py::test_ab_pack_installed_executable
- Errors of `ab-pack`, `ab-results`, `series`, `learn` and `experiment report` are exactly one line
  (`PROG: error: MESSAGE (usage: PROG --help)`), exit 2, and `--help` still shows the full usage.
  Test: tests/test_integration_ab_series.py::test_errors_are_one_line

## Known limits (the README says this)
- The 0.05 margin is a fixed rule, not a significance test. YouTube's CSV has no impression
  counts, so a test on a video with few views can still "win" by chance. YouTube's own label
  in Studio may differ.
- A weight is wins / decided tests the variant was in, so a variant dropped for length is not
  punished. Below 3 tests a variant is "not enough info" and keeps its default place: it is
  neither promoted nor pushed last. 3 is still a small sample, so check `(wins of tests)` next
  to every weight.
- Only exact shares from the CSV are used. No views or click-through rate.
