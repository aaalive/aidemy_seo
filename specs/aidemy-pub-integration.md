# aidemy_pub integration

## Requirements
- suggest_for_lesson(bundle) MUST return keyword, ranked keywords and ranked titles.
- MUST work without network (falls back to the lesson's main topic word).
- CLI output MUST be available as JSON (--json) for the pipeline.

## Scenarios
- Given the real Biologie Kl. 10 bundle and demand Gentechnik 10, then keyword = Gentechnik
  and the first title leads with it. Test: tests/test_aidemy_seo.py::test_suggest_for_real_lesson_bundle
- Test: tests/test_aidemy_seo.py::test_cli_title_and_calibrate
