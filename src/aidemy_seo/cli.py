"""Command line: `aidemy-seo <command> ...` (add --json right after `aidemy-seo` for machine-readable output).

One small handler per command; each returns (json_payload, text_lines).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

Result = tuple[Any, list[str]]


def _default(o: object) -> object:
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    return str(o)


def _keywords(a: argparse.Namespace) -> Result:
    from .keywords import Autocomplete, best_title_keyword, candidates, rank

    ac = Autocomplete(lang=a.lang, region=a.region)
    ranked = rank(candidates(a.topic, short_name=a.short_name, key_terms=a.term), ac.demand)
    best = best_title_keyword(ranked)
    lines = [f"{'demand':>6}  {'score':>5}  keyword"]
    lines += [
        f"{('?' if r.demand < 0 else r.demand):>6}  {r.score:>5}  {r.phrase}{'  (main topic)' if r.main else ''}"
        for r in ranked
    ]
    lines.append(f"\nbest title keyword: {best or '(no lookup succeeded - offline?)'}")
    return {"keywords": ranked, "best": best}, lines


def _title(a: argparse.Namespace) -> Result:
    from .titles import optimize_title, score_title

    if a.generate:
        ranked = optimize_title(a.text, subject=a.subject, grade=a.grade)
        return ranked, [f"{r.total:5.1f}  {r.title}" for r in ranked]
    sc = score_title(a.text, a.keyword)
    return sc, [f"score {sc.total}/100  {sc.title}"] + [f"  - {i}" for i in sc.issues]


def _description(a: argparse.Namespace) -> Result:
    from .descriptions import audit_description

    text = sys.stdin.read() if a.path == "-" else Path(a.path).read_text(encoding="utf-8")
    audit = audit_description(text, keywords=a.keyword, link_hint=a.link_hint)
    return audit, [f"score {audit.score}/100"] + [f"  - {i}" for i in audit.issues]


def _schedule(a: argparse.Namespace) -> Result:
    from .aidemy_pub import load_channel_videos
    from .schedule import best_slots, metric_coverage

    videos = load_channel_videos(a.stats_json)
    slots = best_slots(videos, tz=a.tz, metric=a.metric, min_videos=a.min_videos, fallback_metric=a.fallback_metric)
    have, total = metric_coverage(videos, a.metric)
    used = f"{have} of {total} Shorts have {a.metric}" + (
        f"; the rest use {a.fallback_metric} (older videos look better)"
        if a.fallback_metric
        else "; the rest are left out"
    )
    lines = [used, f"{'slot':<10} {'videos':>6} {'median':>8}  note"]
    lines += [
        f"{x.label:<10} {x.videos:>6} {x.median_views:>8}  {'' if x.enough_data else 'not enough data'}" for x in slots
    ]
    return slots, lines


def _learn(a: argparse.Namespace) -> Result:
    from .aidemy_pub import load_channel_videos
    from .learn import feature_lift

    findings = feature_lift(load_channel_videos(a.stats_json), metric=a.metric, min_group=a.min_group)
    return findings, [
        f"{f.feature:<18} with {f.with_n:>3} ({f.with_median:>7}) without {f.without_n:>3} "
        f"({f.without_median:>7})  {f.verdict}"
        for f in findings
    ]


def _benchmark(a: argparse.Namespace) -> Result:
    from .benchmark import title_patterns
    from .youtube_api import YouTubeAPI

    vids = YouTubeAPI().top_videos(a.keyword, n=a.n, shorts=a.shorts, region=a.region, lang=a.lang)
    pat = title_patterns([(v.title, v.views) for v in vids], a.keyword)
    lines = [*pat.summary(), ""] + [f"{v.views:>10,}  {v.title}  ({v.channel})" for v in vids[:15]]
    return {"patterns": pat, "videos": vids}, lines


def _calibrate(a: argparse.Namespace) -> Result:
    from .titles import calibrate

    rows = []
    for line in Path(a.csv_path).read_text(encoding="utf-8").splitlines():
        if ";" in line and not line.lower().startswith("title;"):
            title, score = line.rsplit(";", 1)
            rows.append((title.strip(), float(score)))
    cal = calibrate(rows)
    by_shape: dict[str, float] = cal["by_shape"]
    return cal, [f"{k:<18} mean {v:>5}  (n={cal['n'][k]})" for k, v in sorted(by_shape.items(), key=lambda x: -x[1])]


def _lesson(a: argparse.Namespace) -> Result:
    from .aidemy_pub import suggest_for_lesson

    sug = suggest_for_lesson(json.loads(Path(a.bundle_json).read_text(encoding="utf-8")), top=a.top)
    return sug, [f"keyword: {sug['keyword']}", ""] + [f"{t['score']:5.1f}  {t['title']}" for t in sug["titles"]]


def _channels(a: argparse.Namespace) -> Result:
    from .competitors import analyse
    from .youtube_api import Video, YouTubeAPI

    vids: dict[str, list[Video]] = {}
    info: dict[str, dict] = {}
    if a.load:
        raw = json.loads(Path(a.load).read_text(encoding="utf-8"))
        for c, d in raw.items():
            vids[c] = [Video(**v) for v in d["videos"]]
            info[c] = d.get("info") or {}
    else:
        refs = list(a.refs)
        if a.file:
            refs += [
                ln.strip()
                for ln in Path(a.file).read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
        api = YouTubeAPI()
        if a.discover:
            refs += [c["id"] for c in api.find_channels(a.discover)]
        missing = []
        for r in dict.fromkeys(refs):
            try:
                chinfo, vs = api.channel_videos(r, limit=a.per_channel)
            except Exception as e:  # noqa: BLE001 - one bad channel must not stop the others
                missing.append(f"{r} ({e})")
                continue
            if not chinfo:
                missing.append(r)
                continue
            name = chinfo["title"] or r
            vids[name], info[name] = vs, chinfo
        if missing:
            print("not found / skipped: " + ", ".join(missing), file=sys.stderr)
        if a.save:
            payload = {c: {"info": info[c], "videos": [asdict(v) for v in vs]} for c, vs in vids.items()}
            Path(a.save).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    res = analyse(vids, info, max_age_days=a.max_age_days, shorts_only=not a.all_videos)
    lines = [
        f"{res['videos']} videos from {res['channels']} channels "
        "(score = views / that channel's own median; 1.0 = usual, 2.0 = twice as good)",
        "",
        "BEST POSTING SLOTS (Berlin time)",
        f"{'slot':<10} {'videos':>6} {'median':>7}  note",
    ]
    lines += [
        f"{x.label:<10} {x.videos:>6} {x.median_views:>7}  {'' if x.enough_data else 'not enough data'}"
        for x in res["slots"][:15]
    ]
    lines += ["", "BEST HOURS (any weekday)"]
    lines += [f"{h:02d}:00  median {m}  ({n} videos)" for h, m, n in res["hours"][:8]]
    lines += ["", "TITLE STYLES"]
    lines += [
        f"{f.feature:<18} with {f.with_n:>4} ({f.with_median:>5}) without {f.without_n:>4} "
        f"({f.without_median:>5})  {f.verdict}"
        for f in res["title_styles"]
    ]
    lines += ["", "CHANNELS"]
    lines += [
        f"{s.title or s.ref:<30} {s.subscribers:>9,} subs  {s.videos_used:>4} shorts used  "
        f"median {s.median_views:>9,.0f} views  posts mostly at {s.top_hours}"
        for s in res["summaries"]
    ]
    return res, lines


HANDLERS: dict[str, Callable[[argparse.Namespace], Result]] = {
    "keywords": _keywords,
    "title": _title,
    "description": _description,
    "schedule": _schedule,
    "learn": _learn,
    "benchmark": _benchmark,
    "calibrate": _calibrate,
    "lesson": _lesson,
    "channels": _channels,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aidemy-seo", description="YouTube SEO analytics and optimisation.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keywords", help="rank keyword candidates of a topic by real YouTube search demand")
    k.add_argument("topic")
    k.add_argument("--short-name", default="")
    k.add_argument("--term", action="append", default=[], help="extra key term (repeatable)")
    k.add_argument("--lang", default="de")
    k.add_argument("--region", default="DE")

    t = sub.add_parser("title", help="score a title, or generate ranked candidates for a keyword")
    t.add_argument("text", help="a title to score, or the keyword with --generate")
    t.add_argument("--keyword", default="", help="the searched keyword the title should lead with")
    t.add_argument("--generate", action="store_true")
    t.add_argument("--subject", default="")
    t.add_argument("--grade", default="")

    d = sub.add_parser("description", help="audit a description (file path or '-' for stdin)")
    d.add_argument("path")
    d.add_argument("--keyword", action="append", default=[])
    d.add_argument("--link-hint", default="")

    s = sub.add_parser("schedule", help="best posting slots from a stats JSON (aidemy_pub state/youtube/stats.json)")
    s.add_argument("stats_json")
    s.add_argument("--metric", default="views_24h")
    s.add_argument(
        "--fallback-metric",
        default=None,
        help="use this metric for videos without --metric (e.g. views); off by default - it favours older videos",
    )
    s.add_argument("--min-videos", type=int, default=3)
    s.add_argument("--tz", default="Europe/Berlin")

    lr = sub.add_parser("learn", help="which title features go with more views on your own channel")
    lr.add_argument("stats_json")
    lr.add_argument("--metric", default="views")
    lr.add_argument("--min-group", type=int, default=5)

    b = sub.add_parser("benchmark", help="title patterns of the top videos for a keyword (needs YOUTUBE_API_KEY)")
    b.add_argument("keyword")
    b.add_argument("--n", type=int, default=25)
    b.add_argument("--shorts", action="store_true")
    b.add_argument("--region", default="DE")
    b.add_argument("--lang", default="de")

    c = sub.add_parser("calibrate", help="which title shapes an external tool scores best (CSV: title;score)")
    c.add_argument("csv_path")

    le = sub.add_parser("lesson", help="keyword + title suggestions for an aidemy_pub bundle.json")
    le.add_argument("bundle_json")
    le.add_argument("--top", type=int, default=5)

    ch = sub.add_parser(
        "channels",
        help="posting times + title styles across OTHER channels in your area (needs YOUTUBE_API_KEY, "
        "~5 units per channel)",
    )
    ch.add_argument("refs", nargs="*", help="@handles, channel ids or URLs")
    ch.add_argument("--file", help="a text file with one channel per line (# comments allowed)")
    ch.add_argument("--discover", default="", help="also add channels YouTube search returns for this topic")
    ch.add_argument("--per-channel", type=int, default=200, help="latest uploads per channel")
    ch.add_argument("--max-age-days", type=float, default=180)
    ch.add_argument("--all-videos", action="store_true", help="not only Shorts")
    ch.add_argument("--save", help="write the raw video data to this JSON file (re-analyse later offline)")
    ch.add_argument("--load", help="analyse a file written by --save instead of calling the API")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    payload, lines = HANDLERS[a.cmd](a)
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_default))
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
