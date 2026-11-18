"""Shorts series from title hashtags (specs/series.md).

Every title that `titles.title_tags()` builds ends with `#Fach #KlasseN` (or a grade range / school
level as written, which is never turned into one grade). Videos with the same
subject and grade form a series "Fach Klasse N" once there are at least 2 of them. Every other
video is listed as "not sorted", with the reason. Reads a CSV (title, optional video_id), writes
nothing. Standard library only, offline, 0 API units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fileio import CsvError, CsvWarning, read_table
from .text import HASHTAG_RE, fold

REQUIRED = ("title",)
OPTIONAL = ("video_id",)
MIN_VIDEOS = 2  # a series needs at least this many videos
GRADE_RE = re.compile(r"#klasse(\d+)")  # on the folded hashtag: #Klasse10, #klasse5, #Klasse05
# Grade tags that are NOT one grade - recognised, but never turned into a grade (see specs/series.md):
# a range (#Klasse11-12, #Klasse11/12, #Klasse11bis12, #Klasse11_12) spans two grades, and a level
# (#Q11, #Q1, #Oberstufe, #SekII, #Abitur) means different grades in different Bundeslaender.
RANGE_RE = re.compile(r"#klasse(\d+)(?:[-–/_]|bis|und)(\d+)")  # on the folded tag
LEVEL_RE = re.compile(r"#(?:q\d{1,2}|(?:ober|mittel|unter)stufe|sek(?:undarstufe)?(?:1|2|i|ii)|ef|abi|abitur)")
# "#Klasse11-12" is ONE tag here; YouTube and text.hashtags() stop at the "-" and see only "#Klasse11"
RANGE_IN_TITLE_RE = re.compile(r"(?<![\w/&?=])#klasse\d+[-–/]\d+(?![\wäöüÄÖÜß])", re.IGNORECASE)
PLATFORM_TAGS = frozenset({"#shorts", "#short", "#youtubeshorts"})  # never a subject


class SeriesError(ValueError):
    """The CSV can't be read at all. One line, safe to show as is."""


@dataclass
class SeriesVideo:
    line: int
    video_id: str | None
    title: str

    def to_json(self) -> dict[str, Any]:
        return {"line": self.line, "video_id": self.video_id, "title": self.title}


@dataclass
class Series:
    name: str  # "Biologie Klasse 11"
    subject: str  # "Biologie" - spelled as in the first video
    grade: int
    videos: list[SeriesVideo]


@dataclass
class NotSorted:
    video: SeriesVideo
    reason: str


def title_hashtags(title: str) -> list[str]:
    """The title's hashtags in title order, as written. A grade range written with - – or /
    (#Klasse11-12) is one tag - text.hashtags() would cut it to #Klasse11, a different grade."""
    ranges = [(m.start(), m.end()) for m in RANGE_IN_TITLE_RE.finditer(title)]
    masked = title
    for start, end in ranges:
        masked = masked[:start] + " " * (end - start) + masked[end:]
    found = [(m.start(), m.group(0)) for m in HASHTAG_RE.finditer(masked)]
    found += [(start, title[start:end]) for start, end in ranges]
    return [tag for _, tag in sorted(found)]


def grade_kind(tag: str) -> str | None:
    """ "grade" (#Klasse10), "range" (#Klasse11-12), "level" (#Q11, #Oberstufe) or None."""
    t = fold(tag)
    if GRADE_RE.fullmatch(t):
        return "grade"
    if RANGE_RE.fullmatch(t):
        return "range"
    if LEVEL_RE.fullmatch(t):
        return "level"
    return None


def series_key(title: str) -> tuple[str, int] | str:
    """(subject, grade) of a title, or the reason it has none.

    Grade = the number of the one #KlasseN hashtag; two different grades are ambiguous. A range
    (#Klasse11-12) or a level (#Q11, #Oberstufe) is never turned into a grade - without a #KlasseN
    the video is not sorted, with a reason; next to a #KlasseN it is extra information.
    Subject = the first hashtag that is no grade, range or level tag (nor #Klasse...) and not #Shorts."""
    written = title_hashtags(title)
    tags = list(dict.fromkeys(fold(t) for t in written))
    spelled = {fold(t): t for t in reversed(written)}  # first spelling wins
    grades = list(dict.fromkeys(int(m.group(1)) for t in tags if (m := GRADE_RE.fullmatch(t))))
    others = [t for t in tags if grade_kind(t) in ("range", "level")]
    subjects = [t for t in tags if not t.startswith("#klasse") and t not in PLATFORM_TAGS and not LEVEL_RE.fullmatch(t)]
    if not grades:
        if others:
            tag = spelled[others[0]]
            if grade_kind(tag) == "range":
                return f"grade range {tag} - a series needs one grade (#KlasseN)"
            return f"{tag} is a school level, not a grade - a series needs #KlasseN (levels are not guessed)"
        return "no #KlasseN hashtag"
    if len(grades) > 1:
        return f"{len(grades)} grade hashtags ({', '.join(f'#Klasse{g}' for g in grades)})"
    if not subjects:
        return "no subject hashtag (#Fach)"
    return spelled[subjects[0]][1:], grades[0]


def series_name(subject: str, grade: int) -> str:
    return f"{subject} Klasse {grade}"


@dataclass
class SeriesReport:
    file: str
    videos: int  # data rows read (blank lines not counted)
    series: list[Series]
    not_sorted: list[NotSorted]
    warnings: list[CsvWarning]

    def to_json(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "videos": self.videos,
            "in_series": sum(len(s.videos) for s in self.series),
            "series": [
                {
                    "name": s.name,
                    "subject": s.subject,
                    "grade": s.grade,
                    "count": len(s.videos),
                    "videos": [v.to_json() for v in s.videos],
                }
                for s in self.series
            ],
            "not_sorted": [{**n.video.to_json(), "reason": n.reason} for n in self.not_sorted],
            "warnings": [{"line": w.line, "message": w.message} for w in self.warnings],
        }

    def lines(self) -> list[str]:
        in_series = sum(len(s.videos) for s in self.series)
        n = len(self.series)
        out = [
            f"{n} series in {self.file}: {in_series} of {self.videos} videos in a series, "
            f"{len(self.not_sorted)} not sorted, {self.videos - in_series - len(self.not_sorted)} skipped",
            "SERIES",
        ]

        def video(v: SeriesVideo) -> str:
            return f"line {v.line:>3}  {v.video_id or '-':<12}  {v.title}"

        for s in self.series:
            out.append(f"{s.name} ({len(s.videos)} videos)")
            out += [f"  {video(v)}" for v in s.videos]
        if not self.series:
            out.append(f"  (none - a series needs {MIN_VIDEOS} videos with the same #Fach and #KlasseN)")
        out.append("NOT SORTED")
        out += [f"  {video(n.video)}  - {n.reason}" for n in self.not_sorted] or ["  (none)"]
        out.append("WARNINGS")
        out += [f"  {'' if w.line is None else f'line {w.line}: '}{w.message}" for w in self.warnings] or ["  (none)"]
        return out


def find_series(path: str | Path) -> SeriesReport:
    """Group the CSV's videos into series by #Fach + #KlasseN. Series sorted by subject, then grade;
    videos (in a series and not sorted) in file order. Writes nothing."""
    try:
        table = read_table(path, REQUIRED, OPTIONAL)
    except CsvError as e:
        raise SeriesError(str(e)) from None
    warnings: list[CsvWarning] = []
    if table.ignored:
        warnings.append(CsvWarning(None, f"ignored columns: {', '.join(table.ignored)}"))
    groups: dict[tuple[str, int], list[SeriesVideo]] = {}
    subject_of: dict[tuple[str, int], str] = {}
    reasons: list[tuple[SeriesVideo, str]] = []
    seen: dict[str, int] = {}
    for r in table.rows:
        title = table.value(r, "title").strip()
        vid = table.value(r, "video_id").strip() or None
        problem = r.error
        if problem is None and not title:
            problem = "skipped - empty title"
        if problem is None and vid is not None and vid in seen:
            problem = f"skipped - video_id {vid} is already on line {seen[vid]} (would count twice)"
        if problem is not None:
            warnings.append(CsvWarning(r.line, problem, skipped_row=True))
            continue
        if vid is not None:
            seen[vid] = r.line
        v = SeriesVideo(r.line, vid, title)
        key = series_key(title)
        if isinstance(key, str):
            reasons.append((v, key))
            continue
        subject, grade = key
        k = (fold(subject), grade)
        subject_of.setdefault(k, subject)
        groups.setdefault(k, []).append(v)
    series = [
        Series(series_name(subject_of[k], k[1]), subject_of[k], k[1], vs)
        for k, vs in sorted(groups.items())
        if len(vs) >= MIN_VIDEOS
    ]
    for k, vs in groups.items():
        if len(vs) < MIN_VIDEOS:
            reasons += [(v, f"only video of {series_name(subject_of[k], k[1])}") for v in vs]
    not_sorted = [NotSorted(v, why) for v, why in sorted(reasons, key=lambda x: x[0].line)]
    return SeriesReport(str(path), len(table.rows), series, not_sorted, warnings)
