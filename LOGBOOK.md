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
- Full pipeline tested on Wave of Mutilation (Pixies, songId=16093, partId=3):
  fetch → parse → cache → LilyPond compile → PDF produced in `scores/`
- No errors, no bar check warnings

---

## Current milestone — Milestone 4 (next session picks up here)

**Goal**: Test more songs and implement ties.

Suggested tasks:
1. Test the remaining known-good songs (Slowly We Rot, Pneuma, Earth unknown)
   and confirm clean PDF output for each
2. Implement tie arcs: `note["tie"] = true` is already parsed and stored in the
   IR as `Event` — the emitter needs to detect consecutive tied notes and emit
   `~` between them in LilyPond
3. Investigate the `anacrusis` field in v5 songs and whether it affects
   bar numbering
4. Once any fixes are confirmed working, update this logbook and push

**Known issues** (carry-over from earlier milestones):
- Ties not drawn (tie arc missing in PDF output)
- `anacrusis` field in v5 songs ignored (may affect bar numbering)
- Dynamics (`velocity`) not emitted