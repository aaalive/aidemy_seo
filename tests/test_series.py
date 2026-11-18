"""Shorts series from #Fach + #KlasseN (specs/series.md). Offline; real titles from tests/fixtures/titles_to_fix.csv."""

import json
from pathlib import Path

import pytest

from aidemy_seo.series import SeriesError, find_series, grade_kind, series_key, title_hashtags

FIX = Path(__file__).parent / "fixtures"
TITLES = FIX / "titles_to_fix.csv"


def write(tmp_path, text, name="videos.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_series_key_subject_and_grade():
    assert series_key("Gentechnik: Das musst du wissen! #Biologie #Klasse10") == ("Biologie", 10)
    assert series_key("Warum? #Klasse10 #Biologie") == ("Biologie", 10)  # order of the two tags doesn't matter
    assert series_key("Mitose #Shorts #Biologie #Klasse9") == ("Biologie", 9)  # #Shorts is never the subject
    assert series_key("Mitose #biologie #KLASSE09") == ("biologie", 9)  # case, leading zero
    # real v09: repeated hashtag and a topic tag after the subject -> the first one is the subject
    assert series_key("🔥🔥 Mitose einfach erklärt!!! #Biologie #biologie #Klasse9 #Zellbiologie") == ("Biologie", 9)
    assert series_key("Sinne #Ethik #Klasse6 #Klasse6") == ("Ethik", 6)  # the same grade twice is one grade
    # no series - never guessed
    assert series_key("DIE GROSSE ZELLTEILUNG im Überblick #Biologie") == "no #KlasseN hashtag"
    assert series_key("Zellteilung im Überblick") == "no #KlasseN hashtag"
    assert series_key("Zellteilung #Biologie #Klasse") == "no #KlasseN hashtag"  # no number
    assert series_key("Zellteilung #Biologie #Klasse9 #Klasse10") == "2 grade hashtags (#Klasse9, #Klasse10)"
    assert series_key("Zellteilung #Klasse10 #Shorts") == "no subject hashtag (#Fach)"


def test_find_series_on_real_titles():
    rep = find_series(TITLES)
    assert [(s.name, [v.video_id for v in s.videos]) for s in rep.series] == [
        ("Biologie Klasse 11", ["v02", "v03", "v06"]),
        ("Ethik Klasse 5", ["v04", "v07"]),
    ]
    assert [(n.video.video_id, n.reason) for n in rep.not_sorted] == [
        ("v01", "no #KlasseN hashtag"),
        ("v05", "only video of Chemie Klasse 8"),
        ("v08", "only video of Deutsch Klasse 6"),
        ("v09", "only video of Biologie Klasse 9"),
        ("v10", "no #KlasseN hashtag"),
    ]
    assert rep.videos == 10 and [(w.line, w.message) for w in rep.warnings] == [
        (None, "ignored columns: description, tags, keyword")
    ]


def test_find_series_groups_case_insensitive_sorted_and_min_two(tmp_path):
    path = write(
        tmp_path,
        "title\n"
        "Sinne #Ethik #Klasse10\n"  # line 2
        "Mitose #Biologie #Klasse10\n"  # line 3
        "Natur #Ethik #Klasse5\n"  # line 4
        "Wahrnehmung #ethik #KLASSE10\n"  # line 5: same series as line 2
        "Zelle #Biologie #Klasse10\n"  # line 6
        "Tugend #Ethik #Klasse5\n"  # line 7
        "Ökologie #Ökologie #Klasse7\n",  # line 8: alone
    )
    rep = find_series(path)
    assert [(s.name, s.subject, s.grade, [v.line for v in s.videos]) for s in rep.series] == [
        ("Biologie Klasse 10", "Biologie", 10, [3, 6]),
        ("Ethik Klasse 5", "Ethik", 5, [4, 7]),  # grade 5 before 10: numbers, not text
        ("Ethik Klasse 10", "Ethik", 10, [2, 5]),  # named by the first spelling
    ]
    assert [(n.video.line, n.reason) for n in rep.not_sorted] == [(8, "only video of Ökologie Klasse 7")]
    assert all(v.video_id is None for s in rep.series for v in s.videos)  # video_id is optional


def test_find_series_skips_bad_rows_and_duplicate_ids(tmp_path):
    path = write(
        tmp_path,
        "video_id;title\n"
        "a1;Mitose #Biologie #Klasse9\n"  # line 2
        "a1;Mitose #Biologie #Klasse9\n"  # line 3: the same video again would make a fake series
        "a2;  \n"  # line 4: empty title
        "a3;Zelle #Biologie;#Klasse9\n"  # line 5: 3 fields
        ";Zellteilung #Biologie #Klasse9\n",  # line 6: no video_id is fine
    )
    before = path.read_bytes()
    rep = find_series(path)
    assert [(s.name, [v.line for v in s.videos]) for s in rep.series] == [("Biologie Klasse 9", [2, 6])]
    assert [(w.line, w.message) for w in rep.warnings] == [
        (3, "skipped - video_id a1 is already on line 2 (would count twice)"),
        (4, "skipped - empty title"),
        (5, "skipped - 3 fields, header has 2"),
    ]
    assert path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["videos.csv"]  # writes nothing
    for bad, message in [
        (tmp_path / "missing.csv", "file not found"),
        (write(tmp_path, "video_id;name\na1;x\n", "no_title.csv"), "missing column(s): title"),
        (write(tmp_path, "", "empty.csv"), "is empty"),
    ]:
        with pytest.raises(SeriesError, match=message.replace("(", r"\(").replace(")", r"\)")):
            find_series(bad)


def test_series_report_json_and_text(tmp_path):
    rep = find_series(TITLES)
    j = json.loads(json.dumps(rep.to_json(), ensure_ascii=False))
    assert set(j) == {"file", "videos", "in_series", "series", "not_sorted", "warnings"}
    assert j["in_series"] == 5 and j["series"][1] == {
        "name": "Ethik Klasse 5",
        "subject": "Ethik",
        "grade": 5,
        "count": 2,
        "videos": [
            {"line": 5, "video_id": "v04", "title": "Warum wir nicht alleine leben koennen #Ethik #Klasse5"},
            {"line": 8, "video_id": "v07", "title": "Was ist  Natur ?  Unberührt , belebt , unbelebt #Ethik #Klasse5"},
        ],
    }
    assert j["not_sorted"][0] == {
        "line": 2,
        "video_id": "v01",
        "title": "Die Worttrennung, die in jeder Klassenarbeit vorkommt 📚 #Deutsch",
        "reason": "no #KlasseN hashtag",
    }
    text = rep.lines()
    assert text[0] == f"2 series in {TITLES}: 5 of 10 videos in a series, 5 not sorted, 0 skipped"
    assert text.index("SERIES") < text.index("Biologie Klasse 11 (3 videos)") < text.index("NOT SORTED")
    assert text.index("NOT SORTED") < text.index("WARNINGS")
    assert (
        "  line   6  v05           Feuer und neue Quellen : Das musst du wissen! #Chemie #Klasse8  - only video of Chemie Klasse 8"
        in text
    )
    empty = find_series(write(tmp_path, "title\nZellteilung #Biologie\n"))
    assert empty.lines()[1:4] == [
        "SERIES",
        "  (none - a series needs 2 videos with the same #Fach and #KlasseN)",
        "NOT SORTED",
    ]
    assert empty.lines()[-1] == "  (none)"  # no warnings


# ---------------------------------------------------------------- grade ranges and school levels
def test_grade_ranges_are_not_guessed():
    # must catch: "#Klasse11-12" is cut to "#Klasse11" by a plain hashtag split (YouTube links only that
    # part too) - the video must NOT be filed under Klasse 11
    for tag in ("#Klasse11-12", "#Klasse11–12", "#Klasse11/12", "#Klasse11bis12", "#Klasse11_12"):
        assert series_key(f"Mitose #Biologie {tag}") == f"grade range {tag} - a series needs one grade (#KlasseN)"
    assert title_hashtags("Mitose #Biologie #Klasse11-12 #Shorts") == ["#Biologie", "#Klasse11-12", "#Shorts"]
    # a range next to one #KlasseN: the #KlasseN decides, the range is extra information
    assert series_key("Mitose #Biologie #Klasse11 #Klasse11-12") == ("Biologie", 11)
    # nearest legitimate cases: a dash with spaces is text, not a range; two single grades stay ambiguous
    assert series_key("Mitose #Biologie #Klasse11 - Teil 2") == ("Biologie", 11)
    assert series_key("Mitose #Biologie #Klasse11-Quiz") == ("Biologie", 11)  # not a number after the dash
    assert series_key("Mitose #Biologie #Klasse11 #Klasse12") == "2 grade hashtags (#Klasse11, #Klasse12)"


def test_school_levels_are_not_grades_and_not_subjects():
    # a level means different grades per Bundesland (Q11 in Bayern, Q1 in NRW = 11 or 12) - never mapped
    for tag in ("#Q11", "#Q1", "#Q12", "#Oberstufe", "#Mittelstufe", "#SekII", "#Sek1", "#Abitur", "#EF"):
        assert series_key(f"Mitose #Biologie {tag}") == (
            f"{tag} is a school level, not a grade - a series needs #KlasseN (levels are not guessed)"
        )
        assert grade_kind(tag) == "level"
    # must catch: a level first used to become the subject ("Oberstufe Klasse 11", "Q11 Klasse 11")
    assert series_key("Mitose #Oberstufe #Biologie #Klasse11") == ("Biologie", 11)
    assert series_key("Mitose #Q11 #Biologie #Klasse11") == ("Biologie", 11)
    assert series_key("Abi-Wissen #Abitur #Biologie #Klasse12") == ("Biologie", 12)
    assert series_key("Mitose #Oberstufe #Klasse11") == "no subject hashtag (#Fach)"
    # nearest legitimate cases: a subject or topic that merely starts like a level is still a subject
    assert series_key("Gleichungen #Quadratik #Klasse9") == ("Quadratik", 9)
    assert series_key("Warum? #Sekundenschlaf #Klasse9") == ("Sekundenschlaf", 9)
    assert [grade_kind(t) for t in ("#Klasse10", "#Klasse11-12", "#Q11", "#Biologie")] == [
        "grade",
        "range",
        "level",
        None,
    ]
    assert grade_kind("#Q") is None and grade_kind("#Q123") is None  # a level is Q + 1-2 digits


def test_find_series_with_ranges_and_levels(tmp_path):
    path = write(
        tmp_path,
        "video_id;title\n"
        "a1;Mitose #Biologie #Klasse11-12\n"  # line 2: range
        "a2;Meiose #Biologie #Klasse11-12\n"  # line 3: range - two of them are still no series
        "a3;Zellzyklus #Biologie #Klasse11\n"  # line 4: the only real Klasse 11 video
        "a4;Redox #Oberstufe #Chemie #Klasse12\n"  # line 5: level first, then the subject
        "a5;Säuren #Q12 #Chemie #Klasse12\n"  # line 6
        "a6;Optik #Physik #Q11\n"  # line 7: level only
        "a7;Wellen #Physik #Q11\n",  # line 8
    )
    rep = find_series(path)
    assert [(s.name, [v.video_id for v in s.videos]) for s in rep.series] == [("Chemie Klasse 12", ["a4", "a5"])]
    assert [(n.video.video_id, n.reason) for n in rep.not_sorted] == [
        ("a1", "grade range #Klasse11-12 - a series needs one grade (#KlasseN)"),
        ("a2", "grade range #Klasse11-12 - a series needs one grade (#KlasseN)"),
        ("a3", "only video of Biologie Klasse 11"),  # the ranges were NOT merged into Klasse 11
        ("a6", "#Q11 is a school level, not a grade - a series needs #KlasseN (levels are not guessed)"),
        ("a7", "#Q11 is a school level, not a grade - a series needs #KlasseN (levels are not guessed)"),
    ]
