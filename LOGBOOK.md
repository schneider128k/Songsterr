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

## Current milestone — Milestone 3 

**Goal**: Verify the desktop project works end-to-end on the local machine.

Tasks for the next session:
1. User runs `pip install requests` and `python main.py <CDN_URL>` on a known-good
   song (e.g. Gouge Away: songId=15960, partId=5)
2. Confirm PDF is produced in `scores/` without errors
3. If bar check warnings appear in LilyPond output, investigate and fix in `emitter.py`
4. If LilyPond is not found, debug `lilypond_utils.py` for the user's platform
5. Once clean, update this logbook and push

**Known issues to address eventually** (not blocking milestone 3):
- Ties not drawn (tie arc missing in output)
- `anacrusis` field in v5 songs ignored (may affect bar numbering)
- Dynamics (`velocity`) not emitted
