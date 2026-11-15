# 0006 - Batch CSV analysis: its own fixed rubric, topic words only, exact duplicates

- Status: accepted
- Date: 2026-11-15

## Context
`aidemy-seo analyze-batch` scores many videos from a CSV (specs/batch-analysis.md). The
requested rubric: title 40-65 characters (30 points), words shared by title and description
(30), 5-15 unique `|`-separated tags with a total under 500 characters. The tag points were
not given. `score_title()` already exists with a different length rule (35-60 characters
without hashtags, 66 total) and other checks (hook, keyword first, listing label).

Real example: "Gentechnik: Das musst du wissen! #Biologie #Klasse10". If every word counted, the
template words "musst" and "wissen" would cost points in every row that uses the channel's
own templates, even when the description covers "Gentechnik" well.

## Options
1. Reuse `score_title()` + `audit_description()` for each row. That gives a different rubric
   from the one requested and needs keywords the CSV doesn't have.
2. A separate, fixed rubric as requested. Within it:
   a. title length outside the range gives 0 points, or loses 1 point per character;
   b. shared words count every title word, or only topic words (no hashtags, no
      template/hook words from `titles.py`);
   c. duplicates are exact after normalising, or near-duplicates by similarity (`difflib`).

## Decision
Option 2, confirmed with the requester: lose 1 point per character (a 66-character title is
almost fine, not worthless). Count only topic words: the filler list comes from
`titles.TEMPLATES`, `EMOTION_WORDS`, `QUESTION_WORDS` and `DIRECT_ADDRESS`, so it can't drift
from the templates. Tags give 40 points: 20 for the count and 20 for the length. Duplicates
are exact after `fold` and whitespace collapse, with hashtags kept. Near-duplicate matching
would flag every pair of titles built from one template ("Gentechnik: Das musst du wissen!"
and "Proteine: Das musst du wissen!").

## Consequences
- The batch score and the `title` score can disagree for the same title. The README and
  spec say so.
- A topic that is also a hook word ("Wahrheit", "Mythos") doesn't count as a shared word.
  `text.stems` over-matches ("Nahrungsnetze" and "Nahrungsketten").
- Near-duplicate titles aren't found. If needed later, add them as a separate, opt-in check.
