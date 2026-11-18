# Shorts series from #Fach + #KlasseN

Status: **implemented** (`src/aidemy_seo/series.py`, tests in `tests/test_series.py` and
`tests/test_integration_ab_series.py`). Decision: ADR 0008.

Need: a YouTube playlist per series ("Biologie Klasse 11") keeps viewers watching the next
Short of the same topic. The channel's titles already end with `#Fach #KlasseN`
(`titles.title_tags()`), so the series can be read from the titles, with no manual sorting.
Real example: `tests/fixtures/titles_to_fix.csv` (10 real titles: 2 series, 5 videos that fit no series).

Command: `aidemy-seo series PATH_TO_CSV [--json]` (`--json` right after `aidemy-seo`, like
every command). Module: `src/aidemy_seo/series.py` (standard library only; reuses the CSV reader
in `fileio.py`, `text.hashtags` and `text.fold`). Cost: **0 API units**. It writes **no file**,
so the input can't be overwritten.

## Requirements
- Input CSV: UTF-8 (BOM allowed), delimiter `,` `;` or tab, the same reader and file-level
  errors as `analyze-batch`. Required column: `title`. Optional: `video_id`. Other columns are
  ignored with one warning. An `ab-pack` input or an `analyze-batch` CSV works as is.
- A row is skipped with a warning naming its line when it has the wrong number of fields, an
  empty title, or a `video_id` that was already on an earlier line. The same video twice would
  make a fake series of 1 video.
- **Grade** = the number in a `#KlasseN` hashtag (case-insensitive, `#Klasse09` = 9). The same
  grade twice is one grade. Two different grades (`#Klasse9 #Klasse10`) are ambiguous: the
  video is not sorted. `#Klasse` without a number is not a grade.
- **Grade ranges and school levels are recognised but never turned into a grade** (2026-11-18).
  - **Range:** `#Klasse11-12`, `#Klasse11–12`, `#Klasse11/12`, `#Klasse11bis12` or
    `#Klasse11_12`. A written range is ONE tag (`series.title_hashtags`). A plain hashtag split,
    like YouTube itself, stops at the `-` and sees `#Klasse11`, which used to file an 11-12 video
    under Klasse 11. A dash with spaces (`#Klasse11 - Teil 2`) or a word after it
    (`#Klasse11-Quiz`) is not a range.
  - **Level:** `#Q1`, `#Q11` (`#Q` + 1-2 digits), `#Oberstufe`, `#Mittelstufe`, `#Unterstufe`,
    `#Sek1`, `#SekII`, `#Sekundarstufe2`, `#EF`, `#Abi` or `#Abitur`.
  - Without a `#KlasseN` the video is **not sorted**, with the reason `grade range #Klasse11-12 -
    a series needs one grade (#KlasseN)` or `#Q11 is a school level, not a grade - a series needs
    #KlasseN (levels are not guessed)`.
  - Next to one `#KlasseN`, the `#KlasseN` decides and the range or level is extra information.
  - A level is **never the subject**. `#Oberstufe #Biologie #Klasse11` is "Biologie Klasse 11",
    not "Oberstufe Klasse 11".
- **Subject (Fach)** = the first hashtag in the title that is not a `#Klasse…` hashtag, not a
  school level and not a platform tag (`#Shorts`, `#Short`, `#YouTubeShorts`, any case). This matches the channel's
  `#Fach #KlasseN` titles. A topic tag after the subject (`#Biologie #Klasse9 #Zellbiologie`)
  does not change it.
- Videos with the same subject (compared after `text.fold`: case and umlauts) and the same
  grade are one group. A group with **2 or more** videos is a series named
  **"{Fach} Klasse {N}"**. Fach is spelled as in the group's first video, and N has no leading
  zero.
- **Not sorted** = every other video, each with its reason: `no #KlasseN hashtag`,
  `grade range #Klasse11-12 - ...`, `#Q11 is a school level, not a grade - ...`,
  `2 grade hashtags (#Klasse9, #Klasse10)`, `no subject hashtag (#Fach)`, or
  `only video of Chemie Klasse 8`.
- `ab-pack` uses `series_key` and `title_hashtags` too. It never drops a series hashtag, a range
  (kept as written, never cut to `#Klasse11`) or a level from a new title. So an A/B title keeps
  its video's grade and series (specs/ab-testing.md).
- Order: series by subject (folded), then grade as a number (5 before 10). Videos inside a
  series, and the not-sorted videos, stay in file order.
- Text output: a summary line (`2 series in videos.csv: 5 of 10 videos in a series, 5 not
  sorted, 0 skipped`), then `SERIES` (one heading per series, its videos with line and
  video_id), `NOT SORTED` (with the reasons) and `WARNINGS`. An empty section says so.
- `--json`: `{"file", "videos", "in_series", "series": [{"name", "subject", "grade", "count",
  "videos": [{"line", "video_id", "title"}]}], "not_sorted": [{"line", "video_id", "title",
  "reason"}], "warnings": [{"line", "message"}]}`. `video_id` is `null` when the column is
  missing or empty.
- File errors (missing, not UTF-8, empty, no `title` column) exit 2 with one line, no
  traceback, nothing on stdout.

## Decisions (interpretation of the request, 2026-11-18)
1. "Group by #fach + #klassN, 2+ videos are a series": a series needs both hashtags and at
   least 2 videos.
2. "Rest could be not sorted": every other video is listed under NOT SORTED with a reason,
   never dropped silently and never guessed into a series.
3. Only hashtags in the title count. Tags and descriptions are not read: the title is what
   the channel controls and what `title_tags()` writes.
4. Grade ranges and school levels are not mapped to a grade (asked how to handle `#Klasse11-12`,
   `#Oberstufe`, `#Q11`; recommended and implemented on 2026-11-18, see ADR 0008 "Grade ranges and
   levels"):
   - `#Q11` is Klasse 11 in Bayern, but NRW's Q1/Q2 are 11/12 or 12/13 (G8/G9).
   - `#Oberstufe` covers 2-3 grades.
   - A range is two grades, and YouTube links only its first part.
   - A misfiled video ends up in the wrong playlist without anyone noticing. An unsorted one is
     listed with a reason that says what to fix.

## Scenarios
- Given `#Biologie #Klasse10`, `#Klasse10 #Biologie`, `#Shorts #Biologie #Klasse9`,
  `#biologie #KLASSE09`, the real v09 title with `#Biologie #biologie #Klasse9 #Zellbiologie`,
  or the same grade twice, then the subject and grade are found. Given no grade, `#Klasse`
  without a number, two grades, or only `#Klasse10 #Shorts`, then the reason.
  Test: tests/test_series.py::test_series_key_subject_and_grade
- Given `tests/fixtures/titles_to_fix.csv`, then the series are "Biologie Klasse 11" (v02, v03,
  v06) and "Ethik Klasse 5" (v04, v07). v01 and v10 have no `#KlasseN`. v05, v08 and v09 are the
  only video of their group.
  Test: tests/test_series.py::test_find_series_on_real_titles
- Given `#Ethik #Klasse10` and `#ethik #KLASSE10`, then one series "Ethik Klasse 10". Given Ethik
  5 and 10, then Klasse 5 comes first. Given 1 video of Ökologie Klasse 7, then it is not sorted.
  A file without `video_id` works.
  Test: tests/test_series.py::test_find_series_groups_case_insensitive_sorted_and_min_two
- Given the same video_id twice, then the second row is skipped and makes no fake series. An
  empty title or a row with the wrong number of fields is skipped with its line. The input is
  unchanged and no file is written. A missing file, no `title` column, or an empty file is an
  error.
  Test: tests/test_series.py::test_find_series_skips_bad_rows_and_duplicate_ids
- Given the fixture, then the JSON has exactly the keys above and the text has SERIES, NOT
  SORTED and WARNINGS in this order. With no series, the text says a series needs 2 videos.
  Test: tests/test_series.py::test_series_report_json_and_text
- CLI text and `--json` on the fixture. The input is unchanged.
  Test: tests/test_integration_ab_series.py::test_series_cli_text_and_json
- A missing or Latin-1 file gives exit 2. Test: tests/test_integration_ab_series.py::test_ab_and_series_cli_errors_exit_2

- **Must catch:** `#Klasse11-12` (and `–`, `/`, `bis`, `_`) is a range, not Klasse 11: not sorted
  with the range reason. A range next to `#Klasse11` gives Klasse 11. `#Klasse11 - Teil 2` and
  `#Klasse11-Quiz` give Klasse 11 (nearest legitimate case). Two single grades stay ambiguous.
  Test: tests/test_series.py::test_grade_ranges_are_not_guessed
- **Must catch:** `#Q11`, `#Q1`, `#Q12`, `#Oberstufe`, `#Mittelstufe`, `#SekII`, `#Sek1`, `#Abitur`
  and `#EF` alone give the level reason. `#Oberstufe #Biologie #Klasse11` and `#Q11 #Biologie
  #Klasse11` give Biologie 11 (the level is not the subject). `#Quadratik` and `#Sekundenschlaf`
  are still subjects (nearest legitimate case), and neither `#Q` nor `#Q123` is a level (Q + 1-2
  digits).
  Test: tests/test_series.py::test_school_levels_are_not_grades_and_not_subjects
- Given 2 videos with `#Biologie #Klasse11-12`, 1 with `#Biologie #Klasse11`, 2 with a level before
  `#Chemie #Klasse12`, and 2 with `#Physik #Q11`, then the only series is "Chemie Klasse 12". The
  ranges are not merged into Klasse 11, and the `#Q11` videos are not sorted with the level reason.
  Test: tests/test_series.py::test_find_series_with_ranges_and_levels

## Known limits
- The level list is fixed (`series.LEVEL_RE`). A level written another way (`#Kursstufe`,
  `#Jahrgang12`, `#J1`) is taken as a subject if it comes first. Add it to the list when it
  shows up.
- A subject is whatever the first hashtag says: `#Bio` and `#Biologie` are two series.
- Titles without `#KlasseN` (e.g. grade-independent Shorts) are never in a series.
- The tool suggests series; it does not create playlists (that would need OAuth write access).
