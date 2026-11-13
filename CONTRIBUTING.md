# Contributing (people and coding agents)

1. **Start from a ticket / user need** and the real example behind it.
2. **Spec first:** update `specs/<feature>.md` (requirements + Given/When/Then scenarios, each
   naming its test). Real alternative chosen? Add an ADR in `docs/adr/`.
3. **Tests from the spec**, then the smallest code change. No network in unit tests.
4. **Verify loop:** `scripts/verify.sh` until green (`--fast` while iterating).
   Enable the git hook once: `git config core.hooksPath .githooks`.
5. **Small PRs:** one feature per PR, use the PR template. CI must pass before merging.
6. **Line-by-line review** for secrets, quota/cost and user/channel data.
7. Before a release: `mutmut run` - every surviving mutant is behaviour no test pins down.

Agents: read `CLAUDE.md` first; the `spec-first-feature` and `verify` skills in
`.claude/skills/` describe the workflow step by step.
