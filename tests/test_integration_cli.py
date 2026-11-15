"""Integration / end-to-end: every CLI command runs on fixtures, in-process and as the
installed `aidemy-seo` executable. No network (YouTube calls are replaced at the fetch layer)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aidemy_seo import keywords as kw_mod
from aidemy_seo.cli import main

FIX = Path(__file__).parent / "fixtures"
STATS = str(FIX / "stats_synthetic.json")
CONFOUND = str(FIX / "stats_age_confound.json")
BUNDLE = str(FIX / "bundle_biologie_kl10_gentechnik.json")


@pytest.fixture
def offline_autocomplete(monkeypatch):
    """Replaces the live HTTP layer only - everything above it (CLI, ranking) runs for real."""
    table = {"Gentechnik": 10, "Grüne Gentechnik": 6, "Rote Gentechnik": 4}

    def fetch(url, params):
        q = params["q"]
        return [q, [f"{q.lower()} {i}" for i in range(table.get(q, 0))]]

    monkeypatch.setattr(kw_mod, "requests_fetch", fetch)


def run(capsys, *argv):
    assert main(list(argv)) == 0
    return capsys.readouterr().out


def test_keywords_command(capsys, offline_autocomplete):
    out = run(
        capsys,
        "keywords",
        "Nutzen und Risiken ausgewählter transgener Organismen",
        "--short-name",
        "Grüne und Rote Gentechnik",
    )
    assert "best title keyword: Gentechnik" in out and "    10" in out


def test_keywords_json(capsys, offline_autocomplete):
    data = json.loads(run(capsys, "--json", "keywords", "Sagen und Mythen"))
    assert "keywords" in data and "best" in data


def test_title_generate_and_score(capsys):
    out = run(capsys, "title", "Gentechnik", "--generate", "--subject", "Biologie", "--grade", "Klasse 10")
    assert out.splitlines()[0].split("  ", 1)[1].startswith("Gentechnik")
    out = run(capsys, "title", "Bio Kl. 10: Transgene Organismen Arbeitsblatt", "--keyword", "Gentechnik")
    assert "not_a_listing" in out


def test_description_from_file_and_stdin(capsys, tmp_path, monkeypatch):
    f = tmp_path / "d.txt"
    f.write_text("Gentechnik einfach erklärt.\nhttps://eduki.com/de/autor/1/x\n", encoding="utf-8")
    out = run(capsys, "description", str(f), "--keyword", "Gentechnik", "--link-hint", "/material/")
    assert "specific_link" in out
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("kurz"))
    assert "score" in run(capsys, "description", "-")


def test_schedule_and_learn_on_stats(capsys):
    out = run(capsys, "schedule", STATS)
    lines = out.splitlines()
    assert lines[0] == "12 of 12 Shorts have views_24h; the rest are left out"  # coverage is always shown
    assert lines[2].startswith(("Wed", "Thu", "Fri", "Sat", "Sun", "Mon", "Tue"))
    out = run(capsys, "learn", STATS, "--metric", "views_24h")
    assert "question" in out and "helps" in out


def _verdict(out: str, feature: str) -> str:
    line = next(ln for ln in out.splitlines() if ln.startswith(feature + " "))
    return line.split(")  ", 1)[1]


def test_learn_views_per_day_cli(capsys):
    out = run(capsys, "learn", STATS, "--metric", "views_per_day", "--now", "2026-11-15")
    assert out.splitlines()[0] == "12 of 12 videos used (metric views_per_day, ages at 2026-11-15 00:00 UTC)"
    assert _verdict(out, "question") == "helps"
    assert "hint:" not in out  # the metric is already age-fair
    data = json.loads(run(capsys, "--json", "learn", STATS, "--metric", "views_per_day", "--now", "2026-11-15"))
    assert isinstance(data, list) and {"feature", "lift", "verdict"} <= set(data[0])  # JSON shape unchanged
    # the age trap end to end: old question titles "help" on total views, "hurt" per day of age
    assert _verdict(run(capsys, "learn", CONFOUND), "question") == "helps"
    out = run(capsys, "learn", CONFOUND, "--metric", "views_per_day", "--now", "2026-11-15T01:00:00+01:00")
    assert _verdict(out, "question") == "hurts"
    assert out.splitlines()[0] == (
        "12 of 16 videos used (metric views_per_day, ages at 2026-11-15 00:00 UTC); "
        "left out: 2 no publish time, 1 published after now, 1 no views_per_day"
    )


def test_learn_age_window_cli(capsys):
    out = run(capsys, "learn", STATS, "--min-age", "7", "--max-age", "40", "--now", "2026-11-15")
    assert out.splitlines()[0] == (
        "7 of 12 videos used (metric views, age 7-40 days, ages at 2026-11-15 00:00 UTC); "
        "left out: 5 outside the age window"
    )
    assert "hint:" not in out  # an age window is a fair comparison too
    assert "question           with   3 " in out  # s6, s8, s10 (38.4, 36.4, 34.4 days old)
    # one-sided windows are labelled too
    first = run(capsys, "learn", STATS, "--min-age", "40", "--now", "2026-11-15").splitlines()[0]
    assert first.startswith("5 of 12 videos used (metric views, age >= 40 days,")
    first = run(capsys, "learn", STATS, "--max-age", "35.5", "--now", "2026-11-15").splitlines()[0]
    assert first.startswith("3 of 12 videos used (metric views, age <= 35.5 days,")  # s9-s11


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--now", "yesterday"], "argument --now: not an ISO 8601 date/time"),
        (["--min-age", "-1"], "argument --min-age: must be a finite number of days >= 0"),
        (["--min-age", "inf"], "argument --min-age: must be a finite number of days >= 0, got inf"),
        # argparse reads a bare "-inf" as an option ("expected one argument"); with "=" it reaches our check
        (["--max-age=-inf"], "argument --max-age: must be a finite number of days >= 0, got -inf"),
        (["--max-age", "nan"], "argument --max-age: must be a finite number of days >= 0, got nan"),
        (["--max-age", "many"], "argument --max-age: not a number of days"),
        (["--min-age", "30", "--max-age", "7"], "min age 30 days is larger than max age 7 days"),
    ],
)
def test_learn_rejects_bad_age_arguments(capsys, args, message):
    with pytest.raises(SystemExit) as exc:
        main(["learn", STATS, *args])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "usage:" in err and message in err and "Traceback" not in err


def test_learn_default_keeps_behaviour_and_warns(capsys):
    from aidemy_seo.aidemy_pub import load_channel_videos
    from aidemy_seo.learn import feature_lift

    lines = run(capsys, "learn", STATS).splitlines()
    assert lines[0] == "12 of 12 videos used (metric views)"
    assert lines[1].startswith("hint: total views favour older videos")
    before = [  # exactly what `learn` printed before this feature
        f"{f.feature:<18} with {f.with_n:>3} ({f.with_median:>7}) without {f.without_n:>3} "
        f"({f.without_median:>7})  {f.verdict}"
        for f in feature_lift(load_channel_videos(STATS), metric="views", min_group=5)
    ]
    assert lines[2:] == before


def test_experiment_assign_and_report_cli(capsys, tmp_path):
    ledger = str(tmp_path / "experiments.json")
    common = ["--experiment", "hook-2026-11", "--now", "2026-11-15T09:00:00Z"]
    out = run(
        capsys,
        "experiment",
        "assign",
        ledger,
        *common,
        "--key",
        "bio-kl10-gentechnik",
        "--keyword",
        "Gentechnik",
        "--subject",
        "Biologie",
        "--grade",
        "Klasse 10",
        "--arm",
        "question",
        "--arm",
        "musst_du_wissen",
    )
    assert out.splitlines() == [
        "experiment hook-2026-11, key bio-kl10-gentechnik -> arm musst_du_wissen (new)",
        "title: Gentechnik: Das musst du wissen! #Biologie #Klasse10",
    ]
    again = json.loads(
        run(
            capsys,
            "--json",
            "experiment",
            "assign",
            ledger,
            *common,
            "--key",
            "bio-kl10-gentechnik",
            "--keyword",
            "Other",
        )
    )
    assert again["already_assigned"] and again["title"] == "Gentechnik: Das musst du wissen! #Biologie #Klasse10"

    # 16 lessons through the CLI (hash split: 7 question, 9 musst_du_wissen), then "publish" them 20 days ago:
    # question titles earn ~30 views per day, musst_du_wissen titles ~10
    videos = []
    for i in range(16):
        a = json.loads(
            run(
                capsys,
                "--json",
                "experiment",
                "assign",
                ledger,
                *common,
                "--key",
                f"lesson-{i}",
                "--keyword",
                f"Thema {i}",
            )
        )
        per_day = (30 if a["arm"] == "question" else 10) + i % 3
        videos.append({"title": a["title"], "went_public_at": "2026-10-26T09:00:00Z", "views": per_day * 20})
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"videos": videos}, ensure_ascii=False), encoding="utf-8")

    out = run(capsys, "experiment", "report", ledger, str(stats), "--experiment", "hook-2026-11", "--now", "2026-11-15")
    lines = out.splitlines()
    assert lines[0].startswith("16 of 17 assigned videos used (metric views_per_day, age >= 7 days,")
    assert lines[0].endswith("left out: 1 not published yet or title changed")  # bio-kl10-gentechnik
    assert lines[1].startswith("verdict: WINNER = question - beats every other arm (musst_du_wissen: ratio")
    data = json.loads(
        run(
            capsys,
            "--json",
            "experiment",
            "report",
            ledger,
            str(stats),
            "--experiment",
            "hook-2026-11",
            "--now",
            "2026-11-15",
        )
    )
    assert (data["verdict"], data["winner"], data["seed"], data["confidence"]) == ("winner", "question", 0, 0.95)
    assert {a["arm"]: a["used"] for a in data["arms"]} == {"musst_du_wissen": 9, "question": 7}
    strict = json.loads(
        run(
            capsys,
            "--json",
            "experiment",
            "report",
            ledger,
            str(stats),
            "--experiment",
            "hook-2026-11",
            "--now",
            "2026-11-15",
            "--confidence",
            "0.99",
            "--seed",
            "7",
        )
    )
    assert (strict["confidence"], strict["seed"], strict["comparisons"][0]["level"]) == (0.99, 7, 0.99)
    # stricter evidence bar: 10 used videos per arm -> not enough yet
    out = run(
        capsys,
        "experiment",
        "report",
        ledger,
        str(stats),
        "--experiment",
        "hook-2026-11",
        "--now",
        "2026-11-15",
        "--min-group",
        "10",
    )
    assert "verdict: insufficient data - need 10 used videos per arm:" in out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            [
                "assign",
                "{L}",
                "--experiment",
                "e",
                "--key",
                "k2",
                "--keyword",
                "x",
                "--arm",
                "question",
                "--arm",
                "endlich",
            ],
            "arms can't change",
        ),
        (
            [
                "assign",
                "{L}",
                "--experiment",
                "e",
                "--key",
                "k2",
                "--keyword",
                "x",
                "--arm",
                "clickbait",
                "--arm",
                "warum",
            ],
            "unknown arm clickbait",
        ),
        (["assign", "{L}", "--experiment", "e", "--key", " ", "--keyword", "x"], "key must not be empty"),
        (["assign", "{BAD}", "--experiment", "e", "--key", "k", "--keyword", "x"], "is not valid JSON"),
        (["report", "{L}", "{STATS}", "--experiment", "nope"], "no experiment 'nope' in the ledger - it has: e"),
        (["report", "{L}", "{STATS}", "--experiment", "e", "--confidence", "1.5"], "--confidence: must be between 0"),
        (
            ["report", "{L}", "{STATS}", "--experiment", "e", "--confidence", "high"],
            "--confidence: not a number: 'high'",
        ),
        (["report", "{L}", "{STATS}", "--experiment", "e", "--confidence", "nan"], "--confidence: must be between 0"),
        (["report", "{L}", "{STATS}", "--experiment", "e", "--min-group", "0"], "--min-group: must be at least 1"),
        (["report", "{L}", "{STATS}", "--experiment", "e", "--min-group", "2.5"], "--min-group: not a whole number"),
        (["report", "{L}", "{STATS}", "--experiment", "e", "--min-age", "inf"], "--min-age: must be a finite number"),
        (["report", "{L}", "{STATS}", "--experiment", "e", "--now", "soon"], "--now: not an ISO 8601 date/time"),
        (["report", "{L}", "{MISSING}", "--experiment", "e"], "can't read stats file"),
        (["report", "{MISSING}", "{STATS}", "--experiment", "e"], "does not exist"),
    ],
    ids=[
        "changed-arms",
        "unknown-arm",
        "empty-key",
        "broken-ledger",
        "unknown-experiment",
        "confidence",
        "confidence-text",
        "confidence-nan",
        "min-group",
        "min-group-float",
        "min-age-inf",
        "bad-now",
        "missing-stats",
        "missing-ledger",
    ],
)
def test_experiment_cli_errors_exit_2(capsys, tmp_path, argv, message):
    ledger, bad = tmp_path / "l.json", tmp_path / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    assert (
        main(
            [
                "experiment",
                "assign",
                str(ledger),
                "--experiment",
                "e",
                "--key",
                "k",
                "--keyword",
                "Gentechnik",
                "--arm",
                "question",
                "--arm",
                "warum",
            ]
        )
        == 0
    )
    capsys.readouterr()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    paths = {"{L}": str(ledger), "{BAD}": str(bad), "{STATS}": STATS, "{MISSING}": str(tmp_path / "missing.json")}
    with pytest.raises(SystemExit) as exc:
        main(["experiment", *[paths.get(x, x) for x in argv]])
    err = capsys.readouterr().err
    assert exc.value.code == 2 and message in err and "Traceback" not in err
    assert err.strip().splitlines()[-1].startswith("aidemy-seo")  # one error line after the usage
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before  # ledger (and everything else) unchanged


def test_lesson_command(capsys, offline_autocomplete):
    out = run(capsys, "lesson", BUNDLE)
    assert out.startswith("keyword: Gentechnik")


def test_calibrate_command(capsys):
    assert "question" in run(capsys, "calibrate", str(FIX / "vidiq_scores_2026-11-12.csv"))


def _fake_api_fetch(url, params):
    if url.endswith("/search") and params.get("type") == "channel":
        return {"items": [{"id": {"channelId": "UCdisc"}, "snippet": {"channelTitle": "Disc"}}]}
    if url.endswith("/search"):
        return {"items": [{"id": {"videoId": f"t{i}"}} for i in range(3)]}
    if url.endswith("/channels"):
        if params.get("forHandle") == "@missing":
            return {"items": []}
        cid = params.get("id") or params.get("forHandle")
        return {
            "items": [
                {
                    "id": "UC" + cid,
                    "snippet": {"title": f"chan {cid}"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid}},
                    "statistics": {"subscriberCount": "100"},
                }
            ]
        }
    if url.endswith("/playlistItems"):
        return {"items": [{"contentDetails": {"videoId": f"{params['playlistId']}-{i}"}} for i in range(8)]}
    from datetime import datetime, timedelta, timezone

    when = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%dT17:00:00Z")
    return {
        "items": [
            {
                "id": i,
                "snippet": {
                    "title": f"Was ist {i}?" if n % 2 else f"{i} Merksatz",
                    "channelTitle": "c",
                    "publishedAt": when,
                },
                "statistics": {"viewCount": str(300 if n % 2 else 100)},
                "contentDetails": {"duration": "PT45S"},
            }
            for n, i in enumerate(params["id"].split(","))
        ]
    }


def test_benchmark_and_channels_with_fake_api(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(kw_mod, "requests_fetch", _fake_api_fetch)

    out = run(capsys, "benchmark", "Gentechnik", "--shorts")
    assert "titles, median length" in out
    save = tmp_path / "ch.json"
    assert main(["channels", "@a", "@b", "@missing", "--discover", "Biologie", "--save", str(save)]) == 0
    cap = capsys.readouterr()
    assert "BEST POSTING SLOTS" in cap.out and "chan @a" in cap.out
    assert "@missing" in cap.err  # a channel that doesn't exist is reported, not hidden
    assert json.loads(save.read_text())  # saved raw data reloads offline
    out = run(capsys, "channels", "--load", str(save))
    assert "TITLE STYLES" in out


def test_installed_executable_end_to_end(tmp_path):
    exe = shutil.which("aidemy-seo")
    if not exe:
        pytest.skip("package not installed (pip install -e .)")
    r = subprocess.run(
        [exe, "--json", "title", "Gentechnik", "--generate", "--subject", "Biologie", "--grade", "Klasse 10"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0 and json.loads(r.stdout)[0]["title"].startswith("Gentechnik")
