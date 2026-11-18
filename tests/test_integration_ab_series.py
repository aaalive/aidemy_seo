"""Integration / end-to-end: ab-pack, ab-results and series through the CLI (in-process and as the installed
executable), on the fixtures. Offline. Input files must come out byte-for-byte unchanged."""

import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from aidemy_seo.cli import main

FIX = Path(__file__).parent / "fixtures"
TITLES = FIX / "titles_to_fix.csv"
RESULTS = FIX / "ab_results.csv"


def run(capsys, *argv):
    assert main([str(a) for a in argv]) == 0
    return capsys.readouterr().out


def test_ab_pack_cli_default_and_weights(capsys, tmp_path):
    before = TITLES.read_bytes()
    out = tmp_path / "pack.csv"
    text = run(capsys, "ab-pack", TITLES, "--out", out).splitlines()
    assert text[0] == f"wrote 27 titles for 10 of 10 videos to {out} (0 skipped, 3 variants dropped)"
    assert text[1] == "order: search, question, why (default - no --weights)"
    # v02, v03, v04: the search title doesn't fit 66 characters with #Fach #KlasseN (never dropped), so only
    # the search variant is dropped - with a warning - and the video is tested with question + why
    assert (
        "  line 4: search variant dropped - the search title is 67 characters with #Biologie #Klasse11 (max 66) - "
        "series hashtags are never dropped; testing question, why"
    ) in text
    rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
    assert rows[0] == ["video_id", "variant", "title", "length"] and len(rows) == 28
    per_video = {}
    for r in rows[1:]:
        per_video.setdefault(r[0], []).append(r[1])
    assert per_video == {
        **{v: ["search", "question", "why"] for v in ("v01", "v05", "v06", "v07", "v08", "v09", "v10")},
        **{v: ["question", "why"] for v in ("v02", "v03", "v04")},
    }
    assert rows[13:16] == [
        ["v06", "search", "Atmung einfach erklärt – das musst du wissen! #Biologie #Klasse11", "65"],
        ["v06", "question", "Atmung – kannst du es erklären? #Biologie #Klasse11", "51"],
        ["v06", "why", "Warum Atmung? Einfach erklärt #Biologie #Klasse11", "49"],
    ]
    assert all(int(r[3]) == len(r[2]) <= 66 for r in rows[1:])
    # the full loop: results (5 decided) -> weights -> the next pack puts the most winning variant first
    weights = tmp_path / "weights.json"
    run(capsys, "ab-results", RESULTS, "--weights", weights)
    j = json.loads(run(capsys, "--json", "ab-pack", TITLES, "--out", out, "--weights", weights))
    assert j["order"] == ["why", "search", "question"]
    assert j["weights"] == {"search": 0.25, "question": 0.2, "why": 0.75}
    assert (j["decided"], j["weights_applied"]) == (5, True)
    assert [r["variant"] for r in j["rows"][:3]] == ["why", "search", "question"]
    assert (j["videos"], j["packed"], j["skipped"], j["out"]) == (10, 10, 0, str(out))
    assert [(d["video_id"], d["variant"]) for d in j["dropped"]] == [
        ("v02", "search"),
        ("v03", "search"),
        ("v04", "search"),
    ]
    got = [r[1] for r in csv.reader(io.StringIO(out.read_text(encoding="utf-8")))]
    assert got[1:4] == ["why", "search", "question"]
    # fewer than 5 decided tests: the usual order
    few = tmp_path / "few.json"
    few.write_text('{"decided": 4, "weights": {"why": 1.0}}', encoding="utf-8")
    text = run(capsys, "ab-pack", TITLES, "--out", out, "--weights", few).splitlines()
    assert (
        text[1] == f"order: search, question, why (default - only 4 decided tests in {few}, the weights count from 5)"
    )
    assert TITLES.read_bytes() == before


def test_ab_results_cli_fixture(capsys, tmp_path):
    before = RESULTS.read_bytes()
    weights = tmp_path / "weights.json"
    text = run(capsys, "ab-results", RESULTS, "--weights", weights).splitlines()
    assert text[0].startswith("8 videos in") and "5 winners, 2 inconclusive, 1 not evaluated" in text[0]
    assert "  v09 (line 14): only 1 variant (search) - a test compares 2 or 3" in text
    assert json.loads(weights.read_text(encoding="utf-8")) == {
        "decided": 5,
        "weights": {"search": 0.25, "question": 0.2, "why": 0.75},
    }
    j = json.loads(run(capsys, "--json", "ab-results", RESULTS, "--weights", weights))
    assert [(t["video_id"], t["result"], t["winner"]) for t in j["tests"]] == [
        ("v02", "winner", "why"),
        ("v04", "inconclusive", None),
        ("v05", "winner", "search"),
        ("v06", "winner", "why"),
        ("v07", "inconclusive", None),
        ("v08", "winner", "why"),
        ("v10", "winner", "question"),
    ]
    assert j["decided"] == 5 and j["weights_file"] == str(weights)
    assert RESULTS.read_bytes() == before


def test_series_cli_text_and_json(capsys):
    before = TITLES.read_bytes()
    text = run(capsys, "series", TITLES).splitlines()
    assert text[0] == f"2 series in {TITLES}: 5 of 10 videos in a series, 5 not sorted, 0 skipped"
    assert "Biologie Klasse 11 (3 videos)" in text and "Ethik Klasse 5 (2 videos)" in text
    j = json.loads(run(capsys, "--json", "series", TITLES))
    assert [(s["name"], s["count"]) for s in j["series"]] == [("Biologie Klasse 11", 3), ("Ethik Klasse 5", 2)]
    assert len(j["not_sorted"]) == 5
    assert TITLES.read_bytes() == before


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["ab-pack", "{TITLES}"], "the following arguments are required: --out"),
        (["ab-pack", "{COPY}", "--out", "{COPY}"], "is the input CSV - choose another file"),
        (["ab-pack", "{COPY}", "--out", "{OUT}", "--weights", "{COPY}"], "can't read weights file"),
        (["ab-pack", "{COPY}", "--out", "{WEIGHTS}", "--weights", "{WEIGHTS}"], "is the weights file"),
        (["ab-pack", "{MISSING}", "--out", "{OUT}"], "file not found"),
        (["ab-pack", "{COPY}", "--out", "{OUT}", "--weights", "{MISSING}"], "weights file not found"),
        (["ab-pack", "{COPY}", "--out", "{OUT}", "--weights", "{FLAT}"], "must look like"),
        (["ab-pack", "{RESULTS_COPY}", "--out", "{OUT}"], "missing column(s): title, keyword"),
        (["ab-results", "{RESULTS_COPY}"], "the following arguments are required: --weights"),
        (["ab-results", "{RESULTS_COPY}", "--weights", "{RESULTS_COPY}"], "is the input CSV"),
        (["ab-results", "{COPY}", "--weights", "{OUT}"], "missing column(s): variant, watch_time_share"),
        (["series", "{MISSING}"], "file not found"),
        (["series", "{LATIN1}"], "not UTF-8"),
    ],
)
def test_ab_and_series_cli_errors_exit_2(capsys, tmp_path, argv, message):
    copy, results_copy = tmp_path / "titles.csv", tmp_path / "results.csv"
    shutil.copy(TITLES, copy)
    shutil.copy(RESULTS, results_copy)
    (tmp_path / "latin1.csv").write_bytes("title\nGrüne #Biologie #Klasse10\n".encode("latin-1"))
    (tmp_path / "weights.json").write_text('{"decided": 5, "weights": {"why": 1}}', encoding="utf-8")
    (tmp_path / "flat.json").write_text('{"why": 1}', encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    paths = {
        "{TITLES}": str(TITLES),
        "{COPY}": str(copy),
        "{RESULTS_COPY}": str(results_copy),
        "{OUT}": str(tmp_path / "out.csv"),
        "{WEIGHTS}": str(tmp_path / "weights.json"),
        "{FLAT}": str(tmp_path / "flat.json"),
        "{MISSING}": str(tmp_path / "missing.csv"),
        "{LATIN1}": str(tmp_path / "latin1.csv"),
    }
    with pytest.raises(SystemExit) as exc:
        main([paths.get(x, x) for x in argv])
    captured = capsys.readouterr()
    assert exc.value.code == 2 and message in captured.err and "Traceback" not in captured.err
    assert captured.out == ""
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before  # nothing written, nothing changed


def test_ab_pack_installed_executable(tmp_path):
    exe = shutil.which("aidemy-seo")
    if not exe:
        pytest.skip("package not installed (pip install -e .)")
    out = tmp_path / "pack.csv"
    r = subprocess.run(
        [exe, "--json", "ab-pack", str(TITLES), "--out", str(out)], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0 and json.loads(r.stdout)["packed"] == 10 and out.is_file()


@pytest.mark.parametrize(
    ("argv", "line"),
    [
        (
            ["ab-pack", "{TITLES}"],
            "aidemy-seo ab-pack: error: the following arguments are required: --out (usage: aidemy-seo ab-pack --help)",
        ),
        (
            ["ab-pack", "{TITLES}", "--out", "{TITLES}"],
            "aidemy-seo ab-pack: error: --out {TITLES} is the input CSV - choose another file, an input is never "
            "overwritten (usage: aidemy-seo ab-pack --help)",
        ),
        (
            ["ab-results", "{MISSING}", "--weights", "{OUT}"],
            "aidemy-seo ab-results: error: file not found: {MISSING} (usage: aidemy-seo ab-results --help)",
        ),
        (
            ["series", "{MISSING}"],
            "aidemy-seo series: error: file not found: {MISSING} (usage: aidemy-seo series --help)",
        ),
        (
            ["learn", "{TITLES}", "--min-age", "-1"],
            "aidemy-seo learn: error: argument --min-age: must be a finite number of days >= 0, got -1 "
            "(usage: aidemy-seo learn --help)",
        ),
        (
            ["experiment", "report", "{MISSING}", "{MISSING}", "--experiment", "e"],
            "aidemy-seo experiment report: error: ledger {MISSING} does not exist - create it with `experiment assign` "
            "(usage: aidemy-seo experiment report --help)",
        ),
    ],
)
def test_errors_are_one_line(capsys, tmp_path, argv, line):
    paths = {"{TITLES}": str(TITLES), "{MISSING}": str(tmp_path / "missing.csv"), "{OUT}": str(tmp_path / "w.json")}

    def fill(text):
        for k, v in paths.items():
            text = text.replace(k, v)
        return text

    with pytest.raises(SystemExit) as exc:
        main([fill(x) for x in argv])
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert err == fill(line) + "\n"  # exactly one line - no usage block before it
    # --help still shows the full usage
    with pytest.raises(SystemExit) as exc:
        main([argv[0], "--help"] if argv[0] != "experiment" else ["experiment", "report", "--help"])
    assert exc.value.code == 0 and capsys.readouterr().out.startswith("usage: aidemy-seo ")
