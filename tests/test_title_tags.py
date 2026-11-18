"""Grade hashtags of generated titles follow the series rule (specs/titles.md, specs/series.md): a grade
range or a school level is never turned into one #KlasseN. Offline."""

import pytest

from aidemy_seo import experiments as ex
from aidemy_seo.cli import main
from aidemy_seo.series import series_key
from aidemy_seo.titles import grade_tag, optimize_title, title_tags


def test_title_tags_single_grade_unchanged():
    # nearest legitimate cases: the grades the channel uses today give the same tags as before
    assert title_tags("Biologie", "Klasse 10") == ["#Biologie", "#Klasse10"]
    assert title_tags("Biologie", "10") == ["#Biologie", "#Klasse10"]
    assert title_tags("Deutsch", "Klasse 6") == ["#Deutsch", "#Klasse6"]
    assert title_tags("Biologie", "Klasse 10a") == ["#Biologie", "#Klasse10"]
    assert title_tags("Biologie", "") == ["#Biologie"] and title_tags("", "Klasse 9") == ["#Klasse9"]
    assert series_key("Mitose " + " ".join(title_tags("Biologie", "Klasse 10"))) == ("Biologie", 10)


@pytest.mark.parametrize(
    ("grade", "tag"),
    [
        ("Klasse 11-12", "#Klasse11-12"),
        ("Klasse 11–12", "#Klasse11-12"),
        ("11/12", "#Klasse11-12"),
        ("Klasse 11 bis 12", "#Klasse11-12"),
        ("Klasse 5 und 6", "#Klasse5-6"),
        ("5./6. Klasse", "#Klasse5-6"),
    ],
)
def test_grade_range_stays_a_range(grade, tag):
    # must catch: the old rule took the first number - "Klasse 11-12" became #Klasse11
    assert grade_tag(grade) == tag
    tags = title_tags("Biologie", grade)
    assert tags == ["#Biologie", tag] and "#Klasse11" not in tags
    assert series_key("Mitose " + " ".join(tags)) == f"grade range {tag} - a series needs one grade (#KlasseN)"


@pytest.mark.parametrize(
    ("grade", "tag"),
    [
        ("Q11", "#Q11"),
        ("Q1", "#Q1"),
        ("Jahrgangsstufe Q12", "#Q12"),
        ("Oberstufe", "#Oberstufe"),
        ("Sek II", "#SekII"),
        ("Sekundarstufe I", "#SekundarstufeI"),
        ("Abitur", "#Abitur"),
        ("EF", "#EF"),
    ],
)
def test_school_level_stays_a_level(grade, tag):
    # must catch: the old rule made "Q11" #Klasse11 and dropped "Oberstufe" (no number)
    assert title_tags("Biologie", grade) == ["#Biologie", tag]
    assert series_key("Mitose " + " ".join(title_tags("Biologie", grade))) == (
        f"{tag} is a school level, not a grade - a series needs #KlasseN (levels are not guessed)"
    )


def test_unknown_grade_text_gets_no_grade_tag():
    # the level list stays as it is: an unknown level without a number gets no grade tag, as before
    assert title_tags("Biologie", "Kursstufe") == ["#Biologie"]
    assert grade_tag("Kursstufe") is None and grade_tag("") is None


def test_generated_titles_keep_range_and_level(capsys, tmp_path):
    # title --generate, experiment assign and lessons all build their tags with title_tags
    top = optimize_title("Mitose", subject="Biologie", grade="Klasse 11-12")[0]
    assert top.title.endswith("#Biologie #Klasse11-12")
    assert all(
        "#Klasse11 " not in s.title and not s.title.endswith("#Klasse11")
        for s in optimize_title("Mitose", subject="Biologie", grade="Klasse 11-12")
    )
    a = ex.assign(
        tmp_path / "l.json",
        experiment="e",
        key="k",
        keyword="Mitose",
        subject="Biologie",
        grade="Q11",
        arms=["question", "warum"],
    )
    assert a.title.endswith("#Biologie #Q11")
    assert main(["title", "Mitose", "--generate", "--subject", "Biologie", "--grade", "Klasse 11-12"]) == 0
    out = capsys.readouterr().out
    assert "#Biologie #Klasse11-12" in out and not any(line.endswith("#Klasse11") for line in out.splitlines())
