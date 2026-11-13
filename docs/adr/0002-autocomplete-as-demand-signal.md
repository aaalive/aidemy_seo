# 0002 - YouTube autocomplete as the keyword-demand signal

- Status: accepted
- Date: 2026-11-13

## Context
Titles led by curriculum words nobody searches ("Konfigurationsisomerie", vidIQ 62) scored
far below titles with searched words ("Proteine & Isomerie", vidIQ 80). Real search volume
needs paid tools (vidIQ, Google Ads); the Data API has no search volume.

## Options
1. Paid keyword API.
2. Data API search.list result counts (100 units per call, measures supply not demand).
3. YouTube autocomplete: count of completions starting with the phrase (free, no quota).

## Decision
Option 3 as a 0-10 demand signal, -1 when unknown. Candidates come only from the lesson
itself so a popular but unrelated word never leads a title.

## Consequences
+ Free, no quota, runs on every upload.
- Ordinal signal, not volume; unofficial endpoint (fail-open to -1).
