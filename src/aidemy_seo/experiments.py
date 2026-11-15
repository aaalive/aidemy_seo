"""Title template experiments: assign a template to each new video by hash, then see which wins.

`learn` looks back at titles that were picked by hand, so it also measures WHY they were
picked (a question title went on the topic you expected to do well) and WHEN (older videos
have had longer to collect views). Here the template ("arm") is drawn by a fixed hash before
upload, all arms are posted over the same weeks, and the report compares them on views per
day with a bootstrap confidence interval. Spec: specs/experiments.md. Standard library only.

    assign(ledger_path, experiment=..., key=..., keyword=...)   -> Assignment (written to the ledger)
    report(load_ledger(path), videos, experiment=...)           -> Report ("winner" / "no winner yet" /
                                                                   "insufficient data")
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import random
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, NoReturn

from .learn import HELPS_AT, HURTS_AT, VIEWS_PER_DAY, check_age_window, coverage_line, parse_time, videos_for_metric
from .titles import MAX_TITLE_LEN, build_title, title_tags

LEDGER_VERSION = 1
ARMS: dict[str, str] = {  # stable name -> template; every titles.TEMPLATES entry has exactly one name
    "question": "{x} – kannst du es erklären?",
    "einfach_musst": "{x} einfach erklärt – das musst du wissen!",
    "einfach_endlich": "{x} einfach erklärt – endlich verstanden!",
    "warum": "Warum {x}? Einfach erklärt",
    "musst_du_wissen": "{x}: Das musst du wissen!",
    "endlich": "{x} – endlich verstanden!",
}
HASH_HEX_DIGITS = 16  # the first 64 bits of the sha256 digest pick the arm
DEFAULT_MIN_AGE_DAYS = 7.0  # a Short's first days are noisy
DEFAULT_MIN_GROUP = 5
DEFAULT_CONFIDENCE = 0.95
BOOTSTRAP_RESAMPLES = 2000
WINNER, NO_WINNER_YET, INSUFFICIENT_DATA = "winner", "no winner yet", "insufficient data"
NOT_PUBLISHED = "not published yet or title changed"


class ExperimentError(ValueError):
    """Bad experiment input or a bad ledger. The message is one line, safe to show as is."""


# ---------------------------------------------------------------- deterministic assignment
def _clean(value: str, what: str) -> str:
    v = str(value).strip()
    if not v:
        raise ExperimentError(f"{what} must not be empty")
    return v


def _check_arms(arms: Iterable[str], *, known: Iterable[str] | None = None) -> list[str]:
    names = list(arms)
    if len(names) < 2:
        raise ExperimentError(f"an experiment needs at least 2 arms, got {len(names)}")
    twice = sorted({a for a in names if names.count(a) > 1})
    if twice:
        raise ExperimentError(f"arm listed twice: {', '.join(twice)}")
    if known is not None:
        allowed = set(known)
        unknown = [a for a in names if a not in allowed]
        if unknown:
            raise ExperimentError(f"unknown arm {', '.join(unknown)} - choose from {', '.join(ARMS)}")
    return names


def assign_arm(experiment: str, key: str, arms: Iterable[str]) -> str:
    """The arm for `key` - depends only on the experiment name, the key and the SET of arms.

    sha256, not hash(): Python salts hash() per process (PYTHONHASHSEED). json.dumps of the
    pair, not "a:b": ("a:b", "c") and ("a", "b:c") must not collide."""
    names = sorted(_check_arms(arms))
    pair = [_clean(experiment, "experiment name"), _clean(key, "key")]
    digest = hashlib.sha256(json.dumps(pair, ensure_ascii=False).encode("utf-8")).hexdigest()
    return names[int(digest[:HASH_HEX_DIGITS], 16) % len(names)]


# ---------------------------------------------------------------- JSON ledger
def empty_ledger() -> dict[str, Any]:
    return {"version": LEDGER_VERSION, "experiments": {}}


def _validate(data: Any, path: Path) -> dict[str, Any]:
    def bad(why: str) -> NoReturn:
        raise ExperimentError(f"ledger {path}: {why} - the file was not changed")

    if not isinstance(data, dict):
        bad("the top level must be a JSON object")
    if data.get("version") != LEDGER_VERSION:
        bad(f"version {data.get('version')!r} is not supported (expected {LEDGER_VERSION})")
    if not isinstance(data.get("experiments"), dict):
        bad('"experiments" must be an object')
    for name, exp in data["experiments"].items():
        if not isinstance(exp, dict) or not all(isinstance(exp.get(f), dict) for f in ("arms", "assignments")):
            bad(f'experiment {name!r} needs "arms" and "assignments" objects')
        if len(exp["arms"]) < 2 or not all(isinstance(t, str) and "{x}" in t for t in exp["arms"].values()):
            bad(f"experiment {name!r} needs at least 2 arms, each a template with {{x}}")
        for key, entry in exp["assignments"].items():
            ok = isinstance(entry, dict) and entry.get("arm") in exp["arms"] and isinstance(entry.get("title"), str)
            if not ok:
                bad(f"assignment {key!r} of {name!r} needs an arm of that experiment and a title")
    return data


def load_ledger(path: str | Path, *, must_exist: bool = False) -> dict[str, Any]:
    """The ledger at `path`; a missing file is an empty ledger (unless `must_exist`)."""
    p = Path(path)
    if not p.exists():
        if must_exist:
            raise ExperimentError(f"ledger {p} does not exist - create it with `experiment assign`")
        return empty_ledger()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ExperimentError(f"ledger {p} is not valid JSON ({e}) - the file was not changed") from None
    return _validate(data, p)


def save_ledger(path: str | Path, ledger: dict[str, Any]) -> None:
    """Atomic: write a temp file next to the ledger, then os.replace - a crash never leaves half a file.
    An existing ledger keeps its file mode; a new one is private to the user (mkstemp: 0600)."""
    p = Path(path)
    text = json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if p.exists():
            shutil.copymode(p, tmp)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _norm_title(title: object) -> str:
    return " ".join(str(title).split())  # whitespace collapsed, case kept


def _iso(now: datetime | None) -> str:
    t = now or datetime.now(timezone.utc)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).isoformat(timespec="seconds")


@dataclass
class Assignment:
    experiment: str
    key: str
    arm: str
    template: str
    keyword: str
    title: str
    assigned_at: str
    already_assigned: bool = False
    warnings: list[str] = field(default_factory=list)


def assign(
    ledger_path: str | Path,
    *,
    experiment: str,
    key: str,
    keyword: str,
    subject: str = "",
    grade: str = "",
    arms: Sequence[str] | None = None,
    now: datetime | None = None,
) -> Assignment:
    """Assign `key` to an arm of `experiment` and record it. Idempotent: an existing key returns its
    stored entry unchanged. A refused assign (error) never touches the ledger file."""
    name, k = _clean(experiment, "experiment name"), _clean(key, "key")
    wanted = _check_arms(arms, known=ARMS) if arms else None
    ledger = load_ledger(ledger_path)
    exp = ledger["experiments"].get(name)
    stamp = _iso(now)
    if exp is None:
        exp = {"created_at": stamp, "arms": {a: ARMS[a] for a in wanted or ARMS}, "assignments": {}}
    elif wanted is not None and set(wanted) != set(exp["arms"]):
        raise ExperimentError(
            f"experiment {name!r} has arms {', '.join(sorted(exp['arms']))} - arms can't change once it has "
            f"started (it would reshuffle {len(exp['assignments'])} earlier assignment(s)); start a new experiment"
        )
    stored = exp["assignments"].get(k)
    if stored is not None:
        return Assignment(
            name,
            k,
            stored["arm"],
            exp["arms"][stored["arm"]],
            str(stored.get("keyword", "")),
            stored["title"],
            str(stored.get("assigned_at", "")),
            already_assigned=True,
        )
    kw = _clean(keyword, "keyword")
    arm = assign_arm(name, k, exp["arms"])
    template = exp["arms"][arm]
    title = build_title(kw, template, title_tags(subject, grade))
    clash = next((o for o, e in exp["assignments"].items() if _norm_title(e["title"]) == _norm_title(title)), None)
    if clash is not None:
        raise ExperimentError(
            f"title {title!r} is already used by key {clash!r} - the report matches videos by title, "
            "so titles in one experiment must differ (use a more specific keyword)"
        )
    warnings = []  # the arm is NEVER re-drawn: that would bring back the bias the experiment removes
    if len(title) > MAX_TITLE_LEN:
        warnings.append(f"title is {len(title)} characters (over {MAX_TITLE_LEN}) - arm kept on purpose")
    if ":" in kw and "{x}:" in template:
        warnings.append("title has two ':' (one from the keyword, one from the template) - arm kept on purpose")
    exp["assignments"][k] = {"arm": arm, "keyword": kw, "title": title, "assigned_at": stamp}
    ledger["experiments"][name] = exp
    save_ledger(ledger_path, ledger)
    return Assignment(name, k, arm, template, kw, title, stamp, warnings=warnings)


# ---------------------------------------------------------------- confidence interval
def _ratio(a: float, b: float) -> float:
    """a / b; with b == 0 the ratio is infinite (a > 0) or 1.0 (both 0) - never a crash."""
    if b == 0:
        return math.inf if a > 0 else 1.0
    return a / b


def seeded_rng(seed: int) -> random.Random:
    """The one random source of the report: seeded so the same data always gives the same interval.
    Statistics only - nothing secret depends on it (that is what S311 warns about)."""
    return random.Random(seed)  # noqa: S311 - reproducible resampling must be seedable; `secrets` can't be


def bootstrap_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    level: float = DEFAULT_CONFIDENCE,
    rng: random.Random | None = None,
    seed: int = 0,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> tuple[float, float]:
    """Percentile-bootstrap interval for median(a) / median(b). Deterministic for a given seed/rng."""
    if not a or not b:
        raise ValueError("both samples need at least one value")
    if not 0 < level < 1:
        raise ValueError(f"level must be between 0 and 1, got {level}")
    rng = rng or seeded_rng(seed)
    ratios = sorted(
        _ratio(median(rng.choices(a, k=len(a))), median(rng.choices(b, k=len(b)))) for _ in range(resamples)
    )
    alpha = 1 - level
    return ratios[math.floor(resamples * alpha / 2)], ratios[math.ceil(resamples * (1 - alpha / 2)) - 1]


# ---------------------------------------------------------------- report
@dataclass
class ArmResult:
    arm: str
    template: str
    assigned: int
    published: int
    used: int
    median: float | None
    lift: float | None  # arm median / median of all other arms' videos; None = not enough data
    verdict: str  # helps / hurts / no clear effect / not enough data - descriptive, never names a winner


@dataclass
class Comparison:
    arm: str  # the leader
    vs: str
    ratio: float  # median(leader) / median(vs)
    level: float  # Bonferroni-adjusted confidence of this interval
    ci_low: float
    ci_high: float


def _fmt(x: float | None) -> str:
    if x is None:
        return "-"
    return "inf" if math.isinf(x) else f"{x:g}"


def _json_safe(o: Any) -> Any:
    """JSON has no Infinity: infinite floats become "inf" / "-inf"."""
    if isinstance(o, float) and math.isinf(o):
        return "inf" if o > 0 else "-inf"
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_json_safe(v) for v in o]
    return o


@dataclass
class Report:
    experiment: str
    metric: str
    min_age: float | None
    max_age: float | None
    now: str
    confidence: float
    seed: int
    min_group: int
    verdict: str  # winner / no winner yet / insufficient data
    winner: str | None
    leader: str | None
    comparisons: list[Comparison]
    arms: list[ArmResult]
    unmatched: list[dict]
    assigned: int
    used: int
    left_out: dict[str, int]

    def to_json(self) -> dict[str, Any]:
        return _json_safe(asdict(self))

    def lines(self) -> list[str]:
        out = [
            coverage_line(
                self.assigned,
                self.used,
                self.left_out,
                metric=self.metric,
                now=parse_time(self.now),
                min_age=self.min_age,
                max_age=self.max_age,
                what="assigned videos",
            )
        ]

        def ci(c: Comparison) -> str:
            return f"{c.vs}: ratio {_fmt(c.ratio)}, {c.level * 100:g}% CI {_fmt(c.ci_low)}-{_fmt(c.ci_high)}"

        if self.verdict == WINNER:
            beaten = "; ".join(map(ci, self.comparisons))
            out.append(f"verdict: WINNER = {self.winner} - beats every other arm ({beaten})")
            out.append(
                "  (only trust this if you fixed the number of videos per arm in advance - "
                "stopping at the first 'winner' overstates the confidence)"
            )
        elif self.verdict == NO_WINNER_YET:
            open_ = [c for c in self.comparisons if not c.ci_low > 1.0]
            out.append(
                f"verdict: no winner yet - leader {self.leader} has not yet beaten "
                f"{', '.join(c.vs for c in open_)} ({'; '.join(map(ci, open_))}); keep posting"
            )
        else:
            short = [a for a in self.arms if a.used < self.min_group]
            need = ", ".join(f"{a.arm} needs {self.min_group - a.used} more" for a in short)
            out.append(f"verdict: insufficient data - need {self.min_group} used videos per arm: {need}")
        out += ["", f"{'arm':<16} {'assigned':>8} {'published':>9} {'used':>4} {'median':>8} {'lift':>6}  note"]
        for a in self.arms:
            counts = f"{a.assigned:>8} {a.published:>9} {a.used:>4}"
            out.append(f"{a.arm:<16} {counts} {_fmt(a.median):>8} {_fmt(a.lift):>6}  {a.verdict}")
        if self.unmatched:
            out += ["", "not counted:"]
            out += [f"  {u['key']} ({u['arm']}): {u['reason']} - {u['title']}" for u in self.unmatched]
        return out


def _lift_verdict(lift: float) -> str:
    return "helps" if lift >= HELPS_AT else "hurts" if lift <= HURTS_AT else "no clear effect"


def report(
    ledger: dict[str, Any],
    videos: list[dict],
    *,
    experiment: str,
    metric: str = VIEWS_PER_DAY,
    now: datetime | None = None,
    min_age: float | None = DEFAULT_MIN_AGE_DAYS,
    max_age: float | None = None,
    min_group: int = DEFAULT_MIN_GROUP,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = 0,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Report:
    """Compare the arms of `experiment` on `metric` (default: views per day, videos >= 7 days old)."""
    exps = ledger["experiments"]
    if experiment not in exps:
        have = ", ".join(sorted(exps)) or "(none)"
        raise ExperimentError(f"no experiment {experiment!r} in the ledger - it has: {have}")
    if not (math.isfinite(confidence) and 0 < confidence < 1):
        raise ExperimentError(f"confidence must be between 0 and 1 (e.g. 0.95), got {confidence}")
    if min_group < 1:
        raise ExperimentError(f"min_group must be at least 1, got {min_group}")
    try:
        check_age_window(min_age, max_age)
    except ValueError as e:
        raise ExperimentError(str(e)) from None
    stamp = _iso(now)
    at = parse_time(stamp) or datetime.now(timezone.utc)
    exp = exps[experiment]
    names = sorted(exp["arms"])

    by_title: dict[str, list[dict]] = {}
    for v in videos:  # stats videos that are not in the ledger are simply never looked up
        by_title.setdefault(_norm_title(v.get("title", "")), []).append(v)
    matched, unmatched = [], []
    for key in sorted(exp["assignments"]):
        entry = exp["assignments"][key]
        hits = by_title.get(_norm_title(entry["title"]), [])
        if len(hits) == 1:
            matched.append(dict(hits[0], experiment_arm=entry["arm"], experiment_key=key))
        else:
            reason = NOT_PUBLISHED if not hits else f"title matches {len(hits)} videos in the stats file"
            unmatched.append({"key": key, "arm": entry["arm"], "title": entry["title"], "reason": reason})
    used, age_left = videos_for_metric(matched, metric=metric, now=at, min_age=min_age, max_age=max_age)
    left_out: dict[str, int] = {}
    for u in unmatched:
        left_out[u["reason"]] = left_out.get(u["reason"], 0) + 1
    left_out.update(age_left)

    values = {a: [float(r[metric]) for r in used if r["experiment_arm"] == a] for a in names}
    arms = []
    for a in names:
        mine = values[a]
        rest = [x for b in names if b != a for x in values[b]]
        lift: float | None = None
        verdict = f"not enough data (need {min_group} per arm)"
        if len(mine) >= min_group and len(rest) >= min_group:
            lift = round(_ratio(median(mine), median(rest)), 2)
            verdict = _lift_verdict(lift)
        arms.append(
            ArmResult(
                a,
                exp["arms"][a],
                assigned=sum(1 for e in exp["assignments"].values() if e["arm"] == a),
                published=sum(1 for m in matched if m["experiment_arm"] == a),
                used=len(mine),
                median=round(median(mine), 2) if mine else None,
                lift=lift,
                verdict=verdict,
            )
        )

    comparisons: list[Comparison] = []
    leader = winner = None
    if any(len(values[a]) < min_group for a in names):
        overall = INSUFFICIENT_DATA
    else:
        leader = min(names, key=lambda a: (-median(values[a]), a))  # a tie goes to the first name
        others = [a for a in names if a != leader]
        level = 1 - (1 - confidence) / len(others)  # Bonferroni: k-1 comparisons
        rng = seeded_rng(seed)  # one rng per report, comparisons in arm-name order
        lows = []
        for o in others:
            lo, hi = bootstrap_ci(values[leader], values[o], level=level, rng=rng, resamples=resamples)
            lows.append(lo)
            ratio = _ratio(median(values[leader]), median(values[o]))
            comparisons.append(Comparison(leader, o, round(ratio, 3), round(level, 4), round(lo, 3), round(hi, 3)))
        if all(lo > 1.0 for lo in lows):  # decided on the unrounded bounds
            overall, winner = WINNER, leader
        else:
            overall = NO_WINNER_YET
    return Report(
        experiment,
        metric,
        min_age,
        max_age,
        stamp,
        confidence,
        seed,
        min_group,
        overall,
        winner,
        leader,
        comparisons,
        arms,
        unmatched,
        assigned=len(exp["assignments"]),
        used=len(used),
        left_out=left_out,
    )
