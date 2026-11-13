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
