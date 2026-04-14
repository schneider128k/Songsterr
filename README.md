# Songsterr Drum Tab → PDF Pipeline

Fetches drum tab data from Songsterr's CDN, parses it into an internal
representation (IR), caches it locally, and compiles it to a PDF score
via LilyPond.

## Pipeline

```
CDN URL
  ↓  requests.get()
Songsterr JSON (v5 or v8 format)
  ↓  parse_json()
Score IR  ←→  disk cache (db/{songId}_{partId}.json)
  ↓  emit_lilypond()
score.ly
  ↓  lilypond (subprocess)
score.pdf  →  scores/
```

## Usage

```bash
pip install requests
python main.py <CDN_URL>   # fetch, parse, compile to PDF
python main.py             # list cached scores
```

### How to get a CDN URL from Songsterr

1. Open the song page on songsterr.com
2. Open DevTools (F12) → Network tab → filter `cloudfront` → Fetch/XHR
3. Reload the page
4. Find the request ending in `/<partId>.json` for the drum track
5. Right-click → Copy → Copy URL

Example:
```
https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json
```

## Project structure

```
main.py            CLI entry point
pipeline.py        fetch_and_parse(), compile_to_pdf(), run_pipeline()
lilypond_utils.py  auto-detect LilyPond binary + version
ir.py              Score / Measure / Event / DrumNote / TempoChange dataclasses
parser.py          parse_json() — handles Songsterr JSON v5 and v8
cache.py           save_score() / load_score() / list_cached()
emitter.py         emit_lilypond() — compiles Score IR to LilyPond source
db/                local JSON cache (gitignored)
scores/            output PDFs and .ly files (gitignored)
```

## Dependencies

- Python 3.10+
- `requests` (pip install requests)
- LilyPond — install from https://lilypond.org/download.html

LilyPond is auto-detected in this order:
1. `LILYPOND_BIN` environment variable
2. Platform-specific known paths (macOS app bundle / Homebrew, Linux apt, Windows)
3. `lilypond` on PATH

## Songsterr JSON formats

Two versions exist in the wild:

**Version 8** (newer):
- `fret` = GM MIDI drum number (35–98)
- `string` = fractional staff position (ignored by this tool)
- `beat["graceNote"]` = `'beforeBeat'` or `'onBeat'`
- Tempo in `automations.tempo` array

**Version 5** (older):
- Same `fret` = GM MIDI number
- `string` = integer (ignored)
- Grace notes: `note["grace"] = true` on the note itself
- `beat["tempo"]["bpm"]` inline on beats
- Measures have explicit `"index"` field (1-based)

**Key insight**: `fret` alone (= GM MIDI number) fully identifies the drum
instrument. The `string` field is only used by Songsterr's canvas renderer
and is ignored here.

## GM Drum Map (fret → LilyPond name)

| MIDI | LilyPond | Description         |
|------|----------|---------------------|
| 35   | bd       | Bass Drum 2         |
| 36   | bd       | Bass Drum 1         |
| 37   | sn       | Side Stick          |
| 38   | sn       | Acoustic Snare      |
| 40   | sn       | Electric Snare      |
| 42   | hh       | Closed Hi-Hat       |
| 44   | hhp      | Pedal Hi-Hat        |
| 46   | hho      | Open Hi-Hat         |
| 49   | cymca    | Crash Cymbal 1      |
| 51   | cymr     | Ride Cymbal 1       |
| 57   | cymcb    | Crash Cymbal 2      |
| 97   | cymca    | Crash (alt)         |
| 98   | hho      | Open Hi-Hat (alt)   |

(Full map including toms and other instruments is in `parser.py`)

## LilyPond typesetting choices

- Single voice, `\stemDown` — no phantom rests, crash+kick share one stem
- `\numericTimeSignature` — shows `4/4` not `𝄼`
- `Beam.damping = +inf` — flat horizontal beams (standard in drum music)
- `ragged-right` — systems not stretched to fill page width
- Section breaks (`\break`) before sections with ≥ 3 measures
- Bar numbers every 4 measures, also at every system start
- Custom `drumStyleTable` — hi-hat above staff (position 5, not 3)
- No courtesy time signature at line ends
- Letter paper, zero indent (no instrument name label)
- Header: title, composer (artist), subtitle (drummer name)

## Songs tested successfully

| Song              | Artist   | songId | partId | Notes                        |
|-------------------|----------|--------|--------|------------------------------|
| Gouge Away        | Pixies   | 15960  | 5      | Simple 4/4, v8               |
| Wave of Mutilation| Pixies   | 16093  | 3      | v5 format, time sig changes  |
| Slowly We Rot     | Obituary | 49310  | 4      | v8, blast beats, multi-tempo |
| Pneuma            | Tool     | 455388 | 8      | v8, complex time sigs, tuplets|
| Earth (unknown)   | unknown  | 412647 | 9      | v8, ties, complex fills      |

## Known issues / not yet implemented

- **Ties**: `note["tie"] = true` present in JSON but not emitted. Notes play
  correctly but no tie arc is drawn.
- **Repeats**: Not seen in any song yet. Unknown how Songsterr encodes them.
- **Dynamics**: `velocity` field stored in IR but not emitted to LilyPond.
- **`anacrusis` field**: Present in some v5 songs, currently ignored.
  Could affect bar numbering for pickup measures.
- **YouTube sync**: `Score.youtube_id` and `Score.youtube_offset` fields
  exist in the IR but are never populated.
