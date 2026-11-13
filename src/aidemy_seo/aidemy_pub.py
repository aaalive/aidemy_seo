"""Adapter for the sibling project aidemy_pub (the lesson + video pipeline).

aidemy_pub keeps the channel snapshot in ``state/youtube/stats.json`` (written every 3 h by
its youtube-stats job) and one ``bundle.json`` per lesson. These helpers read them, so
aidemy_seo never needs its own YouTube login for the analytics part.
"""
from __future__ import annotations

import json
from pathlib import Path

from .keywords import Autocomplete, best_title_keyword, candidates, rank
from .titles import optimize_title


def load_channel_videos(stats_json: str | Path) -> list[dict]:
    data = json.loads(Path(stats_json).read_text(encoding="utf-8"))
    return list(data.get("videos") or [])


def lesson_keyword_inputs(bundle: dict) -> dict:
    meta = bundle.get("meta") or {}
    terms = [k.get("term") if isinstance(k, dict) else k for k in bundle.get("keyTerms") or []]
    return {"topic": meta.get("topic", ""), "short_name": (bundle.get("overview") or {}).get("topicShortName", ""),
            "key_terms": [t for t in terms if t], "subject": meta.get("subject", ""), "grade": meta.get("grade", "")}


def suggest_for_lesson(bundle: dict, *, autocomplete: Autocomplete | None = None, top: int = 5) -> dict:
    """Keyword ranking + ranked title candidates for one aidemy_pub lesson bundle."""
    inp = lesson_keyword_inputs(bundle)
    ac = autocomplete or Autocomplete()
    cands = candidates(inp["topic"], short_name=inp["short_name"], key_terms=inp["key_terms"])
    ranked = rank(cands, ac.demand)
    kw = best_title_keyword(ranked) or (cands[0][0] if cands else inp["topic"])
    titles = optimize_title(kw, subject=inp["subject"], grade=inp["grade"])
    return {"keyword": kw,
            "keywords": [{"phrase": k.phrase, "demand": k.demand, "main": k.main, "score": k.score} for k in ranked],
            "titles": [{"title": t.title, "score": t.total, "issues": t.issues} for t in titles[:top]]}
