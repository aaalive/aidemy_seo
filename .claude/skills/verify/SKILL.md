---
name: verify
description: Use before saying a change is done in aidemy_seo, or when the verify hook reports a failure - runs the local CI and drives the fix loop.
---

# Verify (local CI)

1. Run `scripts/verify.sh` (full) - or `scripts/verify.sh --fast` while iterating.
2. It runs, in order, stopping at the first failure:
   ruff lint -> ruff format check -> mypy -> pytest with coverage gate (>= 85%).
3. On failure: read ONLY the first failing check's output. Fix the cause, not the symptom:
   - lint/format: `ruff check --fix src tests && ruff format src tests`
   - mypy: add/correct type hints; do not add `# type: ignore` without a reason comment
   - test failure: decide whether the code or the test is wrong using the spec in `specs/`;
     never loosen an assertion just to pass
   - coverage below gate: add a test for the uncovered behaviour from the spec
4. Rerun until green. Report the final summary line.
5. Before a release: `mutmut run` and look at surviving mutants - each survivor is a
   behaviour no test pins down. Add a test or note why it does not matter.
