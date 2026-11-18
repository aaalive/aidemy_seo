"""Title A/B packs and results (specs/ab-testing.md). Offline; real titles from tests/fixtures/titles_to_fix.csv
and the Gentechnik lesson, real-shaped Test & Compare results in tests/fixtures/ab_results.csv."""

import csv
import io
import json
import os
import re
import stat
from decimal import Decimal
from pathlib import Path

import pytest

from aidemy_seo.abtest import (
    INCONCLUSIVE,
    VARIANTS,
    WINNER,
    AbError,
    ab_pack,
    ab_results,
    compute_weights,
    decide,
    load_weights,
    make_pack,
    pack_hashtags,
    pack_titles,
    parse_share,
    read_results,
    variant_order,
)
from aidemy_seo.series import series_key
from aidemy_seo.titles import MAX_TITLE_LEN, TEMPLATES, build_title

FIX = Path(__file__).parent / "fixtures"
TITLES = FIX / "titles_to_fix.csv"
RESULTS = FIX / "ab_results.csv"
GEN_TITLE = "Gentechnik: Das musst du wissen! #Biologie #Klasse10"


def rows_of(text):
    return list(csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=";" if ";" in text.splitlines()[0] else ","))


def results_csv(tmp_path, body, header="video_id,variant,watch_time_share"):
    path = tmp_path / "results.csv"
    path.write_text(header + "\n" + body, encoding="utf-8")
    return path


# ---------------------------------------------------------------- ab-pack: titles
def titles_of(keyword, title):
    """The fitting titles as {variant: title}."""
    return dict(pack_titles(keyword, title)[0])


def test_pack_titles_use_search_question_why_templates():
    assert {"search": TEMPLATES[1], "question": TEMPLATES[0], "why": TEMPLATES[3]} == VARIANTS
    titles, dropped = pack_titles("Mitose", "Mitose: Das musst du wissen! #Biologie #Klasse9")
    assert titles == [
        ("search", "Mitose einfach erklärt – das musst du wissen! #Biologie #Klasse9"),
        ("question", "Mitose – kannst du es erklären? #Biologie #Klasse9"),
        ("why", "Warum Mitose? Einfach erklärt #Biologie #Klasse9"),
    ]
    assert dropped == []
    for variant, t in titles:  # exactly what build_title makes - no second title builder
        assert t == build_title("Mitose", VARIANTS[variant], ["#Biologie", "#Klasse9"], MAX_TITLE_LEN)
        assert len(t) <= MAX_TITLE_LEN


def test_pack_hashtags_unique_and_at_most_two():
    # real title v09: the same hashtag twice and 3 different ones
    assert pack_hashtags("🔥🔥 Mitose einfach erklärt!!! #Biologie #biologie #Klasse9 #Zellbiologie")[0] == [
        "#Biologie",
        "#Klasse9",
    ]
    assert pack_hashtags("#Ökologie #ökologie #OEKOLOGIE")[0] == ["#Ökologie", "#OEKOLOGIE"]  # fold: ö -> o, not oe
    assert pack_hashtags("Die Worttrennung, die in jeder Klassenarbeit vorkommt 📚 #Deutsch")[0] == ["#Deutsch"]
    assert pack_hashtags("Zellteilung im Überblick")[0] == []
    titles = titles_of("Mitose", "Mitose!!! #Biologie #biologie #Klasse9 #Zellbiologie")
    assert titles["question"] == "Mitose – kannst du es erklären? #Biologie #Klasse9"
    assert all(t.count("#") <= 2 and "#Zellbiologie" not in t for t in titles.values())
    assert titles_of("Mitose", "Mitose im Überblick")["why"] == "Warum Mitose? Einfach erklärt"


def test_pack_never_drops_series_hashtags():
    # the series hashtags are chosen first: #Shorts or a topic tag never crowd out #KlasseN or #Fach
    assert pack_hashtags("Mitose #Shorts #Biologie #Klasse9") == (["#Biologie", "#Klasse9"], ["#Biologie", "#Klasse9"])
    assert pack_hashtags("Mitose #Zellbiologie #Shorts #Klasse9") == (
        ["#Zellbiologie", "#Klasse9"],
        ["#Zellbiologie", "#Klasse9"],
    )
    assert pack_hashtags("Mitose #Shorts #YouTubeShorts #Klasse5") == (["#Shorts", "#Klasse5"], ["#Klasse5"])
    assert pack_hashtags("Mitose #Biologie #Zellbiologie") == (["#Biologie", "#Zellbiologie"], [])
    # real v06: 65 characters with both series hashtags - they fit and stay
    assert titles_of("Atmung", "Atmung & Gärung: Das musst du wissen! #Biologie #Klasse11")["search"] == (
        "Atmung einfach erklärt – das musst du wissen! #Biologie #Klasse11"
    )
    # boundary: exactly 66 characters with both series hashtags fit
    fits = "x" * (66 - len(VARIANTS["search"].format(x="") + " #Biologie #Klasse11"))
    assert len(titles_of(fits, "#Biologie #Klasse11")["search"]) == 66
    # #KlasseN without a subject: only the other hashtag is dropped
    assert titles_of("alleine leben toll", "#Klasse5 #Shorts")["search"] == (
        "alleine leben toll einfach erklärt – das musst du wissen! #Klasse5"
    )
    # every packed title of the real fixture stays in the series of its video
    rep = make_pack(TITLES)
    current = {row["video_id"]: row["title"] for row in csv.DictReader(io.StringIO(TITLES.read_text("utf-8")))}
    assert all(series_key(r.title) == series_key(current[r.video_id]) for r in rep.rows)
    assert all("#Klasse" in r.title for r in rep.rows if "#Klasse" in current[r.video_id])


def test_pack_keeps_grade_ranges_and_levels():
    # must catch: a plain hashtag split turns "#Klasse11-12" into "#Klasse11" - the new titles would
    # change the video's grade. The range is kept as written, like #KlasseN, and never dropped
    assert pack_hashtags("Mitose #Biologie #Klasse11-12") == (["#Biologie", "#Klasse11-12"], ["#Klasse11-12"])
    titles = titles_of("Mitose", "Mitose #Biologie #Klasse11-12")
    assert titles["question"].endswith("#Biologie #Klasse11-12") and titles["why"].endswith("#Biologie #Klasse11-12")
    # search: 68 characters with both - the title is no series (a range is no single grade), so #Biologie
    # may go; the range stays
    assert titles["search"] == "Mitose einfach erklärt – das musst du wissen! #Klasse11-12"
    assert not any(t.endswith("#Klasse11") for t in titles.values())
    # levels are grade information too: kept, never dropped, and never mistaken for the subject
    assert pack_hashtags("Mitose #Shorts #Q11") == (["#Shorts", "#Q11"], ["#Q11"])
    assert pack_hashtags("Mitose #Oberstufe #Biologie #Klasse11") == (
        ["#Biologie", "#Klasse11"],
        ["#Biologie", "#Klasse11"],
    )  # the series hashtags win the 2 slots over the level
    long_keyword = "x" * (66 - len(VARIANTS["search"].format(x="") + " #Q11"))
    assert titles_of(long_keyword, "#Shorts #Q11")["search"].endswith("wissen! #Q11")  # #Shorts dropped, not #Q11


def test_pack_drops_only_the_variant_that_does_not_fit_v02_v04():
    # real v02-v04: with their series hashtags the search title is 68 / 67 / 68 characters. Dropping
    # #KlasseN would take the video out of its series, so only the search variant is dropped - the
    # video keeps question + why, a valid 2-title test
    rep = make_pack(TITLES, out="pack.csv")
    by_video = {}
    for r in rep.rows:
        by_video.setdefault(r.video_id, []).append((r.variant, r.title))
    assert by_video["v02"] == [
        ("question", "Raubtiere – kannst du es erklären? #Biologie #Klasse11"),
        ("why", "Warum Raubtiere? Einfach erklärt #Biologie #Klasse11"),
    ]
    assert by_video["v03"] == [
        ("question", "Neobiota – kannst du es erklären? #Biologie #Klasse11"),
        ("why", "Warum Neobiota? Einfach erklärt #Biologie #Klasse11"),
    ]
    assert by_video["v04"] == [
        ("question", "alleine leben – kannst du es erklären? #Ethik #Klasse5"),
        ("why", "Warum alleine leben? Einfach erklärt #Ethik #Klasse5"),
    ]
    assert all(len(v) == 3 for k, v in by_video.items() if k not in {"v02", "v03", "v04"})
    assert all(r.length <= 66 for r in rep.rows)  # the 66 limit holds for every title
    assert (rep.videos, rep.packed, len(rep.rows)) == (10, 10, 27)
    # each dropped variant is warned about (not a skipped row) and listed in the report
    series = "(max 66) - series hashtags are never dropped; testing question, why"
    assert [(w.line, w.message, w.skipped_row) for w in rep.warnings[1:]] == [
        (3, f"search variant dropped - the search title is 68 characters with #Biologie #Klasse11 {series}", False),
        (4, f"search variant dropped - the search title is 67 characters with #Biologie #Klasse11 {series}", False),
        (5, f"search variant dropped - the search title is 68 characters with #Ethik #Klasse5 {series}", False),
    ]
    assert [(d.line, d.video_id, d.variant) for d in rep.dropped] == [
        (3, "v02", "search"),
        (4, "v03", "search"),
        (5, "v04", "search"),
    ]
    assert rep.lines()[0] == "wrote 27 titles for 10 of 10 videos to pack.csv (0 skipped, 3 variants dropped)"
    # with weights the 2 remaining titles keep the weighted order
    titles, dropped = pack_titles("Neobiota", "#Biologie #Klasse11", ["why", "search", "question"])
    assert [v for v, _ in titles] == ["why", "question"] and [v for v, _ in dropped] == ["search"]


def test_pack_drops_hashtags_to_fit_66_and_skips_when_fewer_than_2_titles_fit():
    # not a series title: hashtags are dropped from the end to fit
    titles = titles_of("Neobiota", "Neobiota & Selbstregulation #Biologie #Zellbiologie")
    assert titles["search"] == "Neobiota einfach erklärt – das musst du wissen! #Biologie"
    assert titles["question"].endswith("#Biologie #Zellbiologie")
    # boundary: 66 characters fit exactly, 67 without hashtags are dropped - never cut
    fits = "x" * (66 - len(VARIANTS["search"].format(x="")))
    assert len(titles_of(fits, "")["search"]) == 66
    titles, dropped = pack_titles(fits + "y", "#Biologie")
    assert [v for v, _ in titles] == ["question", "why"]
    assert dropped == [("search", "the search title is 67 characters even without hashtags (max 66)")]
    # the 42-character keyword: only the why title fits - one title is no test, the video is skipped
    titles, dropped = pack_titles("Neobiota & Selbstregulation in Ökosystemen", "Ökosysteme #Biologie")
    assert [v for v, _ in titles] == ["why"] and [v for v, _ in dropped] == ["search", "question"]


# ---------------------------------------------------------------- ab-pack: file
def test_make_pack_rows_columns_and_warnings(tmp_path):
    rep = make_pack(TITLES, out="pack.csv")
    assert rep.videos == 10 and rep.packed == 10 and len(rep.rows) == 27
    assert [(r.video_id, r.variant) for r in rep.rows[:6]] == [
        ("v01", "search"),
        ("v01", "question"),
        ("v01", "why"),
        ("v02", "question"),
        ("v02", "why"),
        ("v03", "question"),
    ]
    assert all(r.length == len(r.title) <= 66 for r in rep.rows)
    assert rows_of(rep.csv())[0] == ["video_id", "variant", "title", "length"]
    assert rows_of(rep.csv())[1] == [
        "v01",
        "search",
        "Worttrennung einfach erklärt – das musst du wissen! #Deutsch",
        "60",
    ]
    assert [(w.line, w.message[:23]) for w in rep.warnings] == [
        (None, "ignored columns: descri"),
        (3, "search variant dropped "),
        (4, "search variant dropped "),
        (5, "search variant dropped "),
    ]
    # bad rows are skipped with their line, never guessed
    path = tmp_path / "in.csv"
    path.write_text(
        "video_id;title;keyword\n"
        f"a1;{GEN_TITLE};Mitose\n"  # line 2 ok
        ";Mitose #Biologie;Mitose\n"  # line 3 no video_id
        "a1;Proteine #Chemie;Proteine\n"  # line 4 same video again
        "a3;Atmung #Biologie;  \n"  # line 5 no keyword
        "a4;  ;Atmung\n"  # line 6 no title
        "a5;kaputt\n"  # line 7 wrong number of fields
        "a6;Ökosysteme #Biologie;Neobiota & Selbstregulation in Ökosystemen\n"  # line 8 too long
        ";;\n",  # blank row: ignored
        encoding="utf-8",
    )
    rep = make_pack(path)
    assert rep.videos == 7 and rep.packed == 1 and {r.video_id for r in rep.rows} == {"a1"}
    assert [(w.line, w.message) for w in rep.warnings] == [
        (3, "skipped - empty video_id"),
        (4, "skipped - video_id a1 is already on line 2"),
        (5, "skipped - empty keyword"),
        (6, "skipped - empty title"),
        (7, "skipped - 2 fields, header has 3"),
        (
            8,
            "skipped - a test needs at least 2 titles, only 1 fits 66 characters: the search title is 81 characters "
            "even without hashtags (max 66); the question title is 67 characters even without hashtags (max 66) - "
            "use a shorter keyword",
        ),
    ]
    assert all(w.skipped_row for w in rep.warnings)
    only_bad = tmp_path / "bad.csv"
    only_bad.write_text("video_id,title,keyword\n,Mitose #Biologie,Mitose\n", encoding="utf-8")
    assert make_pack(only_bad).lines()[2:4] == ["TITLES", "  (no valid rows)"]


def weights_file(tmp_path, weights, decided, name="w.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"decided": decided, "weights": weights}), encoding="utf-8")
    return path


def test_pack_order_follows_weights(tmp_path):
    assert variant_order() == variant_order(None) == ["search", "question", "why"]
    assert variant_order({"search": 0.33, "question": 0.0, "why": 0.67}) == ["why", "search", "question"]
    assert variant_order({"search": 0.2, "question": 0.5, "why": 0.5}) == ["question", "why", "search"]  # ties: default
    # a missing variant has no weight: unknown, it keeps its default place (not last)
    assert variant_order({"question": 0.5, "why": 0.5}) == ["search", "question", "why"]
    assert variant_order({"search": 0.0, "question": 0.0, "why": 0.0}) == ["search", "question", "why"]
    weights = weights_file(tmp_path, {"search": 0.2, "question": 0.2, "why": 0.6}, 5)
    rep = ab_pack(TITLES, tmp_path / "pack.csv", weights_path=weights)
    assert rep.order == ["why", "search", "question"] and rep.weights_applied
    got = rows_of((tmp_path / "pack.csv").read_text(encoding="utf-8"))
    assert [r[1] for r in got[1:6]] == ["why", "search", "question", "why", "question"]  # v02: no search title
    assert [r[0] for r in got[1:6]] == ["v01"] * 3 + ["v02"] * 2  # videos keep the input order
    text = "\n".join(rep.lines())
    assert "order: why 0.60, search 0.20, question 0.20 (highest weight first" in text and "5 decided tests)" in text


def test_pack_weights_need_5_decided_tests(tmp_path):
    weights = {"search": 0.0, "question": 0.25, "why": 0.75}
    four = make_pack(TITLES, weights_path=weights_file(tmp_path, weights, 4))
    assert four.order == ["search", "question", "why"] and not four.weights_applied
    assert [r.variant for r in four.rows[:3]] == ["search", "question", "why"]
    assert four.lines()[1] == (
        f"order: search, question, why (default - only 4 decided tests in {tmp_path / 'w.json'}, "
        "the weights count from 5)"
    )
    assert four.to_json()["weights"] == weights and four.to_json()["decided"] == 4  # still reported
    five = make_pack(TITLES, weights_path=weights_file(tmp_path, weights, 5))
    assert five.order == ["why", "question", "search"] and five.weights_applied
    assert five.to_json()["weights_applied"] is True
    assert make_pack(TITLES, weights_path=weights_file(tmp_path, weights, 0)).order == ["search", "question", "why"]


def test_load_weights_rejects_bad_files(tmp_path):
    def weights(text):
        p = tmp_path / "w.json"
        p.write_text(text, encoding="utf-8")
        return p

    assert load_weights(weights('{"decided": 7, "weights": {"why": 1}}')) == (
        {"search": None, "question": None, "why": 1.0},  # missing = not enough info, not 0
        7,
    )
    assert load_weights(weights('{"decided": 7, "weights": {"search": null, "question": 0, "why": 1}}')) == (
        {"search": None, "question": 0.0, "why": 1.0},
        7,
    )
    for text, message in [
        ("{", "can't read weights file"),
        ("[0.5, 0.5]", "must look like"),
        ('{"search": 0.5, "why": 0.5}', "must look like"),  # no decided count
        ('{"decided": 5, "weights": [0.5]}', "must look like"),
        ('{"decided": 5, "weights": {}, "extra": 1}', "must look like"),
        ('{"decided": 4.5, "weights": {}}', "decided must be a whole number >= 0, got 4.5"),
        ('{"decided": -1, "weights": {}}', "decided must be a whole number"),
        ('{"decided": true, "weights": {}}', "decided must be a whole number"),
        ('{"decided": 5, "weights": {"qestion": 0.5}}', "unknown variant qestion - expected search, question, why"),
        ('{"decided": 5, "weights": {"why": "high"}}', "the weight of why must be a number or null, got 'high'"),
        ('{"decided": 5, "weights": {"why": true}}', "the weight of why must be a number"),
        ('{"decided": 5, "weights": {"why": NaN}}', "the weight of why must be a number"),
    ]:
        with pytest.raises(AbError, match=re.escape(message)):
            load_weights(weights(text))
    with pytest.raises(AbError, match="weights file not found"):
        load_weights(tmp_path / "missing.json")
    with pytest.raises(AbError, match="weights file not found"):  # checked before the input CSV is read
        make_pack(TITLES, weights_path=tmp_path / "missing.json")


def test_ab_pack_writes_csv_like_input_and_never_overwrites_inputs(tmp_path):
    src = tmp_path / "in.csv"
    src.write_bytes(b"\xef\xbb\xbfvideo_id;title;keyword\na1;" + GEN_TITLE.encode() + b";Mitose\n")
    before = src.read_bytes()
    out = tmp_path / "pack.csv"
    out.write_text("old content", encoding="utf-8")  # an existing output is replaced
    ab_pack(src, out)
    data = out.read_bytes()
    assert data.startswith(b"\xef\xbb\xbfvideo_id;variant;title;length\n")  # same delimiter + BOM as the input
    assert rows_of(data.decode("utf-8"))[2] == [
        "a1",
        "question",
        "Mitose – kannst du es erklären? #Biologie #Klasse10",
        "51",
    ]
    assert src.read_bytes() == before
    # the input CSV and the weights file are never overwritten - however the path is written
    weights = weights_file(tmp_path, {"why": 1}, 5)
    w_before = weights.read_bytes()
    (tmp_path / "link.csv").symlink_to(src)
    os.link(src, tmp_path / "hard.csv")
    sub = tmp_path / "sub"
    sub.mkdir()
    for target in [src, tmp_path / "sub" / ".." / "in.csv", tmp_path / "link.csv", tmp_path / "hard.csv"]:
        with pytest.raises(AbError, match="is the input CSV - choose another file, an input is never overwritten"):
            ab_pack(src, target, weights_path=weights)
    with pytest.raises(AbError, match="is the weights file"):
        ab_pack(src, weights, weights_path=weights)
    with pytest.raises(AbError, match="is a directory"):
        ab_pack(src, sub)
    with pytest.raises(AbError, match="can't write --out"):
        ab_pack(src, tmp_path / "no_such_dir" / "pack.csv")
    assert src.read_bytes() == before and weights.read_bytes() == w_before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hard.csv", "in.csv", "link.csv", "pack.csv", "sub", "w.json"]


def test_outputs_get_normal_permissions(tmp_path):
    old = os.umask(0o022)
    try:
        ab_pack(TITLES, tmp_path / "pack.csv")
        ab_results(RESULTS, tmp_path / "weights.json")
        # a new file gets normal permissions (0666 minus the umask), not "only your user"
        assert stat.S_IMODE((tmp_path / "pack.csv").stat().st_mode) == 0o644
        assert stat.S_IMODE((tmp_path / "weights.json").stat().st_mode) == 0o644
        os.umask(0o002)
        ab_pack(TITLES, tmp_path / "group.csv")
        assert stat.S_IMODE((tmp_path / "group.csv").stat().st_mode) == 0o664  # the user's umask decides
        # an existing file keeps the mode it has
        (tmp_path / "pack.csv").chmod(0o600)
        ab_pack(TITLES, tmp_path / "pack.csv")
        assert stat.S_IMODE((tmp_path / "pack.csv").stat().st_mode) == 0o600
    finally:
        os.umask(old)


def test_ab_pack_crash_while_writing_keeps_the_old_output(tmp_path, monkeypatch):
    out = tmp_path / "pack.csv"
    out.write_text("old content", encoding="utf-8")

    def crash(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(AbError, match=r"can't write --out .*disk full"):
        ab_pack(TITLES, out)
    assert out.read_text(encoding="utf-8") == "old content" and [p.name for p in tmp_path.iterdir()] == ["pack.csv"]


# ---------------------------------------------------------------- ab-results
def test_parse_share_accepts_fractions_commas_and_percent():
    for raw, want in [
        ("0.42", "0.42"),
        (" 0,42 ", "0.42"),
        ("42%", "0.42"),
        ("42,5 %", "0.425"),
        ("0", "0"),
        ("1", "1"),
        ("100%", "1"),
    ]:
        assert parse_share(raw) == Decimal(want), raw
    for raw, message in [
        ("", "empty watch_time_share"),
        ("%", "empty"),
        ("abc", "is not a number"),
        ("nan", "is not a number"),
        ("inf", "is not a number"),
        ("45", "must be a share from 0 to 1 (0.42) or a percentage (42%)"),  # 45 without % is not 45%
        ("-0.1", "must be a share"),
        ("101%", "must be a share"),
    ]:
        with pytest.raises(ValueError, match=re.escape(message)):
            parse_share(raw)


def test_decide_winner_margin_boundary():
    s = {"search": Decimal("0.45"), "question": Decimal("0.40"), "why": Decimal("0.15")}
    assert 0.45 - 0.40 < 0.05  # with floats this exact boundary would be lost
    assert decide(s) == (WINNER, "search", Decimal("0.05"))
    assert decide({"search": Decimal("0.449"), "question": Decimal("0.40"), "why": Decimal("0.151")})[:2] == (
        INCONCLUSIVE,
        None,
    )
    assert decide({"question": Decimal("0.52"), "why": Decimal("0.48")}) == (INCONCLUSIVE, None, Decimal("0.04"))
    assert decide({"question": Decimal("0.40"), "why": Decimal("0.40"), "search": Decimal("0.20")})[0] == INCONCLUSIVE
    assert decide({"why": Decimal("0.30"), "search": Decimal("0.70")})[:2] == (WINNER, "search")  # any row order


def test_compute_weights_rounding():
    all3 = {"search": 3, "question": 3, "why": 3}
    assert compute_weights({"search": 1, "why": 2}, all3) == {"search": 0.33, "question": 0.0, "why": 0.67}
    eight = {"search": 8, "question": 8, "why": 8}
    assert compute_weights({"search": 1, "question": 7}, eight) == {"search": 0.13, "question": 0.88, "why": 0.0}
    assert compute_weights({}, {"search": 0, "question": 0, "why": 0}) == {
        "search": None,
        "question": None,
        "why": None,
    }
    assert compute_weights({"why": 4}, {"search": 4, "question": 4, "why": 4}) == {
        "search": 0.0,
        "question": 0.0,
        "why": 1.0,
    }


def test_weights_count_only_tests_the_variant_was_in(tmp_path):
    # search is in a1-a3 and wins 2 of them. a4: ab-pack dropped the search title (too long), why wins.
    # search could not win a4, so a4 must not count against it: search 2/3, not 2/4
    path = results_csv(
        tmp_path,
        "a1,search,0.50\na1,question,0.30\na1,why,0.20\n"  # search wins
        "a2,search,0.55\na2,question,0.25\na2,why,0.20\n"  # search wins
        "a3,search,0.20\na3,question,0.30\na3,why,0.50\n"  # why wins
        "a4,question,0.40\na4,why,0.60\n"  # why wins - no search title in this test
        "a5,search,0.35\na5,why,0.33\na5,question,0.32\n",  # inconclusive: counts for nobody
    )
    rep = read_results(path)
    assert rep.decided == 4
    assert rep.wins == {"search": 2, "question": 0, "why": 2}
    assert rep.decided_with == {"search": 3, "question": 4, "why": 4}
    # the old rule (wins / all decided tests) gave search 2/4 = 0.5, a tie with why
    assert rep.weights == {"search": 0.67, "question": 0.0, "why": 0.5}
    assert variant_order(rep.weights) == ["search", "why", "question"]
    text = rep.lines()
    assert "  search    0.67  (2 of 3)" in text and "  why       0.50  (2 of 4)" in text
    assert rep.to_json()["decided_with"] == {"search": 3, "question": 4, "why": 4}
    # the real fixture: v02 (question vs why) and v10 (search vs question) count only for the variants in them
    fixture = read_results(RESULTS)
    assert fixture.decided_with == {"search": 4, "question": 5, "why": 4}
    assert fixture.weights == {"search": 0.25, "question": 0.2, "why": 0.75}


def test_weights_need_3_tests_per_variant(tmp_path):
    # search: 2 wins in 2 tests (1.0) would beat why's 3 wins in 5 (0.6) on almost no evidence - and
    # 0.0 would call it a loser. Below 3 tests it is unknown: None, "not enough info"
    path = results_csv(
        tmp_path,
        "a1,search,0.60\na1,why,0.40\n"  # search wins
        "a2,search,0.70\na2,question,0.30\n"  # search wins
        "a3,question,0.30\na3,why,0.70\n"  # why wins
        "a4,question,0.35\na4,why,0.65\n"  # why wins
        "a5,question,0.20\na5,why,0.80\n"  # why wins
        "a6,question,0.60\na6,why,0.40\n",  # question wins
    )
    rep = read_results(path)
    assert rep.decided_with == {"search": 2, "question": 5, "why": 5}
    assert rep.weights == {"search": None, "question": 0.2, "why": 0.6}  # 2 of 2 is below 3 tests -> unknown
    text = rep.lines()
    assert "  search    not enough info  (2 of 2 - needs 3 tests)" in text
    assert "  why       0.60  (3 of 5)" in text
    assert text[-4].startswith("WEIGHTS (wins / decided tests the variant was in, from 3 tests on;")
    assert rep.to_json()["weights"]["search"] is None
    # boundary: exactly 3 tests count
    rep3 = read_results(
        results_csv(tmp_path, "b1,search,0.6\nb1,why,0.4\nb2,search,0.6\nb2,why,0.4\nb3,why,0.6\nb3,search,0.4\n")
    )
    assert rep3.decided_with == {"search": 3, "question": 0, "why": 3}
    assert rep3.weights == {"search": 0.67, "question": None, "why": 0.33}
    # a variant in no decided test: not enough info, "0 of 0"
    assert "  question  not enough info  (0 of 0 - needs 3 tests)" in rep3.lines()
    # the unit: compute_weights applies the same minimum; 0 wins in 3 tests is a real 0.0
    assert compute_weights({"search": 2}, {"search": 2, "question": 3, "why": 3}) == {
        "search": None,
        "question": 0.0,
        "why": 0.0,
    }


def test_unknown_variant_keeps_its_default_place(tmp_path):
    # search has 2 of 2 wins: not enough info. It must not be ranked last as a loser (0) - it keeps its
    # default place (1st); why 0.6 and question 0.2 are ranked in the other places
    assert variant_order({"search": None, "question": 0.2, "why": 0.6}) == ["search", "why", "question"]
    assert variant_order({"search": 0.0, "question": 0.2, "why": 0.6}) == ["why", "question", "search"]  # a real 0
    assert variant_order({"search": 0.3, "question": None, "why": 0.6}) == ["why", "question", "search"]
    assert variant_order({"search": 0.3, "question": 0.9, "why": None}) == ["question", "search", "why"]
    assert variant_order({"search": None, "question": None, "why": None}) == ["search", "question", "why"]
    # end to end: results -> weights file (null) -> ab-pack
    results = results_csv(
        tmp_path,
        "a1,search,0.60\na1,why,0.40\na2,search,0.70\na2,question,0.30\n"  # search 2 of 2
        "a3,question,0.30\na3,why,0.70\na4,question,0.35\na4,why,0.65\n"
        "a5,question,0.20\na5,why,0.80\na6,question,0.60\na6,why,0.40\n",  # why 3 of 5, question 1 of 5
    )
    weights = tmp_path / "w.json"
    ab_results(results, weights)
    assert json.loads(weights.read_text(encoding="utf-8")) == {
        "decided": 6,
        "weights": {"search": None, "question": 0.2, "why": 0.6},
    }
    pack = ab_pack(TITLES, tmp_path / "pack.csv", weights_path=weights)
    assert pack.order == ["search", "why", "question"]
    assert [r.variant for r in pack.rows[:3]] == ["search", "why", "question"]  # v01
    assert [r.variant for r in pack.rows[3:5]] == ["why", "question"]  # v02: search was dropped (too long)
    assert pack.lines()[1] == (
        "order: search (not enough info), why 0.60, question 0.20 (highest weight first; not enough info keeps "
        f"the default place, from {weights}, 6 decided tests)"
    )
    assert pack.to_json()["weights"] == {"search": None, "question": 0.2, "why": 0.6}


def test_read_results_fixture():
    rep = read_results(RESULTS, weights_file="w.json")
    assert [(t.video_id, t.result, t.winner, t.margin) for t in rep.tests] == [
        ("v02", WINNER, "why", Decimal("0.16")),  # a 2-title test: ab-pack dropped its search title
        ("v04", INCONCLUSIVE, None, Decimal("0.04")),
        ("v05", WINNER, "search", Decimal("0.05")),  # exactly 0.05 is a winner
        ("v06", WINNER, "why", Decimal("0.12")),  # given in percent
        ("v07", INCONCLUSIVE, None, Decimal("0.04")),  # a 2-title test
        ("v08", WINNER, "why", Decimal("0.30")),
        ("v10", WINNER, "question", Decimal("0.24")),  # a 2-title test with a winner
    ]
    assert [(n.video_id, n.line, n.reason) for n in rep.not_evaluated] == [
        ("v09", 14, "only 1 variant (search) - a test compares 2 or 3")
    ]
    assert rep.decided == 5 and rep.wins == {"search": 1, "question": 1, "why": 3}
    assert rep.weights == {"search": 0.25, "question": 0.2, "why": 0.75}  # wins / decided tests with the variant
    assert rep.warnings == []
    text = rep.lines()
    assert text[0] == (
        f"8 videos in {RESULTS}: 5 winners, 2 inconclusive, 1 not evaluated (winner = top share - second share >= 0.05)"
    )
    assert "v05           winner        search    0.450  question  0.400   0.050" in text
    assert "  why       0.75  (3 of 4)" in text and "  search    0.25  (1 of 4)" in text
    assert (
        "WEIGHTS (wins / decided tests the variant was in, from 3 tests on; 5 decided tests, written to w.json)" in text
    )
    assert not any("ab-pack keeps the default order" in line for line in text)  # 5 decided: the weights count
    j = json.loads(json.dumps(rep.to_json()))
    assert set(j) == {
        "file",
        "weights_file",
        "videos",
        "decided",
        "inconclusive",
        "tests",
        "not_evaluated",
        "wins",
        "decided_with",
        "weights",
        "warnings",
    }
    assert j["tests"][2] == {
        "video_id": "v05",
        "result": "winner",
        "winner": "search",
        "margin": 0.05,
        "shares": {"search": 0.45, "question": 0.4, "why": 0.15},
    }


def test_read_results_never_guesses_a_video(tmp_path):
    path = results_csv(
        tmp_path,
        "a1,search,0.30\na1,question,0.25\na1,why,lots\n"  # lines 2-4: the broken row may be the real winner
        "a2,search,0.5\na2,question,0.5,extra\na2,why,0.0\n"  # lines 5-7: wrong number of fields
        "a3,search,0.6\na3,search,0.3\na3,why,0.1\n"  # lines 8-10: a variant twice
        "a4,search,0.6\na4,question,45%\na4,why,0.1\n"  # lines 11-13: adds up to 1.15
        "a5,search,0.5\na5,best,0.4\n"  # lines 14-15: unknown variant
        ",why,0.9\n"  # line 16: no video_id
        "a6,Search,0.60\na6,WHY,0.40\n"  # lines 17-18: variant names are not case-sensitive
        "a7,search,0.34\na7,question,0.33\na7,why,0.33\n",  # lines 19-21: 1.00 - fine
    )
    rep = read_results(path)
    assert [(n.video_id, n.line, n.reason) for n in rep.not_evaluated] == [
        ("a1", 2, "line 4 was skipped - a missing variant could be the real winner"),
        ("a2", 5, "line 6 was skipped - a missing variant could be the real winner"),
        ("a3", 8, "variant search appears twice (lines 8, 9)"),
        ("a4", 11, "watch time shares add up to 1.15 - more than 1 (100%)"),
        ("a5", 14, "line 15 was skipped - a missing variant could be the real winner"),
    ]
    assert [(t.video_id, t.result, t.winner) for t in rep.tests] == [
        ("a6", WINNER, "search"),
        ("a7", INCONCLUSIVE, None),
    ]
    assert [(w.line, w.message) for w in rep.warnings] == [
        (4, "skipped - watch_time_share 'lots' is not a number"),
        (6, "skipped - 4 fields, header has 3"),
        (15, "skipped - unknown variant 'best' (expected search, question, why)"),
        (16, "skipped - empty video_id"),
    ]
    # nearest legitimate case: the ab-pack file with a share column added - title and length are expected
    pack = results_csv(
        tmp_path,
        'a1,search,"Gentechnik einfach erklärt – das musst du wissen! #Biologie",58,0.6,x\na1,why,"Warum?",6,0.4,y\n',
        header="video_id,variant,title,length,watch_time_share,notes",
    )
    rep = read_results(pack)
    assert [(w.line, w.message) for w in rep.warnings] == [(None, "ignored columns: notes")]
    assert rep.tests[0].winner == "search"
    with pytest.raises(AbError, match="missing column"):
        read_results(results_csv(tmp_path, "a1,search\n", header="video_id,variant"))


def test_ab_results_writes_weights_and_never_overwrites_input(tmp_path):
    before = RESULTS.read_bytes()
    weights = tmp_path / "weights.json"
    rep = ab_results(RESULTS, weights)
    assert json.loads(weights.read_text(encoding="utf-8")) == {
        "decided": 5,
        "weights": {"search": 0.25, "question": 0.2, "why": 0.75},
    }
    assert list(json.loads(weights.read_text(encoding="utf-8"))["weights"]) == ["search", "question", "why"]
    assert load_weights(weights) == (rep.weights, 5)  # the weights file is the --weights input of ab-pack
    assert variant_order(load_weights(weights)[0]) == ["why", "search", "question"]
    assert RESULTS.read_bytes() == before
    copy = tmp_path / "results.csv"
    copy.write_bytes(before)
    for target in [copy, tmp_path / "." / "results.csv"]:
        with pytest.raises(AbError, match=r"--weights .* is the input CSV"):
            ab_results(copy, target)
    assert copy.read_bytes() == before
    # no decided test yet: no weight is known and the text says ab-pack keeps the default order
    none = results_csv(tmp_path, "a1,search,0.52\na1,why,0.48\n")
    rep = ab_results(none, tmp_path / "w0.json")
    assert rep.weights == {"search": None, "question": None, "why": None}
    assert "  only 0 decided tests - ab-pack keeps the default order until 5 are decided" in rep.lines()
    assert load_weights(tmp_path / "w0.json") == (rep.weights, 0)
    single = ab_results(results_csv(tmp_path, "a1,search,0.61\n"), tmp_path / "w1.json")
    assert single.lines()[1:3] == ["TESTS", "  (no test could be evaluated)"]
