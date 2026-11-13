# Specs

One file per feature: requirements (MUST / MUST NOT) and Given/When/Then scenarios.
Every scenario names the test that proves it (`Test: tests/<file>.py::<test>`).
`tests/test_specs.py` fails if a named test does not exist - specs and tests can't drift apart.

Change behaviour => update the spec first (see `.claude/skills/spec-first-feature`).
