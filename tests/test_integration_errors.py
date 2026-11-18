"""Every command: bad input ends in ONE short error line on stderr - never a Python traceback
(specs/cli-errors.md). One test per command. Offline: the YouTube API layer is replaced by fakes."""

import json
from pathlib import Path

import pytest

from aidemy_seo import keywords as kw_mod
from aidemy_seo.cli import main

FIX = Path(__file__).parent / "fixtures"
STATS = str(FIX / "stats_synthetic.json")
TITLES = str(FIX / "titles_to_fix.csv")
KEY = "SECRET-KEY-123"


@pytest.fixture
def bad(tmp_path):
    """Broken inputs: a missing file, a folder, a Latin-1 file, broken / wrong-shaped JSON."""
    (tmp_path / "folder").mkdir()
    (tmp_path / "latin1.txt").write_bytes("title;score\nGrüne;80\n".encode("latin-1"))
    (tmp_path / "broken.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")
    (tmp_path / "videos_str.json").write_text('{"videos": "x"}', encoding="utf-8")
    (tmp_path / "videos_nums.json").write_text('{"videos": [1, 2]}', encoding="utf-8")
    return {
        "MISSING": str(tmp_path / "missing.json"),
        "FOLDER": str(tmp_path / "folder"),
        "LATIN1": str(tmp_path / "latin1.txt"),
        "BROKEN": str(tmp_path / "broken.json"),
        "LIST": str(tmp_path / "list.json"),
        "VIDEOS_STR": str(tmp_path / "videos_str.json"),
        "VIDEOS_NUMS": str(tmp_path / "videos_nums.json"),
        "TMP": str(tmp_path),
    }


def fill(text, paths):
    for k, v in paths.items():
        text = text.replace("{" + k + "}", v)
    return text


def error_line(capsys, argv, code=2):
    """Run the CLI, expect exit `code` and exactly one stderr line (no traceback, nothing on stdout)."""
    with pytest.raises(SystemExit) as exc:
        main(argv)
    cap = capsys.readouterr()
    lines = cap.err.splitlines()
    assert exc.value.code == code, cap.err
    assert len(lines) == 1, cap.err  # one short line
    assert "Traceback" not in cap.err and cap.out == ""
    return lines[0]


def check(capsys, bad, argv, expected, code=2):
    prog = "aidemy-seo " + " ".join(argv[:2]) if argv[0] == "experiment" else f"aidemy-seo {argv[0]}"
    line = error_line(capsys, [fill(a, bad) for a in argv], code)
    suffix = f" (usage: {prog} --help)" if code == 2 else ""
    assert line == f"{prog}: error: {fill(expected, bad)}{suffix}"


# ---------------------------------------------------------------- one test per command
def test_keywords_errors_one_line(capsys, bad):
    check(capsys, bad, ["keywords"], "the following arguments are required: topic")


def test_title_errors_one_line(capsys, bad):
    check(capsys, bad, ["title"], "the following arguments are required: text")


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("{MISSING}", "No such file or directory"),
        ("{FOLDER}", "Is a directory"),
        ("{LATIN1}", "not UTF-8 (line 2) - save it as UTF-8"),
    ],
)
def test_description_errors_one_line(capsys, bad, path, reason):
    check(capsys, bad, ["description", path], f"can't read description file {path}: {reason}")


STATS_SHAPE = 'must be a JSON object with a "videos" list of objects (aidemy_pub state/youtube/stats.json)'
STATS_CASES = [
    ("{MISSING}", "can't read stats file {MISSING}: No such file or directory"),
    ("{FOLDER}", "can't read stats file {FOLDER}: Is a directory"),
    ("{LATIN1}", "can't read stats file {LATIN1}: not UTF-8 (line 2) - save it as UTF-8"),
    ("{BROKEN}", "can't read stats file {BROKEN}: not valid JSON (line 1, column 2)"),
    ("{LIST}", f"stats file {{LIST}} {STATS_SHAPE}"),
    ("{VIDEOS_STR}", f"stats file {{VIDEOS_STR}} {STATS_SHAPE}"),
    ("{VIDEOS_NUMS}", f"stats file {{VIDEOS_NUMS}} {STATS_SHAPE}"),
]


@pytest.mark.parametrize(("path", "expected"), STATS_CASES)
def test_schedule_errors_one_line(capsys, bad, path, expected):
    check(capsys, bad, ["schedule", path], expected)


@pytest.mark.parametrize(("path", "expected"), STATS_CASES)
def test_learn_errors_one_line(capsys, bad, path, expected):
    check(capsys, bad, ["learn", path], expected)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            ["experiment", "assign", "{FOLDER}", "--experiment", "e", "--key", "k", "--keyword", "Mitose"],
            "can't read ledger {FOLDER}: Is a directory",
        ),
        (
            [
                "experiment",
                "assign",
                "{TMP}/no/such/folder/l.json",
                "--experiment",
                "e",
                "--key",
                "k",
                "--keyword",
                "x",
            ],
            "can't write ledger {TMP}/no/such/folder/l.json: No such file or directory",
        ),
        (
            ["experiment", "report", "{MISSING}", STATS, "--experiment", "e"],
            "ledger {MISSING} does not exist - create it with `experiment assign`",
        ),
    ],
)
def test_experiment_errors_one_line(capsys, bad, argv, expected):
    check(capsys, bad, argv, expected)


def test_experiment_report_bad_stats_one_line(capsys, bad, tmp_path):
    ledger = tmp_path / "l.json"
    assert main(["experiment", "assign", str(ledger), "--experiment", "e", "--key", "k", "--keyword", "Mitose"]) == 0
    capsys.readouterr()
    check(
        capsys,
        bad,
        ["experiment", "report", str(ledger), "{LIST}", "--experiment", "e"],
        f"stats file {{LIST}} {STATS_SHAPE}",
    )


def test_analyze_batch_errors_one_line(capsys, bad):
    check(capsys, bad, ["analyze-batch", "{MISSING}"], "file not found: {MISSING}")


def test_ab_pack_errors_one_line(capsys, bad):
    check(capsys, bad, ["ab-pack", "{MISSING}", "--out", "{TMP}/out.csv"], "file not found: {MISSING}")


def test_ab_results_errors_one_line(capsys, bad):
    check(capsys, bad, ["ab-results", "{MISSING}", "--weights", "{TMP}/w.json"], "file not found: {MISSING}")


def test_series_errors_one_line(capsys, bad):
    check(capsys, bad, ["series", "{FOLDER}"], "{FOLDER} is a directory, not a CSV file")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("{MISSING}", "can't read calibration CSV {MISSING}: No such file or directory"),  # the reported crash
        ("{FOLDER}", "can't read calibration CSV {FOLDER}: Is a directory"),
        ("{LATIN1}", "can't read calibration CSV {LATIN1}: not UTF-8 (line 2) - save it as UTF-8"),
        ("{TMP}/score.csv", "calibration CSV {TMP}/score.csv, line 3: score 'hoch' is not a number (title;score)"),
    ],
)
def test_calibrate_errors_one_line(capsys, bad, path, expected):
    Path(bad["TMP"], "score.csv").write_text("title;score\nA – kannst du es?;80\nB;hoch\n", encoding="utf-8")
    check(capsys, bad, ["calibrate", path], expected)


BUNDLE_SHAPE = (
    "is not an aidemy_pub bundle.json - it needs meta.topic (and, if present, an overview object and a keyTerms list)"
)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, "can't read bundle {MISSING}: No such file or directory"),
        ("{broken", "can't read bundle {TMP}/bundle.json: not valid JSON (line 1, column 2)"),
        ("[1]", f"bundle {{TMP}}/bundle.json {BUNDLE_SHAPE}"),
        ('{"videos": "x"}', f"bundle {{TMP}}/bundle.json {BUNDLE_SHAPE}"),  # used to print an empty keyword
        ('{"meta": {"topic": "  "}}', f"bundle {{TMP}}/bundle.json {BUNDLE_SHAPE}"),
        ('{"meta": {"topic": "Gentechnik"}, "overview": []}', f"bundle {{TMP}}/bundle.json {BUNDLE_SHAPE}"),
        ('{"meta": {"topic": "Gentechnik"}, "keyTerms": "Gen"}', f"bundle {{TMP}}/bundle.json {BUNDLE_SHAPE}"),
    ],
)
def test_lesson_errors_one_line(capsys, bad, content, expected):
    path = "{MISSING}"
    if content is not None:
        Path(bad["TMP"], "bundle.json").write_text(content, encoding="utf-8")
        path = "{TMP}/bundle.json"
    check(capsys, bad, ["lesson", path], expected)


# ---------------------------------------------------------------- commands that call the YouTube API
class HTTPError(OSError):
    """Like requests.HTTPError (an OSError): the text holds the URL - with the key."""

    def __init__(self):
        super().__init__(
            f"403 Client Error: Forbidden for url: https://www.googleapis.com/youtube/v3/search?q=x&key={KEY}"
        )
        self.response = type(
            "R",
            (),
            {"status_code": 403, "reason": "Forbidden", "json": lambda self: {"error": {"message": "quotaExceeded"}}},
        )()


class ReadTimeout(OSError):
    pass


def failing_fetch(error):
    def fetch(url, params):
        raise error

    return fetch


API_FAILURES = [
    (
        ConnectionError(f"Max retries exceeded with url: /youtube/v3/search?key={KEY}"),
        1,
        "YouTube API request failed: can't reach the YouTube API - are you online?",
    ),
    (ReadTimeout("read timed out"), 1, "YouTube API request failed: the request timed out"),
    (HTTPError(), 1, "YouTube API request failed: HTTP 403 Forbidden - quotaExceeded"),
    # an error of no known kind keeps its own text - the key in it must still be hidden
    (
        OSError(f"SSL: certificate verify failed for https://www.googleapis.com/youtube/v3/search?q=x&key={KEY}"),
        1,
        "YouTube API request failed: SSL: certificate verify failed for https://www.googleapis.com/youtube/v3/search?q=x&key=***",
    ),
    (ValueError(f"bad JSON answer for token {KEY}"), 1, "YouTube API request failed: bad JSON answer for token ***"),
    (
        ModuleNotFoundError("No module named 'requests'"),
        2,
        "live YouTube data needs the optional 'requests' package - pip install 'aidemy-seo[http]'",
    ),
]


@pytest.mark.parametrize(("error", "code", "expected"), API_FAILURES)
def test_benchmark_errors_one_line(capsys, bad, monkeypatch, error, code, expected):
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    monkeypatch.setattr(kw_mod, "requests_fetch", failing_fetch(error))
    line = error_line(capsys, ["benchmark", "Gentechnik"], code)
    assert line.startswith(f"aidemy-seo benchmark: error: {expected}") and KEY not in line  # the key is never printed


def test_benchmark_without_key_one_line(capsys, bad, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    check(
        capsys, bad, ["benchmark", "Gentechnik"], "no YouTube API key - set YOUTUBE_API_KEY (a read-only key is enough)"
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, "can't read channels file {MISSING}: No such file or directory"),
        ("{broken", "can't read channels file {TMP}/ch.json: not valid JSON (line 1, column 2)"),
        ("[1]", "channels file {TMP}/ch.json is not a file written by --save"),
        ('{"chan": {"videos": "x"}}', "channels file {TMP}/ch.json is not a file written by --save (channel 'chan')"),
        (
            '{"chan": {"videos": [{"title": "x"}]}}',
            "channels file {TMP}/ch.json is not a file written by --save (a video of channel 'chan')",
        ),
    ],
)
def test_channels_load_errors_one_line(capsys, bad, content, expected):
    path = "{MISSING}"
    if content is not None:
        Path(bad["TMP"], "ch.json").write_text(content, encoding="utf-8")
        path = "{TMP}/ch.json"
    check(capsys, bad, ["channels", "--load", path], expected)


def test_channels_live_errors_one_line(capsys, bad, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    check(
        capsys, bad, ["channels", "@simpleclub"], "no YouTube API key - set YOUTUBE_API_KEY (a read-only key is enough)"
    )
    check(
        capsys, bad, ["channels", "--file", "{MISSING}"], "can't read channel list {MISSING}: No such file or directory"
    )
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    monkeypatch.setattr(kw_mod, "requests_fetch", failing_fetch(ConnectionError(f"url ...&key={KEY}")))
    line = error_line(capsys, ["channels", "--discover", "Biologie Klasse 10"], 1)
    assert (
        line == "aidemy-seo channels: error: YouTube API request failed: can't reach the YouTube API - are you online?"
    )
    monkeypatch.setattr(kw_mod, "requests_fetch", failing_fetch(ModuleNotFoundError("No module named 'requests'")))
    check(
        capsys,
        bad,
        ["channels", "@simpleclub"],
        "live YouTube data needs the optional 'requests' package - pip install 'aidemy-seo[http]'",
    )
    # one failing channel is listed (short reason, key hidden), the command still runs
    monkeypatch.setattr(kw_mod, "requests_fetch", failing_fetch(HTTPError()))
    assert main(["channels", "@simpleclub"]) == 0
    err = capsys.readouterr().err
    assert err == "not found / skipped: @simpleclub (HTTP 403 Forbidden - quotaExceeded)\n" and KEY not in err

    # --save into a folder that doesn't exist (the fake API has one channel without uploads)
    def one_channel(url, params):
        if url.endswith("/channels"):
            snippet = {"title": "simpleclub"}
            uploads = {"relatedPlaylists": {"uploads": "UU1"}}
            return {"items": [{"id": "UC1", "snippet": snippet, "contentDetails": uploads, "statistics": {}}]}
        return {"items": []}

    monkeypatch.setattr(kw_mod, "requests_fetch", one_channel)
    check(
        capsys,
        bad,
        ["channels", "@simpleclub", "--save", "{TMP}/no/such/folder/ch.json"],
        "can't write --save {TMP}/no/such/folder/ch.json: No such file or directory",
    )


def test_unexpected_file_error_is_one_line_too(capsys, bad, monkeypatch):
    # safety net in main(): a file error no handler expected still ends in one line, not a traceback
    from aidemy_seo import cli

    def boom(a):
        raise PermissionError(13, "Permission denied", "/some/file")

    monkeypatch.setitem(cli.HANDLERS, "title", boom)
    line = error_line(capsys, ["title", "x"])
    assert (
        line == "aidemy-seo title: error: can't access /some/file: Permission denied (usage: aidemy-seo title --help)"
    )


def test_good_input_still_works(capsys):
    # nearest legitimate cases: the same commands with good files run as before
    for argv in (["schedule", STATS], ["learn", STATS], ["calibrate", str(FIX / "vidiq_scores_2026-11-12.csv")]):
        assert main(argv) == 0
    capsys.readouterr()
    assert main(["--json", "series", TITLES]) == 0
    assert json.loads(capsys.readouterr().out)["videos"] == 10
