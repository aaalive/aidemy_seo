"""Title A/B packs for YouTube Studio's "Test & Compare" and reading their results (specs/ab-testing.md).

YouTube Studio tests up to 3 titles on one video and reports each title's share of the watch time.

    ab_pack(csv, out, weights=...)   3 titles per video (search, question, why) -> a CSV to paste from
    ab_results(csv, weights_out)      winner per video (margin >= 0.05) -> variant weights JSON

The weights file of `ab_results` is the `--weights` input of the next `ab_pack`: the variant that
won most often comes first. Titles reuse `titles.TEMPLATES` and `titles.build_title` (66 characters).
Input files are never written to. Standard library only, offline, 0 API units.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .fileio import CsvError, CsvTable, CsvWarning, csv_text, read_table, same_file, write_text_atomic
from .series import grade_kind, series_key
from .series import title_hashtags as hashtags_in_title
from .text import fold
from .titles import MAX_TITLE_LEN, TEMPLATES, build_title

VARIANTS: dict[str, str] = {  # variant -> template; this order is the default order of a pack
    "search": TEMPLATES[1],  # "{x} einfach erklärt – das musst du wissen!" - the words people search
    "question": TEMPLATES[0],  # "{x} – kannst du es erklären?"
    "why": TEMPLATES[3],  # "Warum {x}? Einfach erklärt"
}
MAX_TAGS = 2  # hashtags carried over from the current title
PACK_REQUIRED = ("video_id", "title", "keyword")
PACK_COLUMNS = ("video_id", "variant", "title", "length")
RESULTS_REQUIRED = ("video_id", "variant", "watch_time_share")
WIN_MARGIN = Decimal("0.05")  # top share - second share needed for a winner
MIN_DECIDED = 5  # weights change the order of a pack only after this many decided tests
MIN_TESTS_PER_VARIANT = 3  # a variant's weight counts only after it was in this many decided tests
MIN_TITLES = 2  # Test & Compare needs 2 or 3 titles - a video keeps its test while 2 fit
MAX_SHARE_SUM = Decimal("1.01")  # shares of one video add up to 1; 1% slack for YouTube's rounding
WINNER, INCONCLUSIVE = "winner", "inconclusive"
Weights = dict[str, float | None]  # variant -> weight; None = not enough info (fewer than 3 decided tests)


class AbError(ValueError):
    """Bad input for an A/B command (file, weights, output path). One line, safe to show as is."""


def _read(path: str | Path, required: tuple[str, ...]) -> CsvTable:
    try:
        return read_table(path, required)
    except CsvError as e:
        raise AbError(str(e)) from None


def check_not_input(out: str | Path, inputs: dict[str, str | Path | None], what: str) -> None:
    """Refuse to write `out` over an input file - the inputs are never changed."""
    for name, path in inputs.items():
        if path is not None and same_file(out, path):
            raise AbError(f"{what} {out} is the {name} - choose another file, an input is never overwritten")
    if Path(out).is_dir():
        raise AbError(f"{what} {out} is a directory")


def _write(path: str | Path, text: str, what: str) -> None:
    try:
        write_text_atomic(path, text)
    except OSError as e:
        raise AbError(f"can't write {what} {path}: {e.strerror or e}") from None


# ---------------------------------------------------------------- ab-pack
def pack_hashtags(title: str, limit: int = MAX_TAGS) -> tuple[list[str], list[str]]:
    """(hashtags for the new titles, the ones that are never dropped), from the current title.

    Each hashtag once (case and umlauts ignored, first spelling kept), at most `limit`, in title
    order. The grade tags come first when choosing and are never dropped: #KlasseN, a range
    (#Klasse11-12, kept as written) and a level (#Q11, #Oberstufe); in a series title (see
    series.series_key) its #Fach too - so a new title keeps the video's grade and series."""
    unique: dict[str, str] = {}
    for tag in hashtags_in_title(title):  # a range like #Klasse11-12 stays one tag (never cut to #Klasse11)
        unique.setdefault(fold(tag), tag)
    by_kind = {kind: [t for t in unique.values() if grade_kind(t) == kind] for kind in ("grade", "range", "level")}
    key = series_key(title)
    subject = [unique[fold("#" + key[0])]] if isinstance(key, tuple) else []
    keep = list(dict.fromkeys(subject + by_kind["grade"] + by_kind["range"] + by_kind["level"]))
    chosen = set(list(dict.fromkeys(keep + list(unique.values())))[:limit])
    tags = [t for t in unique.values() if t in chosen]  # title order
    return tags, [t for t in tags if t in keep]


def load_weights(path: str | Path) -> tuple[Weights, int]:
    """(weights, decided tests) from a weights JSON as written by ab-results:
    {"decided": 6, "weights": {"search": null, "question": 0.0, "why": 0.67}}. null (or a missing
    variant) = not enough info: the variant keeps its default place, it is not ranked as a loser."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AbError(f"weights file not found: {p}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise AbError(f"can't read weights file {p}: {getattr(e, 'strerror', None) or e}") from None
    shape = '{"decided": 6, "weights": {"search": 0.5, "why": 0.5}} (the file ab-results writes)'
    if not isinstance(data, dict) or set(data) != {"decided", "weights"} or not isinstance(data["weights"], dict):
        raise AbError(f"weights file {p} must look like {shape}")
    decided = data["decided"]
    if isinstance(decided, bool) or not isinstance(decided, int) or decided < 0:
        raise AbError(f"weights file {p}: decided must be a whole number >= 0, got {decided!r}")
    unknown = [k for k in data["weights"] if k not in VARIANTS]
    if unknown:
        raise AbError(f"weights file {p}: unknown variant {', '.join(unknown)} - expected {', '.join(VARIANTS)}")
    weights: Weights = {}
    for name in VARIANTS:
        w = data["weights"].get(name)
        if w is None:
            weights[name] = None
            continue
        if isinstance(w, bool) or not isinstance(w, int | float) or not math.isfinite(w):
            raise AbError(f"weights file {p}: the weight of {name} must be a number or null, got {w!r}")
        weights[name] = float(w)
    return weights, decided


def variant_order(weights: Weights | None = None) -> list[str]:
    """Highest weight first; equal weights (and no weights) keep the order search, question, why.

    A variant without a weight (None: not enough info) is not a loser - it is unknown. It keeps its
    default place; the variants with a weight are ranked in the other places."""
    default = list(VARIANTS)
    if not weights:
        return default
    known = iter(sorted((v for v in default if weights.get(v) is not None), key=lambda v: -(weights[v] or 0.0)))
    return [v if weights.get(v) is None else next(known) for v in default]


def weight_text(w: float | None) -> str:
    return "not enough info" if w is None else f"{w:.2f}"


@dataclass
class PackRow:
    line: int  # line of the video in the input CSV
    video_id: str
    variant: str
    title: str
    length: int  # characters (Unicode code points), hashtags included


@dataclass
class DroppedVariant:
    line: int
    video_id: str
    variant: str
    reason: str


@dataclass
class PackReport:
    file: str
    out: str
    order: list[str]
    weights: Weights | None
    weights_file: str | None
    decided: int | None  # decided tests behind the weights (None = no --weights)
    rows: list[PackRow]
    dropped: list[DroppedVariant]  # variants that didn't fit 66 characters (their video kept 2 titles)
    videos: int  # data rows read (blank lines not counted)
    warnings: list[CsvWarning] = field(default_factory=list)
    delimiter: str = ","  # the input's - the output CSV opens like the input did
    bom: bool = False

    @property
    def weights_applied(self) -> bool:
        return self.decided is not None and self.decided >= MIN_DECIDED

    @property
    def packed(self) -> int:
        return len({r.video_id for r in self.rows})

    def csv(self) -> str:
        body = [[r.video_id, r.variant, r.title, r.length] for r in self.rows]
        return csv_text([list(PACK_COLUMNS), *body], delimiter=self.delimiter, bom=self.bom)

    def to_json(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "out": self.out,
            "order": list(self.order),
            "weights": self.weights,
            "weights_file": self.weights_file,
            "decided": self.decided,
            "weights_applied": self.weights_applied,
            "videos": self.videos,
            "packed": self.packed,
            "skipped": self.videos - self.packed,
            "dropped": [
                {"line": d.line, "video_id": d.video_id, "variant": d.variant, "reason": d.reason} for d in self.dropped
            ],
            "rows": [
                {"video_id": r.video_id, "variant": r.variant, "title": r.title, "length": r.length} for r in self.rows
            ],
            "warnings": [{"line": w.line, "message": w.message} for w in self.warnings],
        }

    def lines(self) -> list[str]:
        n = len(self.rows)
        out = [
            f"wrote {n} title{'' if n == 1 else 's'} for {self.packed} of {self.videos} videos to {self.out} "
            f"({self.videos - self.packed} skipped, {len(self.dropped)} variant{'' if len(self.dropped) == 1 else 's'} "
            "dropped)"
        ]
        w = self.weights
        if w is None:
            out.append(f"order: {', '.join(self.order)} (default - no --weights)")
        elif not self.weights_applied:
            out.append(
                f"order: {', '.join(self.order)} (default - only {self.decided} decided tests in "
                f"{self.weights_file}, the weights count from {MIN_DECIDED})"
            )
        else:
            order = ", ".join(f"{v} {w[v]:.2f}" if w[v] is not None else f"{v} (not enough info)" for v in self.order)
            keep = "; not enough info keeps the default place" if any(x is None for x in w.values()) else ""
            out.append(
                f"order: {order} (highest weight first{keep}, from {self.weights_file}, {self.decided} decided tests)"
            )
        out.append("TITLES")
        if self.rows:
            out.append("video_id      variant   length  title")
            out += [f"{r.video_id:<12}  {r.variant:<8}  {r.length:>6}  {r.title}" for r in self.rows]
        else:
            out.append("  (no valid rows)")
        out.append("WARNINGS")
        out += [f"  {'' if w.line is None else f'line {w.line}: '}{w.message}" for w in self.warnings] or ["  (none)"]
        return out


def variant_title(keyword: str, variant: str, tags: list[str], keep: list[str]) -> str:
    """One variant's title, at most 66 characters. When it is too long, hashtags are dropped from the
    end, except `keep` (the series hashtags #KlasseN, and #Fach in a series title), which are never
    dropped. Raises AbError with the reason when it still doesn't fit - a title is never cut."""
    use = list(tags)
    t = build_title(keyword, VARIANTS[variant], use, sys.maxsize)  # nothing dropped yet
    while len(t) > MAX_TITLE_LEN and any(x not in keep for x in use):
        use.remove([x for x in use if x not in keep][-1])
        t = build_title(keyword, VARIANTS[variant], use, sys.maxsize)
    if len(t) <= MAX_TITLE_LEN:
        return t
    if keep:
        raise AbError(
            f"the {variant} title is {len(t)} characters with {' '.join(keep)} (max {MAX_TITLE_LEN}) "
            "- series hashtags are never dropped"
        )
    raise AbError(f"the {variant} title is {len(t)} characters even without hashtags (max {MAX_TITLE_LEN})")


def pack_titles(
    keyword: str, title: str, order: list[str] | None = None
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(fitting (variant, title) pairs, dropped (variant, reason) pairs) for one video: its keyword in
    every template + up to 2 of its title's hashtags. A variant that can't fit 66 characters is
    dropped on its own; the others stay."""
    tags, keep = pack_hashtags(title)
    fits, dropped = [], []
    for variant in order or list(VARIANTS):
        try:
            fits.append((variant, variant_title(keyword, variant, tags, keep)))
        except AbError as e:
            dropped.append((variant, str(e)))
    return fits, dropped


def make_pack(path: str | Path, *, out: str = "", weights_path: str | Path | None = None) -> PackReport:
    """Read the input CSV (video_id, title, keyword) and build 3 titles per video (2 when one variant
    can't fit 66 characters - with a warning; fewer than 2: the video is skipped). Writes nothing."""
    weights, decided = load_weights(weights_path) if weights_path is not None else (None, None)
    applied = decided is not None and decided >= MIN_DECIDED
    order = variant_order(weights if applied else None)
    table = _read(path, PACK_REQUIRED)
    warnings: list[CsvWarning] = []
    if table.ignored:
        warnings.append(CsvWarning(None, f"ignored columns: {', '.join(table.ignored)}"))
    rows: list[PackRow] = []
    dropped_rows: list[DroppedVariant] = []
    seen: dict[str, int] = {}
    for r in table.rows:
        vid = table.value(r, "video_id").strip()
        keyword = " ".join(table.value(r, "keyword").split())
        problem = r.error
        if problem is None:
            if not vid:
                problem = "skipped - empty video_id"
            elif vid in seen:
                problem = f"skipped - video_id {vid} is already on line {seen[vid]}"
            elif not table.value(r, "title").strip():
                problem = "skipped - empty title"
            elif not keyword:
                problem = "skipped - empty keyword"
        if problem is None:
            seen[vid] = r.line
            titles, dropped = pack_titles(keyword, table.value(r, "title"), order)
            reasons = "; ".join(reason for _, reason in dropped)
            if len(titles) < MIN_TITLES:
                fit = f"{len(titles)} fit{'s' if len(titles) == 1 else ''}"
                problem = (
                    f"skipped - a test needs at least {MIN_TITLES} titles, only {fit} {MAX_TITLE_LEN} characters: "
                    f"{reasons} - use a shorter keyword"
                )
            else:
                rows += [PackRow(r.line, vid, v, t, len(t)) for v, t in titles]
                left = ", ".join(v for v, _ in titles)
                for variant, reason in dropped:
                    warnings.append(CsvWarning(r.line, f"{variant} variant dropped - {reason}; testing {left}"))
                    dropped_rows.append(DroppedVariant(r.line, vid, variant, reason))
        if problem is not None:
            warnings.append(CsvWarning(r.line, problem, skipped_row=True))
    return PackReport(
        file=str(path),
        out=str(out),
        order=order,
        weights=weights,
        weights_file=None if weights_path is None else str(weights_path),
        decided=decided,
        rows=rows,
        dropped=dropped_rows,
        videos=len(table.rows),
        warnings=warnings,
        delimiter=table.delimiter,
        bom=table.bom,
    )


def ab_pack(path: str | Path, out: str | Path, *, weights_path: str | Path | None = None) -> PackReport:
    """make_pack + write the CSV to `out` (atomic). The output uses the input's delimiter (and its BOM).
    Refuses (AbError, nothing written) when `out` is the input CSV or the weights file."""
    check_not_input(out, {"input CSV": path, "weights file": weights_path}, "--out")
    rep = make_pack(path, out=str(out), weights_path=weights_path)
    _write(out, rep.csv(), "--out")
    return rep


# ---------------------------------------------------------------- ab-results
def parse_share(raw: str) -> Decimal:
    """A watch time share: 0.42, 0,42 (German decimal comma) or 42% / 42,5 %. Exact (Decimal), 0-1."""
    s = raw.strip().replace(",", ".")
    percent = s.endswith("%")
    if percent:
        s = s[:-1].strip()
    if not s:
        raise ValueError("empty watch_time_share")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"watch_time_share {raw.strip()!r} is not a number") from None
    if not d.is_finite():
        raise ValueError(f"watch_time_share {raw.strip()!r} is not a number")
    if percent:
        d /= 100
    if not 0 <= d <= 1:
        raise ValueError(f"watch_time_share {raw.strip()} must be a share from 0 to 1 (0.42) or a percentage (42%)")
    return d


def decide(shares: dict[str, Decimal]) -> tuple[str, str | None, Decimal]:
    """(result, winner, margin) for one test: winner when top - second >= 0.05, else inconclusive."""
    ranked = sorted(shares.items(), key=lambda kv: -kv[1])
    margin = ranked[0][1] - ranked[1][1]
    if margin >= WIN_MARGIN:
        return WINNER, ranked[0][0], margin
    return INCONCLUSIVE, None, margin


def compute_weights(wins: dict[str, int], decided_with: dict[str, int]) -> Weights:
    """wins / decided tests the variant was in, per variant, rounded half up to 2 decimals.

    Only tests that had the variant count: a search title dropped for length can't win that test,
    so the test must not count against it. A variant in fewer than 3 decided tests gets None - not
    enough info. It is not a loser (not 0) and not a winner (1 win in 1 test is not 1.0)."""
    cent = Decimal("0.01")
    return {
        v: float((Decimal(wins.get(v, 0)) / decided_with[v]).quantize(cent, ROUND_HALF_UP))
        if decided_with.get(v, 0) >= MIN_TESTS_PER_VARIANT
        else None
        for v in VARIANTS
    }


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class

    video_id: str
    line: int  # first line of the video in the CSV
    shares: dict[str, Decimal]  # variant -> share, in file order
    result: str  # "winner" | "inconclusive"
    winner: str | None
    margin: Decimal  # top share - second share

    def ranked(self) -> list[tuple[str, Decimal]]:
        return sorted(self.shares.items(), key=lambda kv: -kv[1])


@dataclass
class NotEvaluated:
    video_id: str
    line: int
    reason: str


@dataclass
class ResultsReport:
    file: str
    weights_file: str
    tests: list[TestResult]
    not_evaluated: list[NotEvaluated]
    warnings: list[CsvWarning]

    @property
    def decided(self) -> int:
        return sum(t.result == WINNER for t in self.tests)

    @property
    def wins(self) -> dict[str, int]:
        return {v: sum(t.winner == v for t in self.tests) for v in VARIANTS}

    @property
    def decided_with(self) -> dict[str, int]:
        """Per variant: the decided tests it was in (its chances to win)."""
        return {v: sum(t.result == WINNER and v in t.shares for t in self.tests) for v in VARIANTS}

    @property
    def weights(self) -> Weights:
        return compute_weights(self.wins, self.decided_with)

    def weights_json(self) -> str:
        return json.dumps({"decided": self.decided, "weights": self.weights}, indent=2) + "\n"

    def to_json(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "weights_file": self.weights_file,
            "videos": len(self.tests) + len(self.not_evaluated),
            "decided": self.decided,
            "inconclusive": len(self.tests) - self.decided,
            "tests": [
                {
                    "video_id": t.video_id,
                    "result": t.result,
                    "winner": t.winner,
                    "margin": float(t.margin),
                    "shares": {v: float(s) for v, s in t.shares.items()},
                }
                for t in self.tests
            ],
            "not_evaluated": [{"video_id": n.video_id, "reason": n.reason} for n in self.not_evaluated],
            "wins": self.wins,
            "decided_with": self.decided_with,
            "weights": self.weights,
            "warnings": [{"line": w.line, "message": w.message} for w in self.warnings],
        }

    def lines(self) -> list[str]:
        n, d = len(self.tests) + len(self.not_evaluated), self.decided
        out = [
            f"{n} video{'' if n == 1 else 's'} in {self.file}: {d} winner{'' if d == 1 else 's'}, "
            f"{len(self.tests) - self.decided} inconclusive, {len(self.not_evaluated)} not evaluated "
            f"(winner = top share - second share >= {WIN_MARGIN})",
            "TESTS",
        ]
        if self.tests:
            out.append("video_id      result        top       share  second    share  margin")
            for t in self.tests:
                (top, s1), (second, s2) = t.ranked()[:2]
                out.append(
                    f"{t.video_id:<12}  {t.result:<12}  {top:<8}  {float(s1):>5.3f}  {second:<8}  {float(s2):>5.3f}  "
                    f"{float(t.margin):>6.3f}"
                )
        else:
            out.append("  (no test could be evaluated)")
        out.append("NOT EVALUATED")
        out += [f"  {n.video_id} (line {n.line}): {n.reason}" for n in self.not_evaluated] or ["  (none)"]
        out.append("WARNINGS")
        out += [f"  {'' if w.line is None else f'line {w.line}: '}{w.message}" for w in self.warnings] or ["  (none)"]
        out.append(
            f"WEIGHTS (wins / decided tests the variant was in, from {MIN_TESTS_PER_VARIANT} tests on; "
            f"{self.decided} decided tests, written to {self.weights_file})"
        )
        wins, weights, chances = self.wins, self.weights, self.decided_with
        out += [
            f"  {v:<8}  {weight_text(weights[v])}  ({wins[v]} of {chances[v]}"
            + (f" - needs {MIN_TESTS_PER_VARIANT} tests" if chances[v] < MIN_TESTS_PER_VARIANT else "")
            + ")"
            for v in VARIANTS
        ]
        if self.decided < MIN_DECIDED:
            out.append(
                f"  only {self.decided} decided tests - ab-pack keeps the default order until {MIN_DECIDED} are decided"
            )
        return out


def read_results(path: str | Path, *, weights_file: str = "") -> ResultsReport:
    """Read a results CSV (video_id, variant, watch_time_share) and decide every test. Writes nothing.

    A video is NOT evaluated (never guessed) when one of its rows was skipped, a variant appears twice,
    it has only 1 variant, or its shares add up to more than 1."""
    table = _read(path, RESULTS_REQUIRED)
    warnings: list[CsvWarning] = []
    ignored = [c for c in table.ignored if c.lower() not in PACK_COLUMNS]  # an ab-pack file + shares is fine
    if ignored:
        warnings.append(CsvWarning(None, f"ignored columns: {', '.join(ignored)}"))
    first_line: dict[str, int] = {}
    rows: dict[str, list[tuple[int, str, Decimal]]] = {}
    broken: dict[str, int] = {}  # video_id -> first skipped line
    for r in table.rows:
        vid = table.value(r, "video_id").strip()  # also read from a broken row, to mark its video
        if vid:
            first_line.setdefault(vid, r.line)
            rows.setdefault(vid, [])
        problem = r.error
        variant = fold(table.value(r, "variant").strip()) if problem is None else ""
        share = Decimal(0)
        if problem is None and not vid:
            problem = "skipped - empty video_id"
        if problem is None and variant not in VARIANTS:
            shown = table.value(r, "variant").strip()
            problem = f"skipped - unknown variant {shown!r} (expected {', '.join(VARIANTS)})"
        if problem is None:
            try:
                share = parse_share(table.value(r, "watch_time_share"))
            except ValueError as e:
                problem = f"skipped - {e}"
        if problem is not None:
            warnings.append(CsvWarning(r.line, problem, skipped_row=True))
            if vid:
                broken.setdefault(vid, r.line)
            continue
        rows[vid].append((r.line, variant, share))

    tests: list[TestResult] = []
    not_evaluated: list[NotEvaluated] = []
    for vid, entries in rows.items():
        line = first_line[vid]
        lines_of: dict[str, list[int]] = {}
        for ln, variant, _ in entries:
            lines_of.setdefault(variant, []).append(ln)
        twice = [(v, ls) for v, ls in lines_of.items() if len(ls) > 1]
        shares = {variant: s for _, variant, s in entries}
        total = sum(shares.values(), Decimal(0))
        reason = None
        if vid in broken:
            reason = f"line {broken[vid]} was skipped - a missing variant could be the real winner"
        elif twice:
            v, ls = twice[0]
            reason = f"variant {v} appears twice (lines {', '.join(map(str, ls))})"
        elif len(shares) < 2:
            reason = f"only 1 variant ({', '.join(shares) or 'none'}) - a test compares 2 or 3"
        elif total > MAX_SHARE_SUM:
            reason = f"watch time shares add up to {float(total):.2f} - more than 1 (100%)"
        if reason is not None:
            not_evaluated.append(NotEvaluated(vid, line, reason))
            continue
        result, winner, margin = decide(shares)
        tests.append(TestResult(vid, line, shares, result, winner, margin))
    return ResultsReport(str(path), weights_file, tests, not_evaluated, warnings)


def ab_results(path: str | Path, weights_out: str | Path) -> ResultsReport:
    """read_results + write the weights JSON to `weights_out` (atomic). Refuses (AbError, nothing
    written) when `weights_out` is the input CSV."""
    check_not_input(weights_out, {"input CSV": path}, "--weights")
    rep = read_results(path, weights_file=str(weights_out))
    _write(weights_out, rep.weights_json(), "--weights")
    return rep
