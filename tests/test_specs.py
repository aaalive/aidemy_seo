"""Specs and tests can't drift apart: every `Test:` reference in specs/*.md must exist."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tests_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def test_every_spec_scenario_points_to_an_existing_test():
    refs = []
    for spec in (ROOT / "specs").glob("*.md"):
        refs += [
            (spec.name, f, t)
            for f, t in re.findall(r"Test:\s*(tests/[\w/]+\.py)::(\w+)", spec.read_text(encoding="utf-8"))
        ]
    assert refs, "no Test: references found in specs/"
    missing = [(s, f, t) for s, f, t in refs if not (ROOT / f).is_file() or t not in _tests_in(ROOT / f)]
    assert not missing, f"spec scenarios pointing to missing tests: {missing}"


def test_every_test_is_covered_by_a_spec():
    referenced = set()
    for spec in (ROOT / "specs").glob("*.md"):
        referenced |= set(re.findall(r"::(\w+)", spec.read_text(encoding="utf-8")))
    unspecced = []
    for f in (ROOT / "tests").glob("test_*.py"):
        if f.name in ("test_specs.py",) or f.name.startswith("test_integration") or f.name.startswith("test_live"):
            continue
        unspecced += [f"{f.name}::{t}" for t in _tests_in(f) - referenced]
    assert not unspecced, f"tests with no spec scenario (add them to specs/): {unspecced}"
