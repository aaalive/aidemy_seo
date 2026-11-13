# Keyword research

## Requirements
- MUST rank only words that belong to the lesson (all stems appear in topic or short name).
- MUST turn "A und B C" with a shared head noun into "A C", "B C" and "C"; MUST NOT offer bare "A".
- MUST NOT offer generic single words (Nutzen, Risiken, Grundlagen, ...).
- MUST report an unknown demand as -1, never 0. MUST NOT raise on network failure.
- Cost: 0 API units (autocomplete endpoint).

## Scenarios
- Given the real Biologie Kl. 10 bundle, when candidates are built, then Gentechnik / Grüne
  Gentechnik / Rote Gentechnik are offered and Grüne / Nutzen / Bt-Mais are not.
  Test: tests/test_aidemy_seo.py::test_candidates_real_lesson_gentechnik
- Given autocomplete returns 7 matching completions, then demand is 7; given the network
  fails, then demand is -1.
  Test: tests/test_aidemy_seo.py::test_demand_counts_only_prefix_matches_and_unknown_is_minus_one
- Given demands Gentechnik 10, Grüne Gentechnik 6, then the best title keyword is Gentechnik
  (same stem is never paired).
  Test: tests/test_aidemy_seo.py::test_rank_and_best_keyword_pairs_searched_terms
- Given no lookup succeeds, then the best keyword is "" (caller keeps its default).
  Test: tests/test_aidemy_seo.py::test_best_keyword_offline_is_empty
- Given autocomplete drifts to unrelated topics, then related() drops them.
  Test: tests/test_aidemy_seo.py::test_related_filters_drift
