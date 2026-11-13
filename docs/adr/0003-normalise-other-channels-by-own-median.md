# 0003 - Compare other channels by views relative to their own median

- Status: accepted
- Date: 2026-11-13

## Context
Our channel has 78 videos - too little for reliable posting-time and title-style findings.
Other channels have far more data but very different sizes, and public data has no
"views after 24 h".

## Options
1. Raw views - dominated by the biggest channel.
2. Views per day since upload - still dominated by size, biased by age.
3. Views / that channel's median over the same window (7-180 days, Shorts only).

## Decision
Option 3. 1.0 = usual for that channel. Pooled across channels, analysed with the same
`best_slots()` / `feature_lift()` as our own data, with a higher evidence bar (10+ per side).

## Consequences
+ Small and big channels count equally; one viral channel can't skew the result.
- Window choice matters; channels with < 5 usable Shorts are skipped.
