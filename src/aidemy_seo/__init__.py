"""aidemy_seo - YouTube SEO analytics and optimisation for educational channels.

Sibling of aidemy_pub. Pure-Python core (standard library only); live data needs the
optional ``requests`` extra and, for competitor research, a read-only YouTube API key.
"""

from .benchmark import title_patterns
from .descriptions import audit_description
from .keywords import Autocomplete, best_title_keyword, candidates, rank
from .learn import feature_lift
from .schedule import best_hours, best_slots, metric_coverage
from .titles import calibrate, optimize_title, score_title

__version__ = "0.1.0"
__all__ = [
    "Autocomplete",
    "audit_description",
    "best_hours",
    "best_slots",
    "best_title_keyword",
    "calibrate",
    "candidates",
    "feature_lift",
    "metric_coverage",
    "optimize_title",
    "rank",
    "score_title",
    "title_patterns",
]
