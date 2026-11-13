# Description audit

## Requirements
- MUST check: searched keywords in the first 200 characters, a link in the first 4 lines,
  a direct product link (not only an author page), 3-5 hashtags, length, call to action.

## Scenarios
- Given the real Ethik description with only the author-page link and no hashtags, then
  specific_link and hashtags are reported and keywords_first_200 is not.
  Test: tests/test_aidemy_seo.py::test_description_real_text_finds_author_page_link
- Given a complete description, then the score is >= 90.
  Test: tests/test_aidemy_seo.py::test_description_good_one_scores_high
