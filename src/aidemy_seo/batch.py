"""Batch CSV video SEO analysis (specs/batch-analysis.md).

Reads a CSV with `title`, `description`, `tags` (`|`-separated) and an optional `video_id`,
scores every row 0-100 with an explainable checklist (title length, words shared by title and
description, tags), finds duplicate titles and ranks the rows. Offline: 0 API units.

The score is its own rubric - NOT `titles.score_title()` and NOT vidIQ.
Handles user/channel data: never commit real exports.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from .text import fold, stems, strip_hashtags
from .titles import DIRECT_ADDRESS, EMOTION_WORDS, QUESTION_WORDS, TEMPLATES

REQUIRED = ("title", "description", "tags")
OPTIONAL = ("video_id",)
DELIMITERS = (",", ";", "\t")

TITLE_MIN, TITLE_MAX, TITLE_POINTS = 40, 65, 30
WORDS_POINTS = 30
TAGS_MIN, TAGS_MAX, TAGS_COUNT_POINTS = 5, 15, 20
TAGS_MAX_CHARS, TAGS_LENGTH_POINTS = 500, 20  # total must be < TAGS_MAX_CHARS

# Template and hook words say nothing about the topic ("musst", "wissen", "einfach erklärt").
FILLER_STEMS: frozenset[str] = frozenset().union(
    *(stems(t.replace("{x}", " ")) for t in TEMPLATES),
    *(stems(w) for w in EMOTION_WORDS | QUESTION_WORDS | DIRECT_ADDRESS),
)


class BatchError(ValueError):
    """A file-level problem: the CSV can't be analyzed at all."""


@dataclass
class BatchRow:
    line: int  # line in the file where the row starts (header = line 1)
    video_id: str | None
    title: str
    description: str
    tags: str


@dataclass
class BatchWarning:
    line: int | None  # None = about the whole file
    message: str
    skipped_row: bool = False  # this warning is why a row was not analyzed


@dataclass
class RowScore:
    score: float
    points: dict[str, float]
    issues: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # unique tags, first spelling kept
    repeated_tags: list[str] = field(default_factory=list)


@dataclass
class DuplicatePair:
    line_a: int
    line_b: int
    title: str  # title of line_a as written


# ---------------------------------------------------------------- scoring
def _title_length(title: str) -> tuple[int, list[str]]:
    n = len(title.strip())
    if TITLE_MIN <= n <= TITLE_MAX:
        return TITLE_POINTS, []
    off = TITLE_MIN - n if n < TITLE_MIN else n - TITLE_MAX
    return max(0, TITLE_POINTS - off), [f"title: {n} characters (aim {TITLE_MIN}-{TITLE_MAX})"]


def _topic_words(title: str) -> dict[str, str]:
    """Topic stem -> the word as written in the title (first occurrence), in title order."""
    out: dict[str, str] = {}
    for token in re.findall(r"\w+", strip_hashtags(title)):
        for s in sorted(stems(token) - FILLER_STEMS):
            out.setdefault(s, token)
    return out


def _shared_words(title: str, description: str) -> tuple[float, list[str]]:
    topic = _topic_words(title)
    if not topic:
        return 0.0, ["shared words: title has no topic words"]
    if not description.strip():
        return 0.0, ["shared words: description is empty"]
    in_desc = stems(description)
    missing = [word for s, word in topic.items() if s not in in_desc]
    shared = len(topic) - len(missing)
    points = round(WORDS_POINTS * shared / len(topic), 1)
    if not missing:
        return points, []
    names = ", ".join(f'"{w}"' for w in missing)
    return points, [f"shared words: description misses {names} ({shared} of {len(topic)} title words)"]


def _split_tags(tags: str) -> tuple[list[str], list[str]]:
    unique: dict[str, str] = {}
    repeated: list[str] = []
    for piece in tags.split("|"):
        tag = piece.strip()
        if not tag:
            continue
        if fold(tag) in unique:
            repeated.append(tag)
        else:
            unique[fold(tag)] = tag
    return list(unique.values()), repeated


def _tags(unique: list[str]) -> tuple[int, list[str]]:
    if not unique:
        return 0, ["tags: none"]
    points, issues = 0, []
    if TAGS_MIN <= len(unique) <= TAGS_MAX:
        points += TAGS_COUNT_POINTS
    else:
        issues.append(f"tags: {len(unique)} unique tags (aim {TAGS_MIN}-{TAGS_MAX})")
    total = sum(len(t) for t in unique)
    if total < TAGS_MAX_CHARS:
        points += TAGS_LENGTH_POINTS
    else:
        issues.append(f"tags: {total} characters in total (must be < {TAGS_MAX_CHARS})")
    return points, issues


def score_row(title: str, description: str, tags: str) -> RowScore:
    """Score one video 0-100: title length (30), shared title/description words (30), tags (40). Pure."""
    length, length_issues = _title_length(title)
    words, words_issues = _shared_words(title, description)
    unique, repeated = _split_tags(tags)
    tag_points, tag_issues = _tags(unique)
    return RowScore(
        score=round(length + words + tag_points, 1),
        points={"title_length": length, "shared_words": words, "tags": tag_points},
        issues=length_issues + words_issues + tag_issues,
        tags=unique,
        repeated_tags=repeated,
    )


# ---------------------------------------------------------------- reading
def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise BatchError(f"file not found: {path}") from None
    except IsADirectoryError:
        raise BatchError(f"{path} is a directory, not a CSV file") from None
    except OSError as e:
        raise BatchError(f"can't read {path}: {e.strerror or e}") from None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        line = data[: e.start].count(b"\n") + 1
        raise BatchError(f"{path} is not UTF-8 (line {line}) - save it as CSV UTF-8") from None


def _header(first_line: str) -> tuple[str, list[str]]:
    """Pick the first delimiter that gives all required columns; the header's raw field names."""
    candidates = []
    for d in DELIMITERS:
        names = next(csv.reader([first_line], delimiter=d), [])
        missing = [r for r in REQUIRED if r not in {n.strip().lower() for n in names}]
        if not missing:
            return d, names
        candidates.append((len(REQUIRED) - len(missing), len(names), missing, names))
    # no delimiter works: report against the split that found the most required columns
    _, _, missing, names = max(candidates, key=lambda c: (c[0], c[1]))
    found = ", ".join(n.strip() for n in names if n.strip()) or "none"
    raise BatchError(f"missing column(s): {', '.join(missing)} (required: {', '.join(REQUIRED)}; found: {found})")


def _blank(record: list[str]) -> bool:
    return all(not f.strip() for f in record)


def read_batch(path: str | Path) -> tuple[list[BatchRow], list[BatchWarning]]:
    """Read the CSV. Unknown columns are ignored, broken rows skipped (with a warning).

    Raises BatchError for file-level problems (missing, not UTF-8, no header, missing column).
    """
    path = Path(path)
    text = _read_text(path)
    if not text.strip():
        raise BatchError(f"{path} is empty - expected a header with {', '.join(REQUIRED)}")
    first_line = next(line for line in text.splitlines() if line.strip())
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_header(first_line)[0])
    warnings: list[BatchWarning] = []
    rows: list[BatchRow] = []
    prev_line = 0
    try:
        header = next(reader)
        while _blank(header):  # leading blank lines before the header
            prev_line = reader.line_num
            header = next(reader)
        prev_line = reader.line_num
        norm = [h.strip().lower() for h in header]
        for known in REQUIRED + OPTIONAL:
            if norm.count(known) > 1:
                raise BatchError(f"column '{known}' appears twice in the header")
        col = {name: norm.index(name) for name in REQUIRED + OPTIONAL if name in norm}
        ignored = [h.strip() or f"(unnamed column {i + 1})" for i, h in enumerate(header) if i not in set(col.values())]
        if ignored:
            warnings.append(BatchWarning(None, f"ignored columns: {', '.join(ignored)}"))
        for record in reader:
            line, prev_line = prev_line + 1, reader.line_num
            if _blank(record):
                continue
            if len(record) != len(header):
                warnings.append(BatchWarning(line, f"skipped - {len(record)} fields, header has {len(header)}", True))
                continue
            title = record[col["title"]].strip()
            if not title:
                warnings.append(BatchWarning(line, "skipped - empty title", True))
                continue
            vid = record[col["video_id"]].strip() if "video_id" in col else ""
            rows.append(BatchRow(line, vid or None, title, record[col["description"]], record[col["tags"]]))
    except csv.Error as e:
        raise BatchError(f"{path}: CSV error on line {prev_line + 1}: {e}") from None
    return rows, warnings


# ---------------------------------------------------------------- duplicates
def _title_key(title: str) -> str:
    return " ".join(fold(title).split())


def duplicate_title_pairs(rows: list[BatchRow]) -> list[DuplicatePair]:
    """Every pair of rows whose titles are equal after fold + whitespace collapse (hashtags kept)."""
    groups: dict[str, list[BatchRow]] = {}
    for r in rows:
        groups.setdefault(_title_key(r.title), []).append(r)
    pairs = [
        DuplicatePair(a.line, b.line, a.title)
        for group in groups.values()
        for a, b in combinations(sorted(group, key=lambda r: r.line), 2)
    ]
    return sorted(pairs, key=lambda p: (p.line_a, p.line_b))


# ---------------------------------------------------------------- report
@dataclass
class RankedRow:
    rank: int
    row: BatchRow
    score: RowScore

    def to_json(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "line": self.row.line,
            "video_id": self.row.video_id,
            "title": self.row.title,
            "score": self.score.score,
            "points": dict(self.score.points),
            "issues": list(self.score.issues),
        }


@dataclass
class BatchReport:
    file: str
    min_score: float
    rows: int  # data rows read (blank lines not counted)
    ranked: list[RankedRow]  # every analyzed row, best first
    warnings: list[BatchWarning]
    duplicates: list[DuplicatePair]

    @property
    def shown(self) -> list[RankedRow]:
        return [r for r in self.ranked if r.score.score >= self.min_score]

    def to_json(self) -> dict[str, Any]:
        shown = self.shown
        return {
            "file": self.file,
            "min_score": self.min_score,
            "rows": self.rows,
            "analyzed": len(self.ranked),
            "skipped": self.rows - len(self.ranked),
            "shown": len(shown),
            "hidden": len(self.ranked) - len(shown),
            "ranked": [r.to_json() for r in shown],
            "warnings": [{"line": w.line, "message": w.message} for w in self.warnings],
            "duplicates": [{"lines": [d.line_a, d.line_b], "title": d.title} for d in self.duplicates],
        }

    def lines(self) -> list[str]:
        shown = self.shown
        n_dup = len(self.duplicates)
        out = [
            f"analyzed {len(self.ranked)} of {self.rows} rows in {self.file} ({self.rows - len(self.ranked)} skipped); "
            f"{n_dup} duplicate title pair{'' if n_dup == 1 else 's'}; "
            f"showing {len(shown)} with score >= {self.min_score:g} ({len(self.ranked) - len(shown)} hidden)",
            "RANKING",
        ]
        if not self.ranked:
            out.append("  (no valid rows)")
        else:
            out.append("rank  score  length  words  tags  line  title")
            for r in shown:
                p = r.score.points
                out.append(
                    f"{r.rank:>4}  {r.score.score:>5.1f}  {p['title_length']:>6}  {p['shared_words']:>5.1f}  "
                    f"{p['tags']:>4}  {r.row.line:>4}  {r.row.title}"
                )
                out += [f"        - {i}" for i in r.score.issues]
            if not shown:
                out.append(f"  (no row with score >= {self.min_score:g})")
        out.append("WARNINGS")
        out += [f"  {'' if w.line is None else f'line {w.line}: '}{w.message}" for w in self.warnings] or ["  (none)"]
        out.append("DUPLICATE TITLES")
        out += [f"  lines {d.line_a} and {d.line_b}: {d.title}" for d in self.duplicates] or ["  (none)"]
        return out


def check_min_score(min_score: float) -> float:
    if not (math.isfinite(min_score) and 0 <= min_score <= 100):
        raise BatchError(f"--min-score must be a number from 0 to 100, got {min_score}")
    return float(min_score)


def analyze_batch(path: str | Path, *, min_score: float = 0.0) -> BatchReport:
    """Read, score, rank (score desc, then line) and find duplicate titles. 0 API units."""
    min_score = check_min_score(min_score)
    rows, warnings = read_batch(path)
    skipped = sum(w.skipped_row for w in warnings)
    scored = [(row, score_row(row.title, row.description, row.tags)) for row in rows]
    for row, s in scored:
        if s.repeated_tags:
            warnings.append(BatchWarning(row.line, f"repeated tags ignored: {', '.join(s.repeated_tags)}"))
    warnings.sort(key=lambda w: -1 if w.line is None else w.line)  # stable: file-level first, then by line
    scored.sort(key=lambda x: (-x[1].score, x[0].line))
    ranked = [RankedRow(i + 1, row, s) for i, (row, s) in enumerate(scored)]
    return BatchReport(
        file=str(path),
        min_score=min_score,
        rows=len(rows) + skipped,
        ranked=ranked,
        warnings=warnings,
        duplicates=duplicate_title_pairs(rows),
    )
