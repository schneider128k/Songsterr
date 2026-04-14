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

## Current milestone — Milestone 4 (next session picks up here)

**Goal**: Systematic testing and parser/emitter fixes.

The PDF output should match the Songsterr score as closely as possible before
any editor GUI is built. A buggy data foundation would make the editor painful
to use.

Tasks:
1. Test all known songs and carefully compare PDF output against the Songsterr
   score in the browser, documenting every mismatch
2. Known songs to test:
   - Gouge Away — Pixies (songId=15960, partId=5) — simple 4/4, v8
   - Wave of Mutilation — Pixies (songId=16093, partId=3) — v5, time sig changes
   - Slowly We Rot — Obituary (songId=49310, partId=4) — v8, blast beats, multi-tempo
   - Pneuma — Tool (songId=455388, partId=8) — v8, complex time sigs, tuplets
   - Into the Fire — Dokken (songId=5829) — already tested on desktop
3. Document mismatches: wrong drum instrument, wrong rhythm, missing notes,
   bar check warnings, anything that looks off in the PDF
4. Fix bugs found in `parser.py` and/or `emitter.py`
5. Known issues to investigate during this milestone:
   - Ties: `note["tie"] = true` present in JSON but not emitted (no tie arc drawn)
   - `anacrusis` field in v5 songs currently ignored (may affect bar numbering)
   - Any wrong GM drum mappings for the user's kit:
     Crash, Ride, Hi-Hat (closed/open/pedal), Snare, Side Stick,
     High Tom, Mid Tom, Floor Tom, Bass Drum
6. Once all fixes confirmed working, update logbook and push

---

## Planned milestones (future)

**Milestone 5 — CDN URL automation**
- Given a Songsterr page URL, automatically find the CDN URL for the drum track
- `python main.py https://www.songsterr.com/a/wsa/...` just works
- No more manual DevTools fishing

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
- Tie arcs emitted to LilyPond
- Dynamics (`velocity`) emitted
- Any remaining notation improvements found during editor use