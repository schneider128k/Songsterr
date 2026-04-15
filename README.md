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
python flush_cache.py      # delete all cached score JSONs
python apply_update.py update_vN.zip  # apply a versioned update
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
flush_cache.py     delete all cached score JSONs (run after parser/IR updates)
apply_update.py    apply a versioned update_vN.zip to the project
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

## Update workflow

When a new `update_vN.zip` is provided:

```bash
python apply_update.py update_vN.zip   # backs up old files, applies new ones
python flush_cache.py                  # only if parser.py or ir.py changed
python main.py <CDN_URL>               # re-run to verify
```

`apply_update.py` and `flush_cache.py` are permanent utility scripts —
they never need to be updated themselves.

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

| MIDI | LilyPond name    | Description                       |
|------|------------------|-----------------------------------|
| 35   | bassdrum         | Bass Drum 2                       |
| 36   | bassdrum         | Bass Drum 1                       |
| 37   | sidestick        | Side Stick                        |
| 38   | acousticsnare    | Acoustic Snare                    |
| 40   | electricsnare    | Electric Snare                    |
| 41   | lowfloortom      | Low Floor Tom                     |
| 42   | closedhihat      | Closed Hi-Hat                     |
| 43   | highfloortom     | High Floor Tom                    |
| 44   | pedalhihat       | Pedal Hi-Hat                      |
| 45   | lowtom           | Low Tom                           |
| 46   | openhihat        | Open Hi-Hat                       |
| 47   | lowmidtom        | Low-Mid Tom                       |
| 48   | himidtom         | High-Mid Tom                      |
| 49   | crashcymbal      | Crash Cymbal 1                    |
| 50   | hightom          | High Tom                          |
| 51   | ridecymbal       | Ride Cymbal 1                     |
| 52   | chinesecymbal    | Chinese Cymbal                    |
| 57   | crashcymbalb     | Crash Cymbal 2                    |
| 92   | halfopenhihat    | Half Open Hi-Hat (Songsterr ext.) |
| 97   | crashcymbal      | Crash (alt, Songsterr ext.)       |
| 98   | openhihat        | Open Hi-Hat (alt, Songsterr ext.) |

## LilyPond typesetting choices

- Single voice, `\stemDown` — no phantom rests, crash+kick share one stem
- `\numericTimeSignature` — shows `4/4` not `𝄼`
- `Beam.damping = +inf` — flat horizontal beams (standard in drum music)
- `ragged-right` — systems not stretched to fill page width
- Section breaks (`\break`) before sections with ≥ 3 measures
- Bar numbers every 4 measures, also at every system start
- Custom `drumStyleTable` — hi-hat above staff (position 5),
  bass drum between lines 1 and 2 (position -3)
- Grace notes always use `\acciaccatura` (never `\appoggiatura`)
- `pedalhihat` + `bassdrum` on same beat: bass drum suppressed
- No courtesy time signature at line ends
- Letter paper, zero indent (no instrument name label)
- Header: title, composer (artist), subtitle (drummer name)

## Songs tested successfully

| Song               | Artist   | songId | partId | Notes                               |
|--------------------|----------|--------|--------|-------------------------------------|
| Gouge Away         | Pixies   | 15960  | 5      | v8, half open hi-hat                |
| Wave of Mutilation | Pixies   | 16093  | 3      | v5, time sig changes, china cymbal  |
| Slowly We Rot      | Obituary | 49310  | 5      | v8, blast beats, multi-tempo, flams |
| Into the Fire      | Dokken   | 5829   | 6      | v8, floor tom, ride cymbal          |

## Planned features

- **CDN URL automation**: pass a Songsterr page URL directly —
  no more DevTools fishing for the CDN URL.
- **Browser-based grid editor**: `python editor.py` opens a local web UI
  with a drum grid (rows = instruments, columns = 1/16 beats). Click to
  toggle hits, edit section markers, change time signatures, compile to PDF.
- **Browser playback**: integrated into the editor. Uses Tone.js (Web Audio
  API) with a GM drumkit sample pack. Play/stop/loop controls with a
  scrolling playhead. Timing derived from `Score.seconds_at()` so tempo
  changes and odd time signatures are handled correctly. Accessible from
  any browser on the local network.

- **Ride cymbal vs hi-hat**: `ridecymbal` and `closedhihat` share staff
  position 5 — visually identical. Future fix: move ride to position 6.
- **Half open hi-hat symbol**: renders as `xcircle` (same as open hi-hat).
  LilyPond has no distinct built-in symbol for half-open vs fully open.
- **crashcymbalb notehead**: renders hollow due to LilyPond internal
  hardcoding. Position is correct; hollow vs solid is cosmetic only.
- **Ties**: stored in IR but arc rendering not yet verified across all songs.
- **Repeats**: not seen in any song yet.
- **Dynamics**: `velocity` field stored in IR but not emitted to LilyPond.
- **anacrusis**: supported in parser but not yet tested on a pickup-bar song.
- **YouTube sync**: `Score.youtube_id` / `Score.youtube_offset` fields exist
  but are never populated.
- **Pneuma (Tool)**: not yet retested with current fixes.
