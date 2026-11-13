# aidemy_seo - project context for coding agents

Read this first in every session. Keep it short; details live in `specs/` and `docs/adr/`.

## What this is
YouTube SEO analytics and optimisation for educational channels (MIT). Sibling of
`../pub_pipeline` (aidemy_pub), which imports it. Core = pure standard library; network
only through injectable `fetch` callables.

## Commands
- `scripts/verify.sh` - THE check. Lint, format check, types, tests with coverage gate.
  Run it after every change and before saying "done". It must be green.
- `scripts/verify.sh --fast` - lint + unit tests only (used by the agent hook).
- `pytest -q -m live` - opt-in tests against the real YouTube APIs (need network/key).
- `mutmut run` - mutation testing (slow; run before releases, not on every change).

## How to work (non-negotiable)
1. **Spec first.** Every feature has a spec in `specs/<feature>.md` (requirements +
   scenarios). New feature or behaviour change: write/update the spec BEFORE code.
   Each scenario names the test that proves it.
2. **Decisions go in ADRs** (`docs/adr/NNNN-title.md`, template `0000-template.md`) when
   you choose between real alternatives (a dependency, a data source, a scoring method).
3. **Tests are not written to pass.** A must-catch test from a real example (real lesson,
   real title, real score, real API response shape) plus a must-not-flag test for the
   nearest legitimate case. Never weaken an assertion to make a change pass.
4. **Small steps.** One feature per branch/PR; modular commits. Smallest useful context:
   read the spec + the module you change, not the whole repo.
5. **No network in unit tests.** Inject `fetch`. Live checks go under `-m live`.
6. **Honest output.** Unknown is unknown (`-1`, "not enough data") - never a guessed number.

## Review rules
Line-by-line human review for anything touching: API keys/secrets, quota/cost (each
YouTube call costs units; document the cost in the docstring), and user/channel data.
Never commit `.env`, keys, tokens or downloaded channel data.

## Token economy
Prefer `--fast` while iterating, full `verify.sh` once at the end. Don't paste large
JSON/test output into the conversation - read the summary line and the first failure.

## Layout
`src/aidemy_seo/` modules (one topic each), `tests/` (unit + integration + live),
`specs/` (what), `docs/adr/` (why), `scripts/` (verify), `.claude/` (permissions, hooks, skills).
