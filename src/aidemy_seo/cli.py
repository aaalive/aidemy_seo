"""Command line: `aidemy-seo <command> ...` (add --json for machine-readable output)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path


def _out(obj, as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=lambda o: asdict(o) if is_dataclass(o) else str(o)))
    else:
        print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
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

    l2 = sub.add_parser("lesson", help="keyword + title suggestions for an aidemy_pub bundle.json")
    l2.add_argument("bundle_json")
    l2.add_argument("--top", type=int, default=5)

    a = p.parse_args(argv)

    if a.cmd == "keywords":
        from .keywords import Autocomplete, best_title_keyword, candidates, rank
        ac = Autocomplete(lang=a.lang, region=a.region)
        ranked = rank(candidates(a.topic, short_name=a.short_name, key_terms=a.term), ac.demand)
        best = best_title_keyword(ranked)
        lines = [f"{'demand':>6}  {'score':>5}  keyword"] + [
            f"{('?' if r.demand < 0 else r.demand):>6}  {r.score:>5}  {r.phrase}{'  (main topic)' if r.main else ''}"
            for r in ranked] + [f"\nbest title keyword: {best or '(no lookup succeeded - offline?)'}"]
        _out({"keywords": ranked, "best": best}, a.json, lines)
    elif a.cmd == "title":
        from .titles import optimize_title, score_title
        if a.generate:
            res = optimize_title(a.text, subject=a.subject, grade=a.grade)
            _out(res, a.json, [f"{r.total:5.1f}  {r.title}" for r in res])
        else:
            r = score_title(a.text, a.keyword)
            _out(r, a.json, [f"score {r.total}/100  {r.title}"] + [f"  - {i}" for i in r.issues])
    elif a.cmd == "description":
        from .descriptions import audit_description
        text = sys.stdin.read() if a.path == "-" else Path(a.path).read_text(encoding="utf-8")
        r = audit_description(text, keywords=a.keyword, link_hint=a.link_hint)
        _out(r, a.json, [f"score {r.score}/100"] + [f"  - {i}" for i in r.issues])
    elif a.cmd == "schedule":
        from .aidemy_pub import load_channel_videos
        from .schedule import best_slots
        slots = best_slots(load_channel_videos(a.stats_json), tz=a.tz, metric=a.metric, min_videos=a.min_videos)
        lines = [f"{'slot':<10} {'videos':>6} {'median':>8}  note"] + [
            f"{x.label:<10} {x.videos:>6} {x.median_views:>8}  {'' if x.enough_data else 'not enough data'}"
            for x in slots]
        _out(slots, a.json, lines)
    elif a.cmd == "learn":
        from .aidemy_pub import load_channel_videos
        from .learn import feature_lift
        res = feature_lift(load_channel_videos(a.stats_json), metric=a.metric, min_group=a.min_group)
        _out(res, a.json, [f"{f.feature:<18} with {f.with_n:>3} ({f.with_median:>7}) without {f.without_n:>3} "
                           f"({f.without_median:>7})  {f.verdict}" for f in res])
    elif a.cmd == "benchmark":
        from .benchmark import title_patterns
        from .youtube_api import YouTubeAPI
        vids = YouTubeAPI().top_videos(a.keyword, n=a.n, shorts=a.shorts, region=a.region, lang=a.lang)
        pat = title_patterns([(v.title, v.views) for v in vids], a.keyword)
        _out({"patterns": pat, "videos": vids}, a.json,
             pat.summary() + [""] + [f"{v.views:>10,}  {v.title}  ({v.channel})" for v in vids[:15]])
    elif a.cmd == "calibrate":
        from .titles import calibrate
        rows = []
        for line in Path(a.csv_path).read_text(encoding="utf-8").splitlines():
            if ";" in line and not line.lower().startswith("title;"):
                title, score = line.rsplit(";", 1)
                rows.append((title.strip(), float(score)))
        res = calibrate(rows)
        _out(res, a.json, [f"{k:<18} mean {v:>5}  (n={res['n'][k]})" for k, v in
                           sorted(res["by_shape"].items(), key=lambda x: -x[1])])
    elif a.cmd == "lesson":
        from .aidemy_pub import suggest_for_lesson
        res = suggest_for_lesson(json.loads(Path(a.bundle_json).read_text(encoding="utf-8")), top=a.top)
        lines = [f"keyword: {res['keyword']}", ""] + [f"{t['score']:5.1f}  {t['title']}" for t in res["titles"]]
        _out(res, a.json, lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
