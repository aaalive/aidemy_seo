"""Batch CSV video SEO analysis (specs/batch-analysis.md): read a CSV, score every row,
find duplicate titles, rank. Offline; real titles from the Gentechnik lesson and the vidIQ fixture."""

import csv
import errno
import json
import os
from pathlib import Path

import pytest

from aidemy_seo.batch import BatchError, analyze_batch, duplicate_title_pairs, read_batch, score_row

REAL_TITLE = "Transgene Organismen: Das musst du wissen! #Biologie #Klasse10"  # 62 characters
GENERATED_69 = "Gentechnik einfach erklärt – das musst du wissen! #Biologie #Klasse10"  # 69 characters
GEN_TITLE = "Gentechnik: Das musst du wissen! #Biologie #Klasse10"
REAL_DESC = (
    "Grüne und Rote Gentechnik: Was transgene Organismen sind, wo sie genutzt werden und welche "
    "Risiken es gibt. Arbeitsblatt: https://aidemy.de/material/gentechnik #Biologie #Klasse10"
)
SUBSCRIBE_DESC = "Abonniere den Kanal für mehr Biologie. #Biologie #Klasse10"
REAL_TAGS = "Gentechnik|Grüne Gentechnik|Rote Gentechnik|gentechnik|transgene Organismen|Biologie Klasse 10|GENTECHNIK"
FIVE_TAGS = "Gentechnik|Grüne Gentechnik|Rote Gentechnik|transgene Organismen|Biologie Klasse 10"


def write_csv(path, rows, *, delimiter=";", bom=False):
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        csv.writer(f, delimiter=delimiter).writerows(rows)
    return path


def by_line(report):
    return {r["line"]: r for r in report.to_json()["ranked"]}


# ---------------------------------------------------------------- score
def test_score_row_real_lesson_full_marks():
    s = score_row(REAL_TITLE, REAL_DESC, REAL_TAGS)
    assert s.points == {"title_length": 30, "shared_words": 30.0, "tags": 40}
    assert s.score == 100.0 and s.issues == []
    assert s.tags == ["Gentechnik", "Grüne Gentechnik", "Rote Gentechnik", "transgene Organismen", "Biologie Klasse 10"]
    assert sum(len(t) for t in s.tags) == 79
    assert s.repeated_tags == ["gentechnik", "GENTECHNIK"]  # a warning, not an issue - costs no points


def test_title_length_points_and_boundaries():
    def length_points(n):
        return score_row("x" * n, "", "").points["title_length"]

    assert [length_points(n) for n in (39, 40, 65, 66)] == [29, 30, 30, 29]
    s = score_row(GENERATED_69, "", "")
    assert s.points["title_length"] == 26
    assert "title: 69 characters (aim 40-65)" in s.issues
    assert length_points(5) == 0 and length_points(100) == 0  # never negative
    assert score_row("  " + "x" * 40 + "  ", "", "").points["title_length"] == 30  # trimmed
    assert not any(i.startswith("title:") for i in score_row(REAL_TITLE, "", "").issues)


def test_shared_words_must_catch_missing_keyword():
    s = score_row(GEN_TITLE, SUBSCRIBE_DESC, FIVE_TAGS)
    assert s.points["shared_words"] == 0.0  # #Biologie, "musst", "wissen" are not topic words
    assert 'shared words: description misses "Gentechnik" (0 of 1 title words)' in s.issues
    assert s.score == 70.0


def test_shared_words_ignores_template_words_and_counts_fraction():
    s = score_row(
        "Sagen und Mythen – kannst du es erklären? #Deutsch #Klasse6", "Was unterscheidet Sagen von Märchen?", ""
    )
    assert s.points["shared_words"] == 15.0
    assert 'shared words: description misses "Mythen" (1 of 2 title words)' in s.issues
    s = score_row("Warum? Einfach erklärt #Biologie", REAL_DESC, "")
    assert s.points["shared_words"] == 0.0 and "shared words: title has no topic words" in s.issues
    s = score_row(REAL_TITLE, "  ", "")
    assert s.points["shared_words"] == 0.0 and "shared words: description is empty" in s.issues
    # nearest legitimate case: the template around a matching keyword costs nothing
    s = score_row(GENERATED_69, "Gentechnik: alles über transgene Organismen", "")
    assert s.points["shared_words"] == 30.0 and not any(i.startswith("shared words") for i in s.issues)


def test_shared_words_ignores_verbs_and_lowercase_words():
    # her real live titles (2026-11-15): verbs were reported as "missing" topic words
    marx = "Treibt Ökonomie die Geschichte? Karl Marx erklärt #Geschichte"
    s = score_row(marx, "Ökonomie und Geschichte: was Karl Marx über die Arbeiterbewegung schrieb.", "")
    assert s.points["shared_words"] == 30.0 and not any(i.startswith("shared words") for i in s.issues)
    krieg = "Wie gelang die Humanisierung der Kriegsführung? #Geschichte"
    s = score_row(krieg, "Die Humanisierung der Kriegsführung im 19. und 20. Jahrhundert.", "")
    assert s.points["shared_words"] == 30.0
    lebenslauf = "Ist der ausführliche Lebenslauf eine Liste? #Deutsch #Klasse9"
    s = score_row(lebenslauf, "So schreibst du einen ausführlichen Lebenslauf.", "")
    assert 'description misses "Liste" (1 of 2 title words)' in " ".join(s.issues)  # a noun still counts


def test_shared_words_still_catches_a_missing_topic_noun():
    # must-catch, her real lowest-scoring Short: the description never names the topic
    s = score_row(
        "Artenvielfalt einfach erklärt – endlich klar! #Biologie #Klasse11",
        "Abonniere den Kanal für mehr Biologie. #Biologie #Klasse11",
        "",
    )
    assert 'shared words: description misses "Artenvielfalt" (0 of 1 title words)' in s.issues
    # a capitalised noun at the start is kept (not a verb)
    s = score_row("Sagen und Mythen – kannst du es erklären?", "Sagen und Märchen", "")
    assert 'description misses "Mythen" (1 of 2 title words)' in " ".join(s.issues)
    # a title with no capitalised word keeps every word (English or all lowercase)
    s = score_row("how photosynthesis works in plants", "Plants make sugar from light.", "")
    assert "photosynthesis" in " ".join(s.issues) and s.points["shared_words"] > 0


def test_tags_count_and_length_boundaries():
    def tags(n):
        return "|".join(f"Tag{i}" for i in range(n))

    count = [score_row(REAL_TITLE, REAL_DESC, tags(n)).points["tags"] for n in (4, 5, 15, 16)]
    assert count == [20, 40, 40, 20]  # 0 or 20 for the count, + 20 for a short total
    assert "tags: 4 unique tags (aim 5-15)" in score_row(REAL_TITLE, REAL_DESC, tags(4)).issues
    letters = ["a" * 99, "b" * 99, "c" * 99, "d" * 99]
    s499 = score_row(REAL_TITLE, REAL_DESC, "|".join([*letters, "e" * 103]))
    s500 = score_row(REAL_TITLE, REAL_DESC, "|".join([*letters, "e" * 104]))
    assert s499.points["tags"] == 40 and s500.points["tags"] == 20
    assert "tags: 500 characters in total (must be < 500)" in s500.issues
    assert score_row(REAL_TITLE, REAL_DESC, "a||b| ").tags == ["a", "b"]
    empty = score_row(REAL_TITLE, REAL_DESC, "")
    assert empty.points["tags"] == 0 and "tags: none" in empty.issues
    assert [i for i in empty.issues if i.startswith("tags")] == ["tags: none"]


# ---------------------------------------------------------------- reading the CSV
def test_read_batch_skips_bad_rows_and_ignores_unknown_columns(tmp_path):
    path = tmp_path / "videos.csv"
    path.write_text(
        "video_id;Title;description;TAGS;views;\n"  # line 1, trailing ';' = an unnamed column
        f"v1;{REAL_TITLE};Was transgene Organismen sind.;{FIVE_TAGS};120;\n"  # line 2
        "v2;Kaputt\n"  # line 3: 2 fields
        "v3;   ;desc;a|b|c|d|e;5;\n"  # line 4: empty title
        f'v4;{GEN_TITLE};"Zeile eins über Gentechnik;\nZeile zwei\nZeile drei";a|b|c|d|e;7;\n'  # lines 5-7
        "v5;Proteine: Das musst du wissen! #Chemie #Klasse12;Proteine erklärt;a|b|c|d|e;9;\n"  # line 8
        ";;;;;\n",  # line 9: blank row as Excel writes it
        encoding="utf-8",
    )
    rows, warnings = read_batch(path)
    assert [(r.line, r.video_id) for r in rows] == [(2, "v1"), (5, "v4"), (8, "v5")]
    assert rows[1].description == "Zeile eins über Gentechnik;\nZeile zwei\nZeile drei"
    msgs = [(w.line, w.message) for w in warnings]
    assert (None, "ignored columns: views, (unnamed column 6)") in msgs
    assert (3, "skipped - 2 fields, header has 6") in msgs
    assert (4, "skipped - empty title") in msgs
    assert not any(line == 9 for line, _ in msgs)  # blank lines: no warning
    report = analyze_batch(path)
    j = report.to_json()
    assert (j["rows"], j["analyzed"], j["skipped"]) == (5, 3, 2)
    assert by_line(report)[2]["score"] == score_row(REAL_TITLE, "Was transgene Organismen sind.", FIVE_TAGS).score


def test_read_batch_keeps_rows_with_empty_description_or_tags(tmp_path):
    path = write_csv(
        tmp_path / "v.csv",
        [["title", "description", "tags"], [REAL_TITLE, "", FIVE_TAGS], [GEN_TITLE, SUBSCRIBE_DESC, ""]],
    )
    rows, warnings = read_batch(path)
    assert [r.line for r in rows] == [2, 3] and warnings == []
    ranked = by_line(analyze_batch(path))
    assert "shared words: description is empty" in ranked[2]["issues"]
    assert "tags: none" in ranked[3]["issues"]


def test_read_batch_detects_delimiter_bom_and_header_case(tmp_path):
    data = [[REAL_TITLE, REAL_DESC, REAL_TAGS], [GEN_TITLE, "Gentechnik, kurz; erklärt", "a|b|c"]]
    semi = write_csv(tmp_path / "semi.csv", [["title", "description", "tags"], *data])
    comma = write_csv(tmp_path / "comma.csv", [["Title", "Description", "Tags"], *data], delimiter=",", bom=True)
    tab = write_csv(tmp_path / "tab.tsv", [[" TITLE ", "description", "TAGS"], *data], delimiter="\t")
    assert comma.read_bytes().startswith(b"\xef\xbb\xbf")
    expected = analyze_batch(semi).to_json()
    assert [r["score"] for r in expected["ranked"]] == [100.0, 80.0]
    assert expected["warnings"] == [{"line": 2, "message": "repeated tags ignored: gentechnik, GENTECHNIK"}]
    for path in (comma, tab):
        j = analyze_batch(path).to_json()
        assert (j["ranked"], j["warnings"]) == (expected["ranked"], expected["warnings"])
    leading = tmp_path / "leading.csv"  # empty lines before the header are skipped, line numbers stay real
    leading.write_text(f"\n\ntitle;description;tags\n{REAL_TITLE};{REAL_DESC};{FIVE_TAGS}\n", encoding="utf-8")
    assert [r.line for r in read_batch(leading)[0]] == [4]


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda d: d / "missing.csv", "not found"),
        (lambda d: d, "is a directory"),
        (lambda d: _write_bytes(d / "latin1.csv", "title;description;tags\nGrüne;x;y\n".encode("latin-1")), "UTF-8"),
        (lambda d: _write_bytes(d / "empty.csv", b"\n\n"), "empty"),
        (lambda d: _write_bytes(d / "notags.csv", b"title;description\nA;B\n"), "missing column(s): tags"),
        (lambda d: _write_bytes(d / "twice.csv", b"title;title;description;tags\nA;B;C;D\n"), "'title' appears twice"),
        (  # csv.Error names the line: a field over the csv module's size limit
            lambda d: _write_bytes(d / "huge.csv", b"title;description;tags\nA;B;C\nA;" + b"x" * 200_000 + b";C\n"),
            "CSV error on line 3",
        ),
    ],
)
def test_read_batch_rejects_bad_files(tmp_path, make, message):
    with pytest.raises(BatchError) as exc:
        read_batch(make(tmp_path))
    assert message in str(exc.value)


def test_read_batch_unreadable_file_is_an_error(tmp_path, monkeypatch):
    locked = write_csv(tmp_path / "locked.csv", [["title", "description", "tags"], [REAL_TITLE, REAL_DESC, FIVE_TAGS]])
    locked.chmod(0)
    try:
        if os.access(locked, os.R_OK):  # root reads anything - simulate the same OS error instead
            monkeypatch.setattr(Path, "read_bytes", _raise(PermissionError(errno.EACCES, "Permission denied")))
        with pytest.raises(BatchError) as exc:
            read_batch(locked)
        assert str(exc.value) == f"can't read {locked}: Permission denied"
        monkeypatch.setattr(Path, "read_bytes", _raise(OSError("device not ready")))  # no strerror -> the error text
        with pytest.raises(BatchError, match=r"can't read .*: device not ready$"):
            read_batch(locked)
    finally:
        locked.chmod(0o600)  # so pytest can clean up tmp_path


def _raise(error):
    def read_bytes(self):
        raise error

    return read_bytes


def _write_bytes(path, data):
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- duplicates
def test_duplicate_title_pairs_exact_after_normalising(tmp_path):
    path = write_csv(
        tmp_path / "d.csv",
        [
            ["title", "description", "tags"],
            [GEN_TITLE, "", ""],  # 2
            ["Proteine: Das musst du wissen! #Chemie #Klasse12", "", ""],  # 3 same template, other keyword
            ["Gentechnik: Das musst du wissen! #Biologie #Klasse9", "", ""],  # 4 other grade
            [GEN_TITLE, "", ""],  # 5
            [GEN_TITLE, "", "", "extra"],  # 6 skipped (4 fields)
            ["gentechnik:  das musst du WISSEN! #Biologie #Klasse10", "", ""],  # 7
        ],
    )
    rows, _ = read_batch(path)
    pairs = duplicate_title_pairs(rows)
    assert [(p.line_a, p.line_b) for p in pairs] == [(2, 5), (2, 7), (5, 7)]
    assert all(p.title == GEN_TITLE for p in pairs)
    assert duplicate_title_pairs([r for r in rows if r.line in (3, 4)]) == []


# ---------------------------------------------------------------- ranking and output
def _ranking_file(tmp_path):
    return write_csv(
        tmp_path / "rank.csv",
        [
            ["title", "description", "tags"],
            [REAL_TITLE, REAL_DESC, FIVE_TAGS],  # 2: 100.0
            [GEN_TITLE, SUBSCRIBE_DESC, FIVE_TAGS],  # 3: 70.0
            [GENERATED_69, "", ""],  # 4: 26.0, same title as line 7
            ["", "no title", ""],  # 5: skipped
            ["Proteine: Das musst du wissen! #Chemie #Klasse12", SUBSCRIBE_DESC, FIVE_TAGS],  # 6: 70.0
            [GENERATED_69, "Gentechnik: alles über transgene Organismen", FIVE_TAGS],  # 7: 96.0
        ],
    )


def test_rank_order_ties_and_min_score_hides_but_keeps_duplicates(tmp_path):
    path = _ranking_file(tmp_path)
    j = analyze_batch(path).to_json()
    assert [(r["rank"], r["line"], r["score"]) for r in j["ranked"]] == [
        (1, 2, 100.0),
        (2, 7, 96.0),
        (3, 3, 70.0),
        (4, 6, 70.0),
        (5, 4, 26.0),
    ]
    rep = analyze_batch(path, min_score=50)
    j = rep.to_json()
    assert [r["rank"] for r in j["ranked"]] == [1, 2, 3, 4]
    assert (j["shown"], j["hidden"], j["min_score"]) == (4, 1, 50.0)
    assert j["duplicates"] == [{"lines": [4, 7], "title": GENERATED_69}]
    assert {"line": 5, "message": "skipped - empty title"} in j["warnings"]
    text = rep.lines()
    assert text[0] == (
        f"analyzed 5 of 6 rows in {path} (1 skipped); 1 duplicate title pair; showing 4 with score >= 50 (1 hidden)"
    )
    assert "   1  100.0      30   30.0    40     2  " + REAL_TITLE in text
    assert '        - shared words: description misses "Gentechnik" (0 of 1 title words)' in text
    assert "  lines 4 and 7: " + GENERATED_69 in text
    assert not any(line.endswith("     4  " + GENERATED_69) for line in text)  # hidden row not in RANKING
    assert analyze_batch(path, min_score=0).to_json()["hidden"] == 0
    for bad in (-1, 101, float("nan"), float("inf")):
        with pytest.raises(BatchError):
            analyze_batch(path, min_score=bad)


def test_report_json_shape_and_empty_file(tmp_path):
    path = write_csv(
        tmp_path / "j.csv",
        [
            ["title", "description", "tags", "video_id"],
            ["Sinnestäuschung: Das musst du wissen! #Ethik #Klasse6", "Sinnestäuschungen", "a|b|a", " "],
        ],
    )
    j = analyze_batch(path).to_json()
    assert list(j) == [
        "file",
        "min_score",
        "rows",
        "analyzed",
        "skipped",
        "shown",
        "hidden",
        "ranked",
        "warnings",
        "duplicates",
    ]
    assert list(j["ranked"][0]) == ["rank", "line", "video_id", "title", "score", "points", "issues"]
    assert j["ranked"][0]["video_id"] is None
    assert j["warnings"] == [{"line": 2, "message": "repeated tags ignored: a"}]
    dumped = json.dumps(j, ensure_ascii=False)
    assert "ä" in dumped and json.loads(dumped) == j
    empty = analyze_batch(write_csv(tmp_path / "e.csv", [["title", "description", "tags"]]))
    assert empty.to_json()["ranked"] == [] and empty.to_json()["analyzed"] == 0
    all_hidden = analyze_batch(path, min_score=100).lines()
    assert all_hidden[all_hidden.index("RANKING") + 2] == "  (no row with score >= 100)"
    lines = empty.lines()
    assert lines[lines.index("RANKING") + 1] == "  (no valid rows)"
    assert lines[lines.index("WARNINGS") + 1] == "  (none)" and lines[-1] == "  (none)"
