# Posting times and learning from your own channel

## Requirements
- Slots MUST be weekday + hour in the given timezone, ranked by median, Shorts only by default.
- A slot with fewer than min_videos MUST be marked "not enough data" and ranked below.
- feature_lift MUST NOT claim helps/hurts with fewer than min_group videos on either side.

## Scenarios
- Given 3 Tuesday 15:00 Shorts and a long video, then Tue 15:00 ranks first with enough data
  and the long video is ignored. Test: tests/test_aidemy_seo.py::test_best_slots_ranks_by_median_and_flags_thin_data
- Test: tests/test_aidemy_seo.py::test_best_hours
- Given 5 videos, then every feature says "not enough data".
  Test: tests/test_aidemy_seo.py::test_feature_lift_says_not_enough_data_on_young_channel
- Given 6 question titles at 200 views and 6 others at 50, then question "helps" with lift 4.0.
  Test: tests/test_aidemy_seo.py::test_feature_lift_finds_real_effect_with_enough_data
