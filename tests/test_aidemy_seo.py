"""Tests use real AiDemy data where it exists (a real lesson bundle, real vidIQ scores seen in
YouTube Studio on 2026-11-12, real titles and description text) and recorded/fake network
responses - no test touches the network."""
import json
from pathlib import Path

import pytest

from aidemy_seo import (Autocomplete, audit_description, best_hours, best_slots, best_title_keyword, calibrate,
                        candidates, feature_lift, optimize_title, rank, score_title, title_patterns)
from aidemy_seo.aidemy_pub import suggest_for_lesson
from aidemy_seo.cli import main
from aidemy_seo.youtube_api import YouTubeAPI, _duration

FIX = Path(__file__).parent / "fixtures"
BUNDLE = json.loads((FIX / "bundle_biologie_kl10_gentechnik.json").read_text(encoding="utf-8"))


def fake_autocomplete(table: dict):
    """Recorded YouTube autocomplete shape: ["query", [suggestions...]]."""
    def fetch(url, params):
        q = params["q"]
        n = table.get(q, 0)
        return [q, [f"{q.lower()} {i}" for i in range(n)] + ["something else"]]
    return Autocomplete(fetch=fetch)


# ---------------------------------------------------------------- keywords
def test_candidates_real_lesson_gentechnik():
    c = [p for p, _ in candidates(BUNDLE["meta"]["topic"], short_name=BUNDLE["overview"]["topicShortName"],
                                  key_terms=[k["term"] for k in BUNDLE["keyTerms"]])]
    # must-catch (real Short FjLOZz9YCDs, vidIQ 73): the searched head noun is offered
    assert "Gentechnik" in c and "Grüne Gentechnik" in c and "Rote Gentechnik" in c
    # must-not-flag: the bare adjective, generic words and side terms are never candidates
    assert "Grüne" not in c and "Nutzen" not in c and "Bt-Mais" not in c


def test_demand_counts_only_prefix_matches_and_unknown_is_minus_one():
    ac = fake_autocomplete({"Gentechnik": 7})
    assert ac.demand("Gentechnik") == 7

    def boom(url, params):
        raise OSError("offline")
    assert Autocomplete(fetch=boom).demand("Gentechnik") == -1


def test_rank_and_best_keyword_pairs_searched_terms():
    ac = fake_autocomplete({"Gentechnik": 10, "Grüne Gentechnik": 6, "Transgene Organismen": 1})
    cands = candidates(BUNDLE["meta"]["topic"], short_name=BUNDLE["overview"]["topicShortName"])
    ranked = rank(cands, ac.demand)
    assert ranked[0].phrase == "Gentechnik"
    # "Grüne Gentechnik" shares the stem -> not paired; nothing else searched >= 3
    assert best_title_keyword(ranked) == "Gentechnik"


def test_best_keyword_offline_is_empty():
    def boom(url, params):
        raise OSError
    ranked = rank(candidates("Sagen und Mythen"), Autocomplete(fetch=boom).demand)
    assert best_title_keyword(ranked) == ""


def test_related_filters_drift():
    ac = Autocomplete(fetch=lambda u, p: [p["q"], ["limes grenze rom", "limes mathe grenzwert", "pokemon"]])
    rel = ac.related("Limes")
    assert "pokemon" not in rel and "limes grenze rom" in rel


# ---------------------------------------------------------------- titles
def test_score_title_flags_listing_label():
    bad = score_title("Bio Kl. 10: Transgene Organismen Arbeitsblatt", "Gentechnik")
    assert "not_a_listing" in " ".join(bad.issues) and "keyword_first" in " ".join(bad.issues)


def test_optimize_title_real_lesson_keeps_both_hashtags_and_leads_with_keyword():
    res = optimize_title("Gentechnik", subject="Biologie", grade="Klasse 10")
    assert res and all(r.title.startswith("Gentechnik") for r in res[:3])
    assert all(len(r.title) <= 66 for r in res)
    assert res[0].title.endswith("#Biologie #Klasse10")
    assert res[0].total >= score_title("Transgene Organismen: Das musst du wissen! #Biologie #Klasse10",
                                       "Gentechnik").total


def test_optimize_title_never_doubles_colon():
    res = optimize_title("Indien bis Kongo: Dekolonisierung", subject="Geschichte", grade="Klasse 9")
    assert all(r.title.count(":") <= 1 for r in res)


def test_calibrate_on_real_vidiq_scores():
    rows = [tuple(l.rsplit(";", 1)) for l in (FIX / "vidiq_scores_2026-11-12.csv").read_text(encoding="utf-8")
            .splitlines()[1:]]
    res = calibrate([(t, float(s)) for t, s in rows])
    assert res["by_shape"]["question"] == 79.0 and res["n"]["must_know"] == 4


# ---------------------------------------------------------------- descriptions
REAL_DESC = ("Wahrnehmung & Wahrheit einfach erklärt – Ethik Klasse 6.\n"
             "Dieses umfassende Materialpaket für den Ethikunterricht der Klasse 6 bietet strukturierte Lernzettel, "
             "ein Fachbegriffe-Glossar und sechs fertige Klassenarbeiten in drei Schwierigkeitsstufen.\n\n"
             "Das ganze Lernpaket zu „Wahrnehmung & Wahrheit“ (Ethik Klasse 6) – Arbeitsblätter & Klassenarbeiten "
             "mit Lösungen: https://eduki.com/de/autor/4949577/aidemy\n")


def test_description_real_text_finds_author_page_link():
    a = audit_description(REAL_DESC, keywords=["Wahrnehmung", "Ethik Klasse 6"], link_hint="/material/")
    joined = " ".join(a.issues)
    assert "specific_link" in joined and "hashtags" in joined
    assert "keywords_first_200" not in joined


def test_description_good_one_scores_high():
    good = ("Gentechnik einfach erklärt – Biologie Klasse 10.\n"
            "Alle Arbeitsblätter mit Lösungen: https://eduki.com/de/material/2427015/x\n\n" + "Text. " * 60 +
            "\n\nAbonniere den Kanal und schreib deine Frage in die Kommentare.\n\n#Gentechnik #Biologie #Klasse10")
    a = audit_description(good, keywords=["Gentechnik", "Biologie Klasse 10"], link_hint="/material/")
    assert a.score >= 90, a.issues


# ---------------------------------------------------------------- schedule / learn / benchmark
VIDEOS = [  # synthetic example data (not real channel numbers) - shape of aidemy_pub stats.json
    {"kind": "short", "title": "A – kannst du es erklären?", "went_public_at": "2026-11-03T14:30:00Z", "views_24h": 120, "views": 300},
    {"kind": "short", "title": "B – kannst du es erklären?", "went_public_at": "2026-11-10T14:30:00Z", "views_24h": 100, "views": 250},
    {"kind": "short", "title": "C: Das musst du wissen!", "went_public_at": "2026-11-17T14:30:00Z", "views_24h": 140, "views": 280},
    {"kind": "short", "title": "D: Das musst du wissen!", "went_public_at": "2026-11-04T18:00:00Z", "views_24h": 20, "views": 60},
    {"kind": "long", "title": "Long video", "went_public_at": "2026-11-04T09:00:00Z", "views_24h": 900, "views": 900},
]


def test_best_slots_ranks_by_median_and_flags_thin_data():
    slots = best_slots(VIDEOS, min_videos=3)
    assert slots[0].label == "Tue 15:00" and slots[0].enough_data and slots[0].videos == 3
    assert all(s.label != "Wed 10:00" for s in slots)       # long video excluded by default
    assert not [s for s in slots if s.label == "Wed 19:00"][0].enough_data


def test_best_hours():
    assert best_hours(VIDEOS)[0][0] in (10, 15)


def test_feature_lift_says_not_enough_data_on_young_channel():
    res = feature_lift(VIDEOS, min_group=5)
    assert all(f.lift is None and "not enough data" in f.verdict for f in res)


def test_feature_lift_finds_real_effect_with_enough_data():
    vids = [{"title": f"T{i} – kannst du es erklären?", "views": 200} for i in range(6)] + \
           [{"title": f"T{i}: Merksatz", "views": 50} for i in range(6)]
    q = [f for f in feature_lift(vids) if f.feature == "question"][0]
    assert q.verdict == "helps" and q.lift == 4.0


def test_title_patterns():
    p = title_patterns([("Gentechnik einfach erklärt", 1000), ("Was ist Gentechnik?", 5000),
                        ("Gentechnik in 5 Minuten 🧬", 300)], "Gentechnik")
    assert p.n == 3 and p.share_question == pytest.approx(1 / 3) and p.share_number == pytest.approx(1 / 3)
    assert p.share_keyword_first == pytest.approx(2 / 3) and p.weighted_top_words[0][0] == "gentechnik"


def test_youtube_api_needs_key_and_parses():
    with pytest.raises(RuntimeError):
        YouTubeAPI(api_key="", fetch=lambda u, p: {}).top_videos("x")

    def fetch(url, params):
        if url.endswith("/search"):
            return {"items": [{"id": {"videoId": "v1"}}]}
        return {"items": [{"id": "v1", "snippet": {"title": "Gentechnik einfach erklärt", "channelTitle": "C",
                                                   "publishedAt": "2025-01-01T00:00:00Z", "tags": ["bio"]},
                           "statistics": {"viewCount": "12345"}, "contentDetails": {"duration": "PT1M5S"}}]}
    v = YouTubeAPI(api_key="k", fetch=fetch).top_videos("Gentechnik")
    assert v[0].views == 12345 and v[0].duration_s == 65 and _duration("PT1H2M3S") == 3723


# ---------------------------------------------------------------- integration + CLI
def test_suggest_for_real_lesson_bundle():
    res = suggest_for_lesson(BUNDLE, autocomplete=fake_autocomplete({"Gentechnik": 10, "Grüne Gentechnik": 6}))
    assert res["keyword"] == "Gentechnik" and res["titles"][0]["title"].startswith("Gentechnik")


def test_cli_title_and_calibrate(capsys):
    assert main(["title", "Wahrnehmung: Relativität & Sinne #Ethik #Klasse6", "--keyword", "Wahrnehmung"]) == 0
    assert "score" in capsys.readouterr().out
    assert main(["--json", "calibrate", str(FIX / "vidiq_scores_2026-11-12.csv")]) == 0
    assert json.loads(capsys.readouterr().out)["by_shape"]["question"] == 79.0
