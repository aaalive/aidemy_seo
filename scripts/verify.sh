#!/usr/bin/env bash
# Local CI - the single verification loop used by: you, the git pre-commit hook,
# the Claude Code hooks (.claude/settings.json) and GitHub Actions. Green = done.
#   scripts/verify.sh          full: lint, format, types, all tests + coverage gate
#   scripts/verify.sh --fast   lint + unit tests (quick, used after every agent edit)
#   --quiet                    only the summary / first failure (saves agent tokens)
set -u
cd "$(dirname "$0")/.."
FAST=0; QUIET=0
for a in "$@"; do case "$a" in --fast) FAST=1;; --quiet) QUIET=1;; esac; done

step() {  # step <name> <command...>
  local name="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    [ "$QUIET" = 1 ] || echo "ok    $name"
  else
    echo "FAIL  $name"
    echo "$out" | head -n 40
    echo "verify: FAILED at '$name' - fix this first, then rerun scripts/verify.sh"
    exit 1
  fi
}

step "ruff lint"     ruff check src tests
step "ruff format"   ruff format --check src tests
if [ "$FAST" = 1 ]; then
  step "unit tests"  python -m pytest -q -x --no-header -p no:cacheprovider --ignore=tests/test_integration_cli.py
  echo "verify --fast: OK"
  exit 0
fi
step "mypy"          mypy
step "tests+coverage" python -m pytest -q -x --no-header -p no:cacheprovider --cov --cov-report=term:skip-covered
echo "verify: OK (lint, format, types, $(python -m pytest -q --co -p no:cacheprovider 2>/dev/null | tail -1 | grep -o '^[0-9]*') tests, coverage >= 85%)"
