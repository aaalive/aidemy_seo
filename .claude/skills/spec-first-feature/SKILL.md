---
name: spec-first-feature
description: Use when adding a feature or changing behaviour in aidemy_seo - spec first, then tests from real examples, then code, then the verification loop until green.
---

# Spec-first feature in aidemy_seo

1. **Start from the need.** Restate the user need / ticket in one sentence. Name the real
   example that motivated it (a title, a lesson, an API response, a score).
2. **Read only what you need:** `CLAUDE.md`, the relevant `specs/*.md`, the one module you
   will change and its tests. Check conventions there before writing anything new.
3. **Write or update the spec** in `specs/<feature>.md`:
   - Requirements (MUST / MUST NOT), inputs, outputs, cost (API units), failure behaviour.
   - Scenarios as Given / When / Then, each with `Test:` naming the test that will prove it.
   - Edge cases: offline, empty data, not enough data, unknown values.
   If you choose between real alternatives, add an ADR in `docs/adr/`.
4. **Write the tests first** from the scenarios: one must-catch from the real example,
   one must-not-flag for the nearest legitimate case. Run them - they must FAIL for the
   right reason.
5. **Implement** the smallest change that makes them pass. No network in unit tests.
6. **Verify loop:** run `scripts/verify.sh`. On failure, read the first error, fix, rerun.
   Repeat until green. Never weaken a test to get green.
7. **Report:** what changed, which spec scenarios are covered by which tests, the
   verify.sh summary line, and anything that needs human line-by-line review (keys,
   quota/cost, user data).
