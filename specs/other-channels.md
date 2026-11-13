# Other channels and top videos

## Requirements
- MUST compare channels by views / that channel's median (ADR 0003); Shorts <= 180 s,
  age 7-180 days; channels with < 5 usable Shorts skipped.
- MUST work offline from a saved file (--save / --load).
- MUST state the API cost: ~5 units per channel, +100 for --discover, ~101 per benchmark.
- MUST NOT run without an API key (clear error).

## Scenarios
- Given a big and a small channel with the same relative hit, then both hits score 3.0.
  Test: tests/test_competitors.py::test_ratio_makes_big_and_small_channels_comparable
- Given too-new, too-old, long videos and a tiny channel, then they are excluded.
  Test: tests/test_competitors.py::test_filters_age_long_videos_and_tiny_channels
- Given question titles doing 3x across 3 channels at 17:00 UTC, then question "helps" and
  18:00 Berlin is the best hour. Test: tests/test_competitors.py::test_question_titles_win_across_channels_and_best_hour_found
- Test: tests/test_competitors.py::test_channel_lookup_params
- Given 60 uploads over two pages, then all 60 are fetched.
  Test: tests/test_competitors.py::test_channel_videos_pages_through_uploads
- Test: tests/test_competitors.py::test_cli_channels_offline_from_saved_file
- Given no key, then top_videos raises a clear error; given a response, then fields parse.
  Test: tests/test_aidemy_seo.py::test_youtube_api_needs_key_and_parses
- Test: tests/test_aidemy_seo.py::test_title_patterns
