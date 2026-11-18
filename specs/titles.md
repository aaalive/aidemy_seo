# Title scoring and generation

## Requirements
- Score MUST be explainable: every failed check returns a human-readable issue.
- Generated titles MUST be <= 66 characters, MUST lead with the keyword, MUST NOT claim facts.
- Titles that keep both #Fach and #KlasseN MUST rank above ones that drop a hashtag.
- MUST NOT put a second ':' into a topic that already has one.
- Calibration MUST report n per shape (one example is not evidence).
- The grade hashtag (`title_tags` / `grade_tag`, used by `title --generate`, `lesson` and
  `experiment assign`) follows the series rule (specs/series.md, 2026-11-18). A range or a
  school level is NEVER turned into one `#KlasseN`.
  - A single grade is `#KlasseN` as before: "Klasse 10" / "10" / "Klasse 10a" give `#Klasse10`.
  - A range ("Klasse 11-12", "11–12", "11/12", "11 bis 12", "5 und 6", "5./6. Klasse") is one tag,
    `#Klasse11-12`. The old rule took the first number and wrote `#Klasse11`.
  - A school level ("Q11", "Jahrgangsstufe Q12", "Oberstufe", "Sek II", "Sekundarstufe I",
    "Abitur", "EF") is written as the level, `#Q11` / `#Q12` / `#Oberstufe` / `#SekII` / ...,
    with the same level list as `series` (`series.LEVEL_RE`). The old rule gave `#Klasse11` for
    "Q11" and nothing for "Oberstufe".
  - Other text without a number and without a known level ("Kursstufe") gives no grade tag, as
    before.
  - So `series` reads what the generator writes: a range or a level is not sorted, with its
    reason, never filed under one grade. YouTube links only `#Klasse11` in `#Klasse11-12`. The
    tag is still written as the range, because the title must not claim one grade.

## Scenarios
- Given the shop-label title "Bio Kl. 10: Transgene Organismen Arbeitsblatt", then
  not_a_listing and keyword_first are reported. Test: tests/test_aidemy_seo.py::test_score_title_flags_listing_label
- Given keyword Gentechnik, Biologie, Klasse 10, then the top title leads with Gentechnik and
  ends "#Biologie #Klasse10". Test: tests/test_aidemy_seo.py::test_optimize_title_real_lesson_keeps_both_hashtags_and_leads_with_keyword
- Given "Indien bis Kongo: Dekolonisierung", then no title has two colons.
  Test: tests/test_aidemy_seo.py::test_optimize_title_never_doubles_colon
- Given the real vidIQ scores of 2026-11-12, then question = 79.0 and must_know n = 4.
  Test: tests/test_aidemy_seo.py::test_calibrate_on_real_vidiq_scores
- Given "Klasse 10", "10", "Klasse 6", "Klasse 10a", an empty grade or no subject, then the tags are
  the same as before, and `series` reads Biologie 10.
  Test: tests/test_title_tags.py::test_title_tags_single_grade_unchanged
- **Must catch:** "Klasse 11-12", "Klasse 11–12", "11/12", "Klasse 11 bis 12", "Klasse 5 und 6" and
  "5./6. Klasse" give `#Klasse11-12` / `#Klasse5-6`, never `#Klasse11`, and `series` reports the
  range. Test: tests/test_title_tags.py::test_grade_range_stays_a_range
- **Must catch:** "Q11", "Q1", "Jahrgangsstufe Q12", "Oberstufe", "Sek II", "Sekundarstufe I",
  "Abitur" and "EF" give the level tag, and `series` reports the level.
  Test: tests/test_title_tags.py::test_school_level_stays_a_level
- Given "Kursstufe" (not in the level list, which stays as it is) or an empty grade, then no grade
  tag. Test: tests/test_title_tags.py::test_unknown_grade_text_gets_no_grade_tag
- Given "Klasse 11-12", then `optimize_title`'s top title ends `#Biologie #Klasse11-12` and no
  candidate ends in `#Klasse11`. `experiment assign --grade Q11` ends in `#Biologie #Q11`, and so does
  `aidemy-seo title Mitose --generate --grade "Klasse 11-12"`.
  Test: tests/test_title_tags.py::test_generated_titles_keep_range_and_level
