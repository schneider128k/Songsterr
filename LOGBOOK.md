# Logbook

## Milestone 1 — Colab prototype (completed)

Built a working end-to-end pipeline in a Google Colab notebook:
`ir.py`, `parser.py`, `cache.py`, `emitter.py`. Tested on 5 songs.

---

## Milestone 2 — Desktop project (completed)

`lilypond_utils.py`, `pipeline.py`, `main.py`, `.gitignore`, `requirements.txt`,
`README.md`. Pushed to https://github.com/schneider128k/Songsterr

---

## Milestone 3 — Windows end-to-end verification (completed)

LilyPond 2.24.4 at `C:\LilyPond\lilypond-2.24.4\`, `LILYPOND_BIN` env var set.
Tested Wave of Mutilation and Into the Fire — clean PDFs, no bar check warnings.

---

## Milestone 4 — Systematic testing and parser/emitter fixes (completed)

### Utility scripts
- `apply_update.py`: applies versioned `update_vN.zip`, backs up replaced files
- `flush_cache.py`: deletes all cached score JSONs from `db/`

### Songs tested and confirmed working
Square Hammer (Ghost), Smells Like Teen Spirit (Nirvana), Wave of Mutilation (Pixies)

### parser.py fixes (updates v1–v15, v19, v27)
- Full GM map rewritten with canonical LilyPond drum names throughout
  (`crashcymbal`, `closedhihat`, `acousticsnare`, `bassdrum`, etc.)
- MIDI 37 → `sidestick`, MIDI 41 → `lowfloortom`, MIDI 92 → `halfopenhihat`
- MIDI 48 → `hightom` (was `tomfh` = floor tom — wrong!)
- MIDI 50 → `hightom` (was `tomml` = middle line — wrong!)
- Fret 27 → `bassdrum` (CR-78 bass, In the Air Tonight)
- Fret 93 → `ridecymbal` (Songsterr extension, Rosanna)
- `anacrusis`/pickup bar duration fixed
- Ties: `DrumNote.tie` field added; parser reads it
- v8 grace note cursor handling fixed

### emitter.py fixes (updates v1–v27)
- Single voice `\stemDown`, flat beams — no phantom rests
- Snare position: `+1` (space between lines 3 and 4 — standard published position)
- Pickup bar: rest-only measure with different time sig emits `\partial`
  instead of `\time`, matching Songsterr bar numbering
- Tie validation: only emit `~` when tied note's lily name in next event
- onBeat grace notes: emit `\appoggiatura { note8 }` only (no double note)
  — fixes 7 bar check warnings in Smells Like Teen Spirit
- Subtitle: removed redundant "drums: " prefix
- **Drum Key legend**: appended by default at end of every score.
  Shows only instruments that appear in the score, ordered top→bottom.
  Suppress with `--no-drum-key` flag.
- SyntaxWarning in docstring fixed (raw string)

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

## Current milestone — Milestone 5: CDN URL automation

**Goal**: `python main.py https://www.songsterr.com/a/wsa/...` just works,
with no manual DevTools fishing for the CDN URL.

**Approach**: The Songsterr website makes an API call to fetch tab data.
We need to reverse-engineer how to derive the CDN URL from a page URL.
Likely approach: fetch the Songsterr page, find the song ID from the URL,
then call Songsterr's API to get the revision/CDN URL.

**Known Songsterr API endpoint** (observed via DevTools):
`https://www.songsterr.com/api/meta/{songId}/revisions`
or similar — needs investigation.

**Next update will be v28** (this session's consolidated update).

---

## Planned milestones (future)

**Milestone 6 — Browser-based grid editor**
- `python editor.py` opens a local web UI with a drum grid
- Toggle hits, edit section markers, change time signatures, compile to PDF
- Browser playback (Tone.js), YouTube sync

**Milestone 7 — Notation polish**
- Tie arcs emitted to LilyPond
- Dynamics (`velocity`) emitted

## Milestone 4 continued — Layout polish (updates v29–v32)

- `ragged-right = ##f` (flush) tried but caused stretched short lines before
  section breaks — no clean LilyPond fix for per-line ragged control.
- `ragged-right = ##t` (ragged) restored — matches published Hal Leonard /
  Alfred drum scores; looks clean and professional.
- `MAX_MEASURES_PER_LINE = 4` added: forced `\break` after every 4 measures
  prevents crowding. LilyPond may break earlier for dense measures (correct).
  Section breaks reset the counter so sections always start on a new line.
- `ragged-last = ##t` added then removed (only affects last line of whole piece,
  not lines before section breaks).

**Final layout settings**: ragged-right, max 4 measures per line,
section breaks always start a new line.
