"""Description audit - the checks YouTube SEO tools apply to the text under a video."""
from __future__ import annotations

from dataclasses import dataclass, field

from .text import URL_RE, fold, hashtags, words


@dataclass
class DescriptionAudit:
    score: float
    checks: dict = field(default_factory=dict)

    @property
    def issues(self) -> list[str]:
        return [f"{k}: {v[2]}" for k, v in self.checks.items() if not v[0]]


def audit_description(description: str, *, keywords: list[str] = (), link_hint: str = "") -> DescriptionAudit:
    d = description or ""
    head = d[:200]
    head_words = set(words(head))
    checks: dict = {}

    def add(name, ok, weight, note):
        checks[name] = (bool(ok), weight, note)

    kws = [k for k in keywords if k]
    hits = [k for k in kws if all(w in head_words for w in words(k))]
    add("keywords_first_200", (len(hits) >= min(2, len(kws))) if kws else True, 25,
        f"searched keywords in the first 200 characters (found: {hits or 'none'})")
    first_lines = "\n".join(d.splitlines()[:4])
    urls = URL_RE.findall(first_lines)
    add("link_near_top", bool(urls) and (not link_hint or any(link_hint in u for u in urls)), 20,
        "the product/PDF link within the first 4 lines")
    add("specific_link", not any("/autor/" in u for u in URL_RE.findall(d)) or not link_hint, 10,
        "a direct product link, not only the author page")
    n_tags = len(hashtags(d))
    add("hashtags", 3 <= n_tags <= 5, 10, f"3-5 hashtags ({n_tags} found)")
    add("length", 250 <= len(d) <= 5000, 15, f"{len(d)} characters (aim 250+)")
    add("call_to_action", any(w in fold(d) for w in ("abonn", "kommentar", "subscribe", "comment")), 10,
        "asks to subscribe or comment")
    add("chapters_or_structure", d.count("\n") >= 4, 10, "several short paragraphs / lines")
    total = sum(w for _o, w, _n in checks.values())
    got = sum(w for o, w, _n in checks.values() if o)
    return DescriptionAudit(round(100.0 * got / total, 1), checks)
