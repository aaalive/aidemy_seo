# 0007 - Title A/B tests: up to 3 variants per video, a fixed 0.05 margin, per-variant win-rate weights

- Status: accepted
- Date: 2026-11-18 (final state after the review of the same day; see History)

## Context
YouTube Studio's "Test & Compare" shows up to 3 titles on the *same* video and reports each
title's share of the watch time. Within one video the topic, the upload time and the age are
the same for every title. So it has none of the bias `learn` has (titles chosen by hand, older
videos) and it is faster than `experiment` (hash-assigned templates across videos, 5 published
videos per arm, bootstrap CI - ADR 0005, specs/experiments.md).

Requested:
- `ab-pack` writes 3 titles per video: search, question, why = `titles.TEMPLATES` 1, 0, 3.
  Each title is at most 66 characters and carries the title's hashtags, no repeats, at most 2.
- `ab-results` reads `video_id, variant, watch_time_share` and names a winner when
  top - second >= 0.05. It writes weights, wins / decided tests (2 decimals).
- The weights steer the order of the next pack.
- Input files must never be overwritten. No new dependencies.

Real example: `tests/fixtures/titles_to_fix.csv` (her titles with a keyword per video).
v02 "Raubtiere", v03 "Neobiota" and v04 "alleine leben" need 68 / 67 / 68 characters for the
search title with their series hashtags `#Biologie #Klasse11` / `#Ethik #Klasse5`.

## Options
1. **Winner rule**: a) the requested fixed margin (top - second >= 0.05); b) a significance
   test. The results CSV has no impression or view counts, so there is nothing to test with.
2. **Comparing shares**: a) floats: `0.45 - 0.40 = 0.04999…`, so an exact 0.05 margin would
   lose its winner; b) `decimal.Decimal` from the CSV text: exact, and still standard library.
3. **A title that doesn't fit 66 characters**: a) cut it; b) exceed 66; c) skip the whole
   video; d) drop only that variant and test the others.
4. **Hashtags when a title is too long**: a) drop from the end (`titles.build_title`), which can
   drop `#KlasseN`; b) never drop the series hashtags (`#KlasseN`, and the `#Fach` of a series
   title) and drop only the others.
5. **Weight of a variant**: a) wins / all decided tests; b) wins / decided tests the variant was
   in. Below a minimum number of tests: c) the raw rate; d) a smoothed rate ((wins+1)/(tests+2));
   e) 0; f) "not enough info".
6. **Order of a pack when a weight is unknown**: a) the whole pack falls back to the default
   order; b) the unknown variant keeps its default place and the known ones are ranked.
7. **Where the code comes from**: copies in the new module, or reuse `titles.TEMPLATES` /
   `titles.build_title`, the batch CSV reader (made reusable as `fileio.read_table`) and one
   atomic writer (`fileio.write_text_atomic`, also used by the experiment ledger).

## Decision
1a, 2b, 3d, 4b, 5b + 5f, 6b, reuse for 7. In detail:

- **Titles.** A variant is `build_title(keyword, template, tags)` with at most 66 characters,
  never cut. The series hashtags are picked first for the 2 slots and never dropped. This keeps
  every new title in the video's series (ADR 0008). A variant that still doesn't fit is
  dropped with a warning on its line (JSON `dropped`). The video keeps the other titles, since
  Test & Compare accepts 2. Only when fewer than 2 fit (`MIN_TITLES`) is the video skipped.
- **Winner.** Top share - second share >= 0.05 (`WIN_MARGIN`, exact `Decimal`), otherwise
  inconclusive. **A video is never evaluated on partial data**:
  - one of its rows was skipped;
  - a variant appears twice;
  - only 1 variant is there;
  - or its shares add up to more than 1.01.

  Comparing the rest could name the wrong winner.
- **Weights.** Per variant: wins / decided tests **the variant was in** (JSON `decided_with`).
  A test without the variant (e.g. its search title was dropped for length) is not a loss for it.
  - Inconclusive tests count for no variant.
  - Rounding is half up (`1/8` = 0.13, not Python's 0.12).
  - A variant in **fewer than 3 decided tests** (`MIN_TESTS_PER_VARIANT`) is "not enough info":
    `null` in the file and `None` in Python. It is not a loser and not a winner.
  - 0 wins in 3+ tests is a real 0.00.
- **Weights file.** `{"decided": N, "weights": {"search": 0.25, "question": 0.2, "why": null}}`.
  `ab-results` always writes it, and `ab-pack` decides whether it counts.
  - A missing variant means `null`.
  - A flat file without `decided`, an unknown variant, or a weight that is not a number or
    `null` is refused.
- **Order in `ab-pack`.** With fewer than **5 decided tests in total** (`MIN_DECIDED`), the
  default order search, question, why is used. From 5 on, the variants with a weight are ranked
  highest first, and a "not enough info" variant keeps its default place:
  `search null, question 0.2, why 0.6` gives search, why, question. Equal weights keep the
  default order. A video with 2 titles keeps the order of its 2.
- **Files.**
  - Inputs are never overwritten. An output that is the same file as an input (resolved path,
    or `os.path.samefile` for hard links and a case-insensitive disk) is refused.
  - Every write goes through `fileio.write_text_atomic`: a temp file, then `os.replace`, and an
    existing file keeps its mode.
  - New A/B outputs get normal permissions (0666 minus the umask, usually 0644). The
    experiment ledger passes `new_file_mode=0o600` and stays private (specs/experiments.md).
  - The output CSV uses the input's delimiter and BOM.
- **CLI errors.** Every error of every command is exactly one line, never a traceback
  (specs/cli-errors.md):
  - bad arguments or input (argparse, `UsageError`, unreadable or wrongly shaped files, no API
    key): `PROG: error: MESSAGE (usage: PROG --help)`, exit 2, with no argparse usage block
    (`cli.OneLineErrorParser`);
  - a failed YouTube API request (`CommandFailed`): `PROG: error: MESSAGE`, exit 1, with a
    short reason and the API key hidden.

  `--help` still shows the usage.

Why: a fixed margin is what was asked, and the only rule the data supports (it is a threshold,
not a confidence level, and the README says so). A cut title reads badly. A title without
`#KlasseN` leaves its series. A variant that could not take part, or took part only once or
twice, must not be ranked as if it had lost or won.

## Consequences
- `ab-results` needs only what Studio shows. A small video can still "win" by chance. The
  output shows `(wins of tests)` next to every weight, so judge the weights with it.
- Long keywords with long `#Fach` tags lose the `search` variant (v02-v04 of the fixture). So
  `search` collects fewer tests and stays "not enough info" longer. It keeps its default place
  meanwhile, and is neither promoted nor pushed last.
- 3 tests per variant and 5 in total are still small samples, chosen for simplicity.
- `batch.py` reads through `fileio.read_table` and `experiments.save_ledger` writes through
  `fileio.write_text_atomic`. Their behaviour and messages are unchanged, and all their existing
  tests pass unchanged. `experiments.py` keeps `import os  # noqa: F401`, because an existing
  test patches `experiments.os.replace` to simulate a crash, and existing tests are not changed.
  The patch replaces `os.replace` for the shared writer too, so that test still checks the real
  write.
- `CsvWarning.skipped_row` is keyword-only, so a caller must write `skipped_row=True`.
- Since History 8, every command reports bad input files, a wrong file shape, a missing API key
  or `requests`, and a failed API request in one short line too (specs/cli-errors.md).
  Programming errors are not caught, so a bug still shows its traceback.
- `experiment` (across videos, views per day) and `ab-pack` / `ab-results` (within a video,
  watch time share) both stay. They answer the same question with different data.

## History (review of 2026-11-18, in order)
1. First version: `#KlasseN` could be dropped to fit 66 characters, and v03 left its series.
   Then series hashtags were never dropped, and a video that didn't fit was skipped.
2. Weights got a minimum of 5 decided tests, so the file stores `decided`. New output files
   went from 0600 to normal permissions.
3. Skipping the whole video was replaced by dropping only the variant that doesn't fit (3c -> 3d).
4. Weights / all decided tests counted a dropped variant's tests as losses. They became wins /
   decided tests the variant was in (5a -> 5b).
5. 1 win in 1 test gave 1.0, so a minimum of 3 tests per variant was added, first as weight 0
   (5e). That ranked a barely tested variant last, so it became "not enough info" (`null`),
   keeping its default place (5f, 6b).
6. CLI errors (argparse and `UsageError`) became one line for every command.
7. Cleanup: the experiment ledger uses the shared atomic writer (`new_file_mode=0o600`), and
   `skipped_row` is keyword-only.
8. `calibrate missing.csv` crashed with a traceback. A survey found the same crash in every
   older command that reads a file or calls the API. All of them now give one short line
   (`fileio.read_input_text` / `read_input_json`, shape checks, `CommandFailed`). A bad bundle
   used to print an empty keyword and is now an error. A failed request's message used to
   include the URL with the API key, which is now hidden.
