# Logbook

## Milestone 1 — Colab prototype (completed)

Built a working end-to-end pipeline in a Google Colab notebook:

- `ir.py`: dataclasses for `Score`, `Measure`, `Event`, `DrumNote`, `TempoChange`
  using exact `Fraction` arithmetic for all time positions
- `parser.py`: parses Songsterr CDN JSON, handles both v5 (older, integer strings,
  inline tempo) and v8 (newer, fractional strings, grace notes on beat) formats
- `cache.py`: serialises/deserialises `Score` IR to/from local JSON files,
  with `Fraction` values stored as `[numerator, denominator]` lists
- `emitter.py`: compiles `Score` IR to a LilyPond source string with all
  typesetting choices finalised (single voice stemDown, flat beams, custom
  drum style table, bar numbers every 4, section breaks, etc.)
- Successfully tested on 5 songs: Gouge Away, Wave of Mutilation, Slowly We Rot,
  Pneuma, and one unknown Earth song

---

## Milestone 2 — Desktop project (completed)

Converted the Colab notebook into a proper desktop Python project:

- `lilypond_utils.py`: auto-detects LilyPond binary (env var → known platform
  paths → PATH fallback); works on macOS, Linux, Windows
- `pipeline.py`: `fetch_and_parse()` and `compile_to_pdf()` extracted from the
  Colab notebook; PDFs saved to `scores/`, cache in `db/`
- `main.py`: thin CLI — `python main.py <CDN_URL>` runs the full pipeline,
  `python main.py` lists cached scores
- `.gitignore`: excludes `db/`, `scores/`, `__pycache__/`, `.venv/`
- `requirements.txt`: `requests` only
- `README.md`: full project documentation
- Pushed to https://github.com/schneider128k/Songsterr

---

## Milestone 3 — Windows end-to-end verification (completed)

Verified the full pipeline works on Windows:

- LilyPond 2.24.4 installed from zip, placed at `C:\LilyPond\lilypond-2.24.4\`
- `LILYPOND_BIN` user environment variable set to
  `C:\LilyPond\lilypond-2.24.4\bin\lilypond.exe`
- `lilypond_utils.py` auto-detects the binary correctly via the env var
- Python virtual environment set up with `.venv`, `requests` installed
- Full pipeline tested on Wave of Mutilation (Pixies, songId=16093, partId=3)
  and Into the Fire (Dokken, songId=5829): fetch → parse → cache →
  LilyPond compile → PDF produced in `scores/`
- No errors, no bar check warnings

---

## Milestone 4 — Systematic testing and parser/emitter fixes (completed)

Tested songs: Gouge Away (Pixies), Wave of Mutilation (Pixies),
Slowly We Rot (Obituary), Into the Fire (Dokken).

### Utility scripts added

- `apply_update.py`: permanent script that applies versioned `update_vN.zip`
  files, backing up replaced files automatically. Never needs updating.
- `flush_cache.py`: deletes all cached score JSONs from `db/`. Run after
  any update that changes `parser.py` or `ir.py`.
- `.gitignore` updated: excludes `*.bak` and `update_v*.zip`

### Bugs fixed in `parser.py`

1. All drum note names were Songsterr aliases, not standard LilyPond names.
   LilyPond silently drops unrecognised names — crashes, hi-hats and other
   instruments were completely invisible in every PDF. Fixed by rewriting
   the entire GM map to use canonical LilyPond drum names.
2. MIDI 37 (Side Stick) mapped to snare — now maps to `sidestick`.
3. MIDI 41 (Low Floor Tom) mapped to mid-tom — now maps to `lowfloortom`.
4. MIDI 92 (Half Open Hi-Hat) missing from GM map — Songsterr-specific
   extension. All half open hi-hat notes were silently dropped. Now maps
   to `halfopenhihat`.
5. `anacrusis` field ignored — pickup bars used wrong duration, corrupting
   all subsequent measure positions. Fixed.
6. Ties not stored — `DrumNote.tie` field added; parser reads it.
7. v8 grace notes used fragile duration threshold for cursor advance —
   replaced with explicit `Event.grace_is_v8` flag.

### Bugs fixed in `emitter.py`

8. Staff positions wrong: `crashcymbal` 7→5, `bassdrum` -5→-3, `pedalhihat` -6→-5.
9. `crashcymbalb` renders hollow (LilyPond internal hardcoding) — emitted as
   `crashcymbal` with `\once \override NoteHead.staff-position = #6`.
10. `pedalhihat` + `bassdrum` collision — bassdrum suppressed when pedalhihat
    present on same beat (matches Songsterr behaviour).
11. `\appoggiatura` stole time from following note in drummode, causing bar
    check failures. Fixed: always use `\acciaccatura`.
12. Grace note emitted doubled main note, adding an extra beat to the measure.
    Fixed: grace token emits only the `\acciaccatura { }` prefix.
13. Double `\time` at start of score — fixed by initialising `prev_sig`
    to first measure's time sig.
14. Mid-measure tempo changes silently dropped — fixed.
15. `_fill_rests` silent fallback — now prints a warning to stderr.
16. `SyntaxWarning` in docstring — converted to raw string.

### Known remaining issues

- Ride cymbal and closed hi-hat share staff position 5 (visually identical).
- Half open hi-hat renders as `xcircle` (same as open hi-hat) — LilyPond
  has no distinct built-in symbol.
- `crashcymbalb` still renders hollow — cosmetic only, position is correct.
- Ties stored in IR but arc rendering not yet verified across all songs.
- Pneuma (Tool) not yet retested with current fixes.

---

## Current milestone — Milestone 5 (next session picks up here)

**Goal**: CDN URL automation.

Given a Songsterr page URL, automatically find the CDN URL for the drum track
so the user never has to use DevTools manually.

Tasks:
1. Investigate Songsterr's page structure and API to find how the CDN URL
   is embedded or derivable from the song page URL
2. Implement `resolve_cdn_url(page_url) -> str` in a new `songsterr_api.py`
3. Update `pipeline.py` and `main.py` to accept either a CDN URL or a
   Songsterr page URL transparently
4. Test on all known songs
5. Update README and logbook, push

---

## Planned milestones (future)

**Milestone 6 — Browser-based grid editor**
- `python editor.py` starts a local server and opens the browser automatically
- Grid view: rows = drum instruments, columns = 1/16 beats, continuous scroll
- Drum rows: Crash, Ride, Hi-Hat, Open Hi-Hat, Hi-Hat Pedal, Snare, Side Stick,
  High Tom, Mid Tom, Floor Tom, Bass Drum
- Left click = toggle hit, Shift+click = cycle accent (normal → accent → ghost)
- Right-click measure header = edit section marker text
- Toolbar: load cached score, new blank score, add/delete measure,
  change time signature, Compile → PDF, Save
- No new pip dependencies (stdlib `http.server` + `webbrowser` only)
- Supports both workflows: correct an existing Songsterr score, or
  compose a new score from scratch

**Milestone 7 — Notation polish**
- Tie arcs emitted and verified
- Dynamics (`velocity`) emitted
- Ride cymbal moved to staff position 6 (above hi-hat)
- Any remaining notation improvements found during editor use
