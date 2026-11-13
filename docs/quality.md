# Quality baseline

Track these numbers over time; a PR should never make them worse.

| Date | Tests | Coverage | Mutation score (killed / killed+survived) | Notes |
|---|---|---|---|---|
| 2026-11-13 | 36 (+2 live) | 93.7% (gate 85%) | 55% (1585 / 2863) | first run |

## Surviving mutants by module (2026-11-13)
| Module | Survived | Priority |
|---|---|---|
| cli | 324 | low - mostly help/output text |
| youtube_api | 249 | low/medium - request parameter strings; pinned by `-m live` |
| titles | 169 | **high** - scoring weights and thresholds not pinned by tests |
| keywords | 123 | **high** - candidate filtering edge cases |
| descriptions | 88 | medium |
| schedule | 80 | medium |
| competitors | 77 | medium |
| aidemy_pub | 66 | medium |
| benchmark | 47 | low |
| learn | 42 | medium - verdict thresholds |
| text | 13 | low |

Next: raise titles + keywords first (`mutmut results`, `mutmut show <id>` per survivor).
