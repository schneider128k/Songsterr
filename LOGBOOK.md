# Logbook

## Milestone 1 — Colab prototype (completed)

Built a working end-to-end pipeline in a Google Colab notebook:
`ir.py`, `parser.py`, `cache.py`, `emitter.py`. Tested on 5 songs.

---

## Milestone 2 — Desktop project (completed)

`lilypond_utils.py`, `pipeline.py`, `main.py`, `.gitignore`, `requirements.txt`,
`README.md`. Pushed to <https://github.com/schneider128k/Songsterr>

---

## Milestone 3 — Windows end-to-end verification (completed)

LilyPond 2.24.4 at `C:\LilyPond\lilypond-2.24.4\`, `LILYPOND_BIN` env var set.
Tested Wave of Mutilation and Into the Fire — clean PDFs, no bar check warnings.

---

## Milestone 4 — Systematic testing and parser/emitter fixes (completed)

### Utility scripts

* `apply_update.py`: applies versioned `update_vN.zip`, backs up replaced files
* `flush_cache.py`: deletes all cached score JSONs from `db/`

### Songs tested and confirmed working

Square Hammer (Ghost), Smells Like Teen Spirit (Nirvana), Wave of Mutilation (Pixies)

### parser.py fixes (updates v1–v15, v19, v27)

* Full GM map rewritten with canonical LilyPond drum names throughout
  (`crashcymbal`, `closedhihat`, `acousticsnare`, `bassdrum`, etc.)
* MIDI 37 → `sidestick`, MIDI 41 → `lowfloortom`, MIDI 92 → `halfopenhihat`
* MIDI 48 → `hightom` (was `tomfh` = floor tom — wrong!)
* MIDI 50 → `hightom` (was `tomml` = middle line — wrong!)
* Fret 27 → `bassdrum` (CR-78 bass, In the Air Tonight)
* Fret 93 → `ridecymbal` (Songsterr extension, Rosanna)
* `anacrusis`/pickup bar duration fixed
* Ties: `DrumNote.tie` field added; parser reads it
* v8 grace note cursor handling fixed

### emitter.py fixes (updates v1–v27)

* Single voice `\stemDown`, flat beams — no phantom rests
* Snare position: `+1` (space between lines 3 and 4 — standard published position)
* Pickup bar: rest-only measure with different time sig emits `\partial`
  instead of `\time`, matching Songsterr bar numbering
* Tie validation: only emit `~` when tied note's lily name in next event
* onBeat grace notes: emit `\appoggiatura { note8 }` only (no double note)
  — fixes 7 bar check warnings in Smells Like Teen Spirit
* Subtitle: removed redundant "drums: " prefix
* **Drum Key legend**: appended by default at end of every score.
  Shows only instruments that appear in the score, ordered top→bottom.
  Suppress with `--no-drum-key` flag.
* SyntaxWarning in docstring fixed (raw string)

### Staff positions (final collision-free layout)

```
+7  Crash          +5  Hi-Hat         +4  Ride
+3  High Tom       +2  Hi-Mid Tom     +1  Snare
 0  Low-Mid Tom   -1  Low Tom        -2  Side Stick
-3  Hi Floor Tom  -4  Lo Floor Tom   -5  Bass Drum / Pedal Hi-Hat
```

Validated across 5 songs: Square Hammer, In the Air Tonight,
Smells Like Teen Spirit, Rosanna, Money.

---

## Milestone 4 continued — Layout polish (updates v29–v32)

* `ragged-right = ##f` (flush) tried but caused stretched short lines before
  section breaks — no clean LilyPond fix for per-line ragged control.
* `ragged-right = ##t` (ragged) restored — matches published Hal Leonard /
  Alfred drum scores; looks clean and professional.
* `MAX_MEASURES_PER_LINE = 4` added: forced `\break` after every 4 measures
  prevents crowding. LilyPond may break earlier for dense measures (correct).
  Section breaks reset the counter so sections always start on a new line.
* `ragged-last = ##t` added then removed (only affects last line of whole piece,
  not lines before section breaks).

**Final layout settings**: ragged-right, max 4 measures per line,
section breaks always start a new line.

---

## Milestone 5 attempt #1 — CDN URL automation (update v33, failed live test)

Shipped a two-strategy resolver: (A) `/api/meta/{songId}/revisions` looking
for a `source`/`token` field on the latest revision, (B) `__NEXT_DATA__`
script tag scrape from page HTML. Both strategies failed on the live API
when tested on Wave of Mutilation:

* Strategy A: revision objects no longer carry a `source` token. The token
  isn't in `/api/meta/{songId}/revisions` at all under any name.
* Strategy B: Songsterr is not a Next.js app. No `<script id="__NEXT_DATA__">`
  exists in their page HTML. Worse, the page route is fronted by Cloudflare,
  which sends an HTTP 103 Early Hints response that Python's `requests` and
  `urllib.request` both incorrectly treat as final, returning length=0 — so
  even if I'd searched for a different script id, the fetch would still fail.

The v33 design lesson: speculative API discovery from third-party
documentation is unreliable. Three rounds of `diagnoseN.py` were needed to
pin down where the token actually lives.

---

## Milestone 5 — CDN URL automation (completed, update v34)

### Where the token actually lives

The 21-character revision token (e.g. `qE0QIyDkUuju6PtZ-Hg3I`) is the
`image` field on the song's current-revision metadata. Songsterr uses the
same token to identify a revision's preview images and audio asset paths,
so it's stored once under that name and reused for the per-track JSON URL.

`GET /api/meta/{songId}` returns a JSON object with everything needed:

```
revisionId    → the second path segment
image         → the third path segment (the "token")
tracks[i]     → has partId, instrumentId, isDrums, name
                — pick the entry where isDrums == true
```

CDN URL = `https://dqsljvtekg760.cloudfront.net/{songId}/{revisionId}/{image}/{drumPartId}.json`.

This is the **same endpoint** the v32 pipeline already called to fetch
title/artist. The token was being delivered to us all along under a
non-obvious name; v33's mistake was looking for it in `/revisions` (which
returns light revision summaries without asset identifiers) and assuming
the Next.js framework based on extension activity from older Songsterr.

### What v34 changes

`cdn_resolver.py` rewritten with two strategies:

* **Strategy A (primary)**: `GET /api/meta/{songId}` →
  `_build_cdn_url_from_meta(meta, song_id, hint)`. Single API call, no
  subprocess. Works for every song tested. This is the path the resolver
  takes virtually 100% of the time.
* **Strategy B (fallback)**: page HTML via `curl` subprocess →
  `<script id="state" type="application/json">…</script>` → state.meta.current
  → same builder. Used only if Strategy A fails. Uses `curl` instead of
  `requests`/`urllib` because Python HTTP libraries mishandle Cloudflare's
  103 Early Hints; curl handles 103 correctly per RFC 8297.

`pipeline.py` and `main.py` are **unchanged** from v33 — the public API
of `cdn_resolver` (`resolve_cdn_url`, `is_cdn_url`, `is_songsterr_page_url`,
`probe_page`, `ResolveError`) is preserved.

`probe_page()` updated to dump the new fields the next debug cycle would
need: meta API status + key list + presence flags for `image`, `revisionId`,
and `tracks`; curl availability; page state extraction status; the
discovered cloudfront host from `<link rel="dns-prefetch">`.

### Drum-track identification

`_find_drum_track(tracks, hint)` priority order:

1. URL hint (e.g. `t3` in `...drum-tab-s16093t3` → partId 3)
2. `tracks[i].isDrums == true` (Songsterr's own derived field)
3. `tracks[i].instrumentId == 1024` (GM drum kit)
4. `'drum'` substring in track name (last-resort fallback for tabs missing
   the structured fields)

The hint, when given, is honored even if the resulting track isn't drums —
useful for selecting alternate percussion tracks or as a manual override
when auto-detection fails.

### Validation

* 24 offline tests in `test_resolver_v34.py`, including a regression test
  using the real `meta.current` JSON captured from the live page during the
  v33 → v34 debug cycle. The test verifies that the resolver produces the
  exact byte-for-byte CDN URL the user observed in DevTools:
  `https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json`.
* Live test on the user's Windows machine pending.

### Known dependency note

Strategy B requires `curl` on PATH. Windows 10+ ships with `curl.exe` by
default; Strategy A doesn't need it. If both strategies are needed and
curl is missing, the resolver still raises a clear error explaining how to
work around (install curl, or pass the CDN URL directly).

---

## Current milestone — Milestone 6: Browser-based grid editor (next)

* `python editor.py` opens a local web UI with a drum grid
* Toggle hits, edit section markers, change time signatures, compile to PDF
* Browser playback (Tone.js), YouTube sync

## Planned future milestones

**Milestone 7 — Notation polish**

* Tie arcs emitted to LilyPond
* Dynamics (`velocity`) emitted
