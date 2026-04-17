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

**Goal**: PDF output should match the Songsterr score as closely as possible
before any editor GUI is built.

### Utility scripts added

- `apply_update.py`: permanent script that applies versioned `update_vN.zip`
  files, backing up replaced files automatically. Never needs updating.
- `flush_cache.py`: deletes all cached score JSONs from `db/`. Run after
  any update that changes `parser.py` or `ir.py`.

### Bugs fixed in `parser.py`

1. All drum note names were Songsterr aliases — rewrote entire GM map to use
   canonical LilyPond drum names (`crashcymbal`, `closedhihat`, etc.)
2. MIDI 37 (Side Stick) → `sidestick`
3. MIDI 41 (Low Floor Tom) → `lowfloortom`
4. MIDI 92 (Half Open Hi-Hat, Songsterr ext.) → `halfopenhihat`
5. `anacrusis` / pickup bar duration fixed
6. Ties: `DrumNote.tie` field added; parser reads it
7. v8 grace note cursor handling fixed

### Bugs fixed in `emitter.py` (update v18)

1. Snare position: `acousticsnare`/`snare`/`electricsnare`/`sn`: 0 → -1
2. Pickup bar: rest-only measure with different time sig emits `\partial`
   instead of `\time`, matching Songsterr bar numbering
3. Tie validation: only emit `~` when tied note's lily name appears in next
   non-grace event (prevents spurious arcs)

---

## Milestone 4 continued — GM map verification and staff position audit (completed)

**Songs analysed** (update v19): Square Hammer (Ghost), In the Air Tonight
(Phil Collins), Smells Like Teen Spirit (Nirvana), Rosanna (Toto),
Money (Pink Floyd)

### Changes in `emitter.py` — `_DRUM_STYLE` positions

Collision-free layout validated across all 5 songs:

| Instrument           | lily names                     | Old pos | New pos |
|----------------------|--------------------------------|---------|---------|
| Crash cymbal         | `crashcymbal`/`cymca`          | 7       | 7       |
| Hi-Hat               | `closedhihat`/`hh`/`hho`       | 5       | 5       |
| **Ride cymbal**      | `ridecymbal`/`cymr`/`ridebell` | **5**   | **4**   |
| High Tom             | `hightom`/`tomh`               | 3       | 3       |
| Hi-Mid Tom           | `tommh`                        | 2       | 2       |
| Snare (v18)          | `acousticsnare` etc.           | 1       | 1       |
| **Low-Mid Tom**      | `tomml`/`lowmidtom`            | **1**   | **0**   |
| Low Tom              | `lowtom`/`toml`                | -1      | -1      |
| Side Stick           | `sidestick`                    | -2      | -2      |
| **High Floor Tom**   | `tomfh`/`highfloortom`         | **-2**  | **-3**  |
| **Low Floor Tom**    | `tomfl`/`lowfloortom`          | **-3**  | **-4**  |
| Bass Drum            | `bassdrum`/`bd`                | -5      | -5      |

### New fret mappings in `parser.py` (update v19)

- Fret 27 → `bassdrum` (CR-78 bass sound, In the Air Tonight part 10)
- Fret 93 → `ridecymbal` (Ride area variant, Rosanna)

**After applying update_v19.zip, run `python flush_cache.py` before retesting.**

---

## Milestone 4 continued — Grace note bar check fix (update v20)

**Bug**: `onBeat` grace notes (v8 format, `ppoggiatura` style) were emitting
`\appoggiatura { note8 } noteXX` — but the following normal event at the same
position also emitted its note. LilyPond counted `noteXX` as real duration,
causing bar check failures (7 warnings in Smells Like Teen Spirit).

**Fix in `emitter.py`**: for `grace_type='on'`, emit only `\appoggiatura { note8 }`
(no trailing note). The following normal event already provides the target.
`beforeBeat` / `acciaccatura` style is unchanged (self-contained token).

**Also fixed**: `SyntaxWarning` about `\s` in emitter.py docstring — changed
module docstring to a raw string (`r"""`).

**No cache flush needed** (emitter.py only).

## Milestone 4 continued — Snare position corrected (update v21)

**Bug**: Snare was at position -1 (space between lines 2 and 3 — below middle
line). The standard published position is +1 (space between lines 3 and 4 —
above middle line), which matches Songsterr's rendering.

**Fix in `emitter.py`**: `acousticsnare`/`snare`/`electricsnare`/`sn`: -1 → +1.

Final collision-free layout:
  crashcymbal +7, hihat +5, ride +4, hightom +3, himidtom +2,
  snare +1, tomml 0, lowtom -1, sidestick -2, tomfh -3, tomfl -4, bassdrum -5

**No cache flush needed** (emitter.py only).

## Current milestone — Milestone 5: CDN URL automation

**Goal**: `python main.py https://www.songsterr.com/a/wsa/...` just works,
with no manual DevTools fishing for the CDN URL.

Given a Songsterr page URL, the pipeline should automatically determine the
CDN URL for the drum track. **Next update will be v22.**

---

## Planned milestones (future)

**Milestone 6 — Browser-based grid editor**
- `python editor.py` opens a local web UI with a drum grid
  (rows = instruments, columns = 1/16 beats)
- Toggle hits, edit section markers, change time signatures, compile to PDF
- **Browser playback**: Tone.js with GM drumkit sample pack
- **YouTube sync**: embed YouTube player, set time offset, drum + video in sync
- Both "correct existing" and "blank score from scratch" workflows

**Milestone 7 — Notation polish**
- Tie arcs emitted to LilyPond
- Dynamics (`velocity`) emitted
- Any remaining notation improvements
