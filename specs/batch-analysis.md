# Batch CSV video SEO analysis

Status: **implemented** (`src/aidemy_seo/batch.py`, tests in `tests/test_batch.py` and
`tests/test_integration_cli.py`). Scoring decisions: ADR 0006.

Need: check the SEO basics of many videos at once (e.g. a whole channel export or a
planned batch of aidemy_pub lessons), instead of calling `title` / `description` once per video.
Real example: the Biologie Kl. 10 Gentechnik lesson (`tests/fixtures/bundle_biologie_kl10_gentechnik.json`)
and the titles in `tests/fixtures/vidiq_scores_2026-11-12.csv`.

Command: `aidemy-seo analyze-batch PATH_TO_CSV [--min-score N] [--json]`.
Module: `src/aidemy_seo/batch.py` (standard library only: `csv`, `dataclasses`, `math`,
`pathlib`, `itertools`; reuses `text.fold`, `text.stems`, `text.strip_hashtags` and
`titles.TEMPLATES` / `EMOTION_WORDS` / `QUESTION_WORDS` / `DIRECT_ADDRESS`).
Cost: **0 API units**, no network. The whole analysis is offline.

## Requirements

### Input CSV
- The file MUST be read as UTF-8. A leading BOM (Excel "CSV UTF-8") MUST be accepted.
  Other encodings are an error ("not UTF-8 - save as CSV UTF-8"). The tool MUST NOT guess.
- The delimiter MUST be found from the header line: the first of `,` `;` `\t` that gives a
  header with all required columns. The repo's own CSVs use `;` (`calibrate`), Excel in
  Germany writes `;` and most other tools write `,`. Quoted fields (with delimiters or line
  breaks inside a description) MUST work (`csv` module, no hand-written splitting).
- Required columns: `title`, `description`, `tags`. Optional: `video_id` (passed through to
  the output so a row can be found again). Header names are matched after trimming and
  ignoring case (`Title`, ` TAGS ` are fine).
- **Bad columns are skipped:** any other column (e.g. `views`, `notes`) and any column with an
  empty header name is ignored. One warning lists the ignored columns. They MUST NOT cause an
  error and MUST NOT change any score.
- **Bad rows are skipped, never guessed:** a row is skipped with a warning naming its line when
  - its number of fields differs from the header's (a shifted row would put the description
    into `tags`), or
  - its `title` is empty after trimming.

  Fully blank lines (no fields, or only empty fields such as the `;;;` rows Excel writes) are
  ignored without a warning and are not counted as rows. Empty lines before the header are skipped.
- An empty `description` or `tags` is NOT a bad row. The row is scored (low) and the issue is
  reported. Skipping it would hide exactly the videos that need work.
- "line" always means the line in the file where the row starts (header = line 1). A quoted
  multi-line description counts as several lines, so the number matches the line an editor
  shows.
- File-level errors MUST stop the command (exit 2, one message, nothing on stdout). These
  are: the file is missing, is a directory or can't be read; it is not UTF-8; it is empty or
  has no header; a required column is missing (the message lists the required columns and the
  ones found); a required column or `video_id` appears twice; the `csv` module raises `csv.Error` (the message
  names the line).

### Score per row (0-100, explainable)
Every check gives points. Every check that doesn't give full points adds exactly one
human-readable issue (same rule as `titles.md`). `score` = sum of the three parts, rounded to
1 decimal. This rubric is separate from `score_title()` (35-60 characters without hashtags, 66
total) and from vidIQ. It MUST NOT call or change them.

1. **Title length - up to 30 points.** `n = len(title.strip())` in characters (Unicode code
   points; hashtags count, "–" counts as 1). `40 <= n <= 65` gives 30 points. Outside that
   range the row loses 1 point per character: `30 - (40 - n)` below,
   `30 - (n - 65)` above, never below 0. Issue: `title: 69 characters (aim 40-65)`.
2. **Shared words between title and description - up to 30 points.**
   - Title topic words = `text.stems(text.strip_hashtags(title))` minus the *filler stems*.
     Filler stems are the stems of every `titles.TEMPLATES` text (without `{x}`) plus
     `EMOTION_WORDS`, `QUESTION_WORDS` and `DIRECT_ADDRESS`. Hashtags and template words
     ("musst", "wissen", "einfach erklärt") say nothing about the topic. If they counted, the
     channel's own templates would lose points in every row.
   - Description words = `text.stems(description)` (hashtags included).
   - Points = `round(30 * shared / topic_words, 1)`. Issue lists the missing words (as
     written in the title): `shared words: description misses "Gentechnik" (0 of 1 title words)`.
   - No topic words in the title: 0 points, issue `shared words: title has no topic words`.
     An empty description gives 0 points with the issue `shared words: description is empty`.
3. **Tags - up to 40 points.**
   - The `tags` field is split on `|`. Each tag is trimmed and empty pieces are dropped
     (`a||b|` has 2 tags). Tags are unique after `text.fold` (case and umlauts), and the first
     spelling is kept. Repeated tags are removed with a *warning*, not an issue. They cost no
     points beyond not counting twice.
   - Count: `5 <= unique tags <= 15` gives 20 points, otherwise 0. Issue: `tags: 4 unique tags (aim 5-15)`.
   - Length: total characters of the unique tags (`sum(len(tag))`, separators not counted)
     `< 500` gives 20 points, otherwise 0. It needs at least 1 tag, so an empty field doesn't
     get points for being short. Issue: `tags: 512 characters in total (must be < 500)` or
     `tags: none`.

### Duplicate titles
- Two analyzed rows are duplicates when their titles are equal after `text.fold` (case,
  umlauts, accents), trimming and collapsing whitespace. Hashtags stay part of the title,
  so `#Klasse9` and `#Klasse10` are different videos.
- The output MUST list **pairs**: n rows with the same title give n·(n-1)/2 pairs, each as
  `(line_a, line_b)` with `line_a < line_b`, sorted by `(line_a, line_b)`.
- Skipped rows are never part of a pair. `--min-score` MUST NOT hide duplicates: pairs are
  found over all analyzed rows.
- A duplicate does not change either row's score (it is a channel-level problem, not a
  row-level one).
- Only exact duplicates are reported. Titles built from the same template with another
  keyword ("Gentechnik: Das musst du wissen!" and "Proteine: Das musst du wissen!") MUST NOT
  be flagged.

### Ranking and `--min-score`
- Rows are ranked by score, highest first. Ties are broken by line, lower first, so the
  same file always gives the same order. `rank` is the 1-based position among all analyzed rows.
- `--min-score N` (default 0) shows only rows with `score >= N` in the rank list. The rank
  numbers don't change. The summary line MUST say how many rows were hidden, so a row is never
  dropped without notice. Warnings and duplicates still cover every row.
- `--min-score` MUST be a finite number from 0 to 100. Otherwise exit 2 (`-1`, `101`,
  `nan`, `inf`, `abc`).
- Exit code is 0 whenever the file could be analyzed, even with 0 analyzed rows.

### Text output
Three sections always appear in this order, after one summary line. An empty section says
`(none)`, so it's clear the check ran:

```
analyzed 5 of 7 rows in videos.csv (2 skipped); 1 duplicate title pair; showing 4 with score >= 50 (1 hidden)
RANKING
rank  score  length  words  tags  line  title
   1  100.0      30   30.0    40     2  Transgene Organismen: Das musst du wissen! #Biologie #Klasse10
   2   70.0      30    0.0    40     6  Gentechnik: Das musst du wissen! #Biologie #Klasse10
        - shared words: description misses "Gentechnik" (0 of 1 title words)
   ...
WARNINGS
  ignored columns: views, notes
  line 4: skipped - 2 fields, header has 4
  line 5: skipped - empty title
  line 7: repeated tags ignored: gentechnik, GENTECHNIK
DUPLICATE TITLES
  lines 6 and 9: Gentechnik: Das musst du wissen! #Biologie #Klasse10
```

- The issues of each shown row are listed under it, indented.
- WARNINGS is only about the input (ignored columns, skipped rows, repeated tags). Score
  issues belong to their row.
- With 0 analyzed rows, RANKING says `(no valid rows)`. When `--min-score` hides every row, it
  says `(no row with score >= N)` under the table header.

### JSON output (`--json`)
- `--json` MUST work in both places and give the same output:
  `aidemy-seo --json analyze-batch x.csv` (the global flag, like every other command) and
  `aidemy-seo analyze-batch x.csv --json` (as asked for this command). Watch out: a
  subcommand option with the same `dest` overwrites the global value with its default, so the
  subparser needs `default=argparse.SUPPRESS`.
- Shape (UTF-8, `ensure_ascii=False`, valid for `json.loads`):
  ```json
  {"file": "videos.csv", "min_score": 50.0,
   "rows": 7, "analyzed": 5, "skipped": 2, "shown": 4, "hidden": 1,
   "ranked": [{"rank": 1, "line": 2, "video_id": null,
               "title": "Transgene Organismen: Das musst du wissen! #Biologie #Klasse10",
               "score": 100.0,
               "points": {"title_length": 30, "shared_words": 30.0, "tags": 40},
               "issues": []}],
   "warnings": [{"line": null, "message": "ignored columns: views, notes"},
                {"line": 4, "message": "skipped - 2 fields, header has 4"}],
   "duplicates": [{"lines": [6, 9], "title": "Gentechnik: Das musst du wissen! #Biologie #Klasse10"}]}
  ```
  `ranked` holds only the shown rows. `video_id` is `null` when the column is missing or
  empty. The `title` of a duplicate pair is the title of `line_a` as written.

### Library API (`batch.py`)
- `read_batch(path) -> (rows, warnings)` raises `BatchError` for file-level errors.
  `score_row(title, description, tags) -> RowScore` (pure, no I/O).
  `duplicate_title_pairs(rows) -> list[DuplicatePair]`.
  `analyze_batch(path, *, min_score=0.0) -> BatchReport` with `.to_json()` and `.lines()`,
  like `experiments.report`.
- CLI handler `_analyze_batch` turns `BatchError` into `UsageError` (exit 2, no traceback).

### Data and review
- A CSV export holds channel data. Real exports MUST NOT be committed (`.gitignore` /
  review rule in CLAUDE.md). Test fixtures are synthetic rows built from titles that are
  already in the repo. The CSV reading code needs a line-by-line review (user/channel data).

### Known limits (the README MUST say this)
- `text.stems` is a crude 6-letter prefix: "Nahrungsnetze" and "Nahrungsketten" count as the
  same word. A topic that is also a hook word ("Wahrheit", "Mythos", "Fehler") is removed as
  filler and doesn't count as a shared word.
- The tag length is the sum of the tag characters. YouTube's own 500 limit also counts
  separators and quotes around tags with spaces, so a total just under 500 can still be too
  long on YouTube.
- Only exact duplicate titles are found. Near-duplicates are not.

## Decisions (confirmed with the requester)
1. Title length outside 40-65 loses 1 point per character (not 0 points right away).
2. Tag points: 40 = 20 for the count + 20 for the length.
3. "Skip bad columns" means: ignore unknown columns, skip broken rows.
4. `--min-score` hides rows below N. It is not an exit-1 gate.
5. Shared words leave out hashtags and template/hook words.
6. Duplicates keep hashtags in the title, so the same topic for two grades is not a duplicate.

## Scenarios

### Score
- Given the real lesson title "Transgene Organismen: Das musst du wissen! #Biologie #Klasse10"
  (62 characters), a description that names "transgene Organismen", and tags
  `Gentechnik|Grüne Gentechnik|Rote Gentechnik|gentechnik|transgene Organismen|Biologie Klasse 10|GENTECHNIK`,
  then the points are 30 / 30.0 / 40, the score is 100.0 and there are no issues. There are
  5 unique tags (79 characters), and the warning names the 2 repeated tags.
  Test: tests/test_batch.py::test_score_row_real_lesson_full_marks
- Given titles of 39, 40, 65 and 66 characters, then title_length is 29, 30, 30, 29. Given the
  real generated title "Gentechnik einfach erklärt – das musst du wissen! #Biologie #Klasse10"
  (69 characters), then it is 26 with the issue "69 characters (aim 40-65)". Given 5 or 100
  characters, then it is 0, never negative.
  Test: tests/test_batch.py::test_title_length_points_and_boundaries
- Given "Gentechnik: Das musst du wissen! #Biologie #Klasse10" and the description "Abonniere den
  Kanal für mehr Biologie. #Biologie #Klasse10", then shared_words is 0.0 and the issue names
  "Gentechnik". The hashtags #Biologie and "musst"/"wissen" don't count as shared.
  Test: tests/test_batch.py::test_shared_words_must_catch_missing_keyword
- Given "Sagen und Mythen – kannst du es erklären? #Deutsch #Klasse6" and "Was unterscheidet
  Sagen von Märchen?", then shared_words is 15.0 (1 of 2 topic words). Given "Warum? Einfach
  erklärt #Biologie", then 0.0 with "title has no topic words". Given an empty description,
  then 0.0 with "description is empty".
  Test: tests/test_batch.py::test_shared_words_ignores_template_words_and_counts_fraction
- Given 4, 5, 15 and 16 unique tags, then the count points are 0, 20, 20, 0. Given unique tags
  totalling 499 and 500 characters, then the length points are 20 and 0. Given `a||b| `, then 2
  tags. Given an empty tags field, then tags is 0 with the issue "tags: none".
  Test: tests/test_batch.py::test_tags_count_and_length_boundaries

### Reading the CSV
- Given a `;` file with header `video_id;Title;description;TAGS;views;` and rows: good, a
  row with 2 fields, a row with an empty title, a good row with a quoted 3-line description,
  and a good row after it, then 3 rows are analyzed and 2 are skipped with their lines. One
  warning says "ignored columns: views" and mentions the unnamed column. The row after the
  multi-line description has the line number an editor shows.
  Test: tests/test_batch.py::test_read_batch_skips_bad_rows_and_ignores_unknown_columns
- Given rows with an empty description or empty tags, then they are analyzed (not skipped)
  and get their issues. Nearest legitimate case.
  Test: tests/test_batch.py::test_read_batch_keeps_rows_with_empty_description_or_tags
- Given a comma file with a UTF-8 BOM and header `Title,Description,Tags`, and a tab file,
  then both give the same scores and warnings as the `;` file.
  Test: tests/test_batch.py::test_read_batch_detects_delimiter_bom_and_header_case
- Given a missing file, a directory, a Latin-1 file with "ä", an empty file, a file without
  `tags`, or a file with `title` twice, then `read_batch` raises `BatchError` with a clear
  message.
  Test: tests/test_batch.py::test_read_batch_rejects_bad_files
- Given a file without read permission, then `read_batch` raises `BatchError` with
  "can't read PATH: Permission denied" (as root, where the permission can't block reading, the
  same OS error is simulated). Given an OS error without an error text, then the message
  ends with the error itself.
  Test: tests/test_batch.py::test_read_batch_unreadable_file_is_an_error

### Duplicates
- Given "Gentechnik: Das musst du wissen! #Biologie #Klasse10" on lines 2 and 5 and
  "gentechnik:  das musst du WISSEN! #Biologie #Klasse10" on line 7, then the pairs are
  (2, 5), (2, 7), (5, 7). Given "Proteine: Das musst du wissen! #Chemie #Klasse12" and
  "Gentechnik: Das musst du wissen! #Biologie #Klasse9" in the same file, then they are not
  in any pair. A skipped row with the same title is not in any pair.
  Test: tests/test_batch.py::test_duplicate_title_pairs_exact_after_normalising

### Ranking and output
- Given rows scoring 100.0 (line 2), 96.0 (line 7), 70.0 (lines 6 and 3) and 26.0 (line 4,
  same title as line 7), then the order is lines 2, 7, 3, 6, 4. With min_score 50 line 4 is
  hidden, `hidden` is 1, the rank numbers stay 1-4, and the duplicate pair (4, 7) is still
  listed. A min_score of -1, 101, NaN or inf raises.
  Test: tests/test_batch.py::test_rank_order_ties_and_min_score_hides_but_keeps_duplicates
- Given a report, then `to_json()` has exactly the keys of the JSON shape above, passes
  `json.loads(json.dumps(..., ensure_ascii=False))` and keeps "ä". Given 0 analyzed rows,
  then `ranked` is empty and the text says "(no valid rows)".
  Test: tests/test_batch.py::test_report_json_shape_and_empty_file

### CLI
- Given a fixture CSV, then `aidemy-seo analyze-batch FILE` prints the summary line and
  the RANKING, WARNINGS and DUPLICATE TITLES sections. `aidemy-seo --json analyze-batch FILE`
  and `aidemy-seo analyze-batch FILE --json` print the same JSON. `--min-score 60` hides the
  lower rows and says how many.
  Test: tests/test_integration_cli.py::test_analyze_batch_cli_text_json_and_min_score
- Given a missing file, a Latin-1 file, a file without a `tags` column, or `--min-score` -1 / 101
  / nan / inf / abc, then exit code 2, one message on stderr, no traceback and nothing on
  stdout. Test: tests/test_integration_cli.py::test_analyze_batch_cli_errors_exit_2
