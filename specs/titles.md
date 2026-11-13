# Title scoring and generation

## Requirements
- Score MUST be explainable: every failed check returns a human-readable issue.
- Generated titles MUST be <= 66 characters, MUST lead with the keyword, MUST NOT claim facts.
- Titles that keep both #Fach and #KlasseN MUST rank above ones that drop a hashtag.
- MUST NOT put a second ':' into a topic that already has one.
- Calibration MUST report n per shape (one example is not evidence).

## Scenarios
- Given the shop-label title "Bio Kl. 10: Transgene Organismen Arbeitsblatt", then
  not_a_listing and keyword_first are reported. Test: tests/test_aidemy_seo.py::test_score_title_flags_listing_label
- Given keyword Gentechnik, Biologie, Klasse 10, then the top title leads with Gentechnik and
  ends "#Biologie #Klasse10". Test: tests/test_aidemy_seo.py::test_optimize_title_real_lesson_keeps_both_hashtags_and_leads_with_keyword
- Given "Indien bis Kongo: Dekolonisierung", then no title has two colons.
  Test: tests/test_aidemy_seo.py::test_optimize_title_never_doubles_colon
- Given the real vidIQ scores of 2026-11-12, then question = 79.0 and must_know n = 4.
  Test: tests/test_aidemy_seo.py::test_calibrate_on_real_vidiq_scores
