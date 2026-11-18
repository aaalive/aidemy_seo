# CLI errors: one short line, never a Python traceback

Status: **implemented** (`src/aidemy_seo/cli.py`, `src/aidemy_seo/fileio.py`; tests in
`tests/test_integration_errors.py`, one test per command). Decision: ADR 0007 (History 8).

Need: `aidemy-seo calibrate missing.csv` ended in a long Python traceback
(`FileNotFoundError: [Errno 2] No such file or directory`). The newer commands already gave one
line. A survey of every command found the same crash in `description`, `schedule`, `learn`,
`lesson`, `channels` (`--load`, `--file`), `calibrate`, `benchmark` and `experiment assign`. The
inputs were a missing file, a folder, a non-UTF-8 file, broken JSON, JSON of the wrong shape, a
score that is not a number, no API key, the `requests` package missing, and no network.

## Requirements
- Every error MUST be exactly **one line on stderr**, with nothing on stdout and no traceback:
  - **exit 2**: bad arguments or bad input the user can fix. Format:
    `aidemy-seo CMD: error: MESSAGE (usage: aidemy-seo CMD --help)`.
  - **exit 1**: the command was used correctly but could not finish (the YouTube API request
    failed). Format: `aidemy-seo CMD: error: MESSAGE`.
- Input files (`fileio.read_input_text` / `read_input_json`, one message format,
  `can't read <what> <path>: <reason>`):
  - missing: `No such file or directory`; a folder: `Is a directory`; no permission:
    `Permission denied`;
  - not UTF-8: `not UTF-8 (line N) - save it as UTF-8` (a BOM is fine);
  - broken JSON: `not valid JSON (line L, column C)`.
  - `<what>` names the file's role: `description file`, `stats file`, `bundle`, `calibration
    CSV`, `channels file`, `channel list`, `ledger`.
- Wrong shape = one line that says what was expected. A shape error MUST NOT be silently
  accepted:
  - stats file: `must be a JSON object with a "videos" list of objects` (a missing `videos`
    key is still 0 videos, as before);
  - bundle: `is not an aidemy_pub bundle.json - it needs meta.topic (and, if present, an
    overview object and a keyTerms list)`. A bundle without a topic used to print an empty
    keyword;
  - `channels --load`: `is not a file written by --save`, naming the channel or video;
  - calibration CSV: `line N: score 'hoch' is not a number (title;score)`.
- Output files: `can't write ledger PATH: ...`, `can't write --save PATH: ...`.
- YouTube API (`benchmark`, `channels`):
  - no `YOUTUBE_API_KEY`: exit 2, checked **before** any request;
  - `requests` not installed: exit 2, `pip install 'aidemy-seo[http]'`;
  - request failed: exit 1 with a **short** reason: `can't reach the YouTube API - are you
    online?`, `the request timed out`, or `HTTP 403 Forbidden - <the API's message>`. It is not
    requests' long text with the URL.
  - **The API key is never printed.** A `key=...` in any message becomes `key=***`, and the key
    itself is replaced too.
  - One failing channel in `channels` stays a note on stderr (`not found / skipped: @x (HTTP 403
    Forbidden - ...)`, key hidden) and the other channels still run, as before.
- Safety net: any other `OSError` that reaches `main()` is one line too: `can't access PATH:
  REASON` (exit 2). Programming errors are NOT caught, so a bug still shows its traceback and can
  be fixed.
- Good input behaves exactly as before (all existing tests pass unchanged).

## Scenarios (one test per command)
- `keywords` without a topic, then one argparse line.
  Test: tests/test_integration_errors.py::test_keywords_errors_one_line
- `title` without text, then one argparse line.
  Test: tests/test_integration_errors.py::test_title_errors_one_line
- `description` with a missing file, a folder, or a Latin-1 file.
  Test: tests/test_integration_errors.py::test_description_errors_one_line
- `schedule` and `learn` with a missing file, a folder, Latin-1, broken JSON, a list, `"videos": "x"`
  or `"videos": [1, 2]`.
  Test: tests/test_integration_errors.py::test_schedule_errors_one_line
  Test: tests/test_integration_errors.py::test_learn_errors_one_line
- `experiment assign` with a folder as the ledger, or a ledger in a missing folder.
  `experiment report` with a missing ledger, or a stats file of the wrong shape.
  Test: tests/test_integration_errors.py::test_experiment_errors_one_line
  Test: tests/test_integration_errors.py::test_experiment_report_bad_stats_one_line
- `analyze-batch`, `ab-pack`, `ab-results`, `series` with a missing file or a folder.
  Test: tests/test_integration_errors.py::test_analyze_batch_errors_one_line
  Test: tests/test_integration_errors.py::test_ab_pack_errors_one_line
  Test: tests/test_integration_errors.py::test_ab_results_errors_one_line
  Test: tests/test_integration_errors.py::test_series_errors_one_line
- **Must catch (the reported crash):** `calibrate` with a missing file gives `can't read
  calibration CSV PATH: No such file or directory`. So do a folder, Latin-1, and the score
  `hoch` on line 3. Test: tests/test_integration_errors.py::test_calibrate_errors_one_line
- `lesson` with a missing file, broken JSON, a list, no `meta.topic`, a blank topic, `overview: []`
  or `keyTerms: "Gen"`. Test: tests/test_integration_errors.py::test_lesson_errors_one_line
- `benchmark` offline, on a timeout, on HTTP 403 whose URL holds the key, on an unknown error whose
  text holds `key=...` or the key itself, or without `requests`. Then exit 1 or 2, a short reason,
  and the key is never in the line (`key=***`). Without a key: exit 2 before any request.
  Test: tests/test_integration_errors.py::test_benchmark_errors_one_line
  Test: tests/test_integration_errors.py::test_benchmark_without_key_one_line
- `channels --load` with a missing file, broken JSON, a list, `videos: "x"`, or a video with the
  wrong fields. Test: tests/test_integration_errors.py::test_channels_load_errors_one_line
- `channels` live:
  - without a key, with a missing `--file`, offline `--discover`, or without `requests`: one line;
  - one channel on HTTP 403: a short skip note with the key hidden, exit 0;
  - `--save` into a missing folder: one line.
  Test: tests/test_integration_errors.py::test_channels_live_errors_one_line
- An unexpected `PermissionError` inside a command gives `can't access /some/file: Permission
  denied`. Test: tests/test_integration_errors.py::test_unexpected_file_error_is_one_line_too
- Nearest legitimate case: `schedule`, `learn`, `calibrate` and `series` with good files exit 0.
  Test: tests/test_integration_errors.py::test_good_input_still_works
