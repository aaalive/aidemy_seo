# 0008 - Shorts series from the title hashtags #Fach + #KlasseN

- Status: accepted
- Date: 2026-11-18

## Context
Requested: `aidemy-seo series PATH_TO_CSV` groups Shorts by `#Fach` + `#KlasseN`. 2 or more
videos make a series "{Fach} Klasse {N}", and the rest is "not sorted". Her titles end with
`#Fach #KlasseN`, because `titles.title_tags()` writes them. Real example:
`tests/fixtures/titles_to_fix.csv`: "#Biologie #biologie #Klasse9 #Zellbiologie" (a repeat and
a topic tag), "#Deutsch" without a grade, and "#Biologie #Klasse11" on 3 videos.

## Options
1. **Which hashtag is the subject**
   a. a fixed list of school subjects;
   b. the first hashtag that is not `#Klasse…` and not a platform tag such as `#Shorts`;
   c. every non-grade hashtag, so one video can be in several series.
2. **Unclear videos** (2 grades, no grade, no subject)
   a. guess (e.g. the first grade);
   b. put them under "not sorted" with a reason.
3. **Where the data comes from**: the title only, or also the tags and the description.

## Decision
1b, 2b, 3 = the title only.
- A subject list would miss subjects (Ethik, Philosophie, WAT, ...) and needs upkeep. The first
  hashtag matches how `title_tags()` builds titles.
- Option 1c would put a video in "Biologie Klasse 9" and "Zellbiologie Klasse 9", which is no
  use for a playlist.
- A guessed series puts a video in the wrong playlist. A reason tells the user what to fix.
- The same video_id twice is skipped with a warning, because it would make a fake 2-video
  series.
- Subjects are grouped after `text.fold`, so `#Ethik` and `#ethik` are one series, spelled as in
  the first video.
- The command writes no file, so the input can't be overwritten.

## Consequences
- `#Bio` and `#Biologie` are two series. Consistent titles (`title --generate`, `ab-pack`)
  avoid this.
- A title that starts its hashtags with a topic (`#Zellbiologie #Biologie #Klasse9`) gets the
  topic as its subject. The output shows every series, so the user sees it.
- No playlist is created. That would need OAuth write access. This project only uses a
  read-only API key (`youtube_api.py`), and `series` uses no API at all.

## Grade ranges and levels (2026-11-18, asked after the first version)
Question: what happens with `#Klasse11-12`, `#Oberstufe`, `#Q11`?

What the first version did:
- `#Klasse11-12` was read as `#Klasse11`, because a hashtag stops at `-` (YouTube links only
  `#Klasse11` too). The video was filed under Klasse 11 without any warning, and `ab-pack` rewrote
  the tag to `#Klasse11`.
- A level first (`#Oberstufe #Biologie #Klasse11`) became the subject: "Oberstufe Klasse 11".
- A level alone was not sorted with the unhelpful reason "no #KlasseN hashtag".

Options:
1. Map to grades: `#Q11` -> 11, `#Q1` -> 11, `#Oberstufe` -> 11?
2. Put a range into every series it spans (11-12 -> Klasse 11 and Klasse 12).
3. Separate series per level ("Biologie Oberstufe", "Biologie Q11").
4. Recognise ranges and levels, never turn them into a grade. Without `#KlasseN` the video is not
   sorted with a specific reason. Next to `#KlasseN` they are extra information, and a level is
   never the subject.

Decision: option 4.
- Option 1 guesses. `#Q11` is Klasse 11 in Bayern, NRW's Q1/Q2 are 11/12 or 12/13 depending on
  G8/G9, and `#Oberstufe` covers 2-3 grades. A wrongly filed video sits in the wrong playlist
  without anyone noticing. An unsorted one is listed with its reason and fixed in a minute.
- Option 2 is defensible: an 11-12 video does fit both playlists. But it breaks "each video in one
  place", and counts videos twice. And `#Klasse11-12` is a broken tag on YouTube anyway (only
  `#Klasse11` is a link), so the better fix is in the title.
- Option 3 adds a second naming scheme next to the requested "{Fach} Klasse {N}". It can be added
  later as an opt-in if the channel uses levels consistently.

Consequences:
- `series.title_hashtags` reads a written range (`-`, `–`, `/`) as one tag. `grade_kind` tells a
  grade, a range and a level apart. `ab-pack` uses both, so a range stays in the new titles as
  written and is never dropped, and so does a level.
- The level list (`series.LEVEL_RE`) is fixed. An unknown way of writing a level (`#Kursstufe`,
  `#J1`) in first place is still taken as the subject. Extend the list when one shows up.
- `titles.title_tags()` (used by `title --generate`, `lesson` and `experiment assign`) follows the
  same rule since 2026-11-18, as requested. "Klasse 11-12" gives `#Klasse11-12` and "Q11" gives
  `#Q11`, instead of `#Klasse11`. So the generator never writes a grade that `series` would then
  misfile (specs/titles.md).
- Ranges stay "not sorted". Putting them into every series they span (option 2) was offered
  and declined.
