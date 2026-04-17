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
Score IR  ↔  disk cache (db/{songId}_{partId}.json)
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
apply_update.py    permanent: applies update_vN.zip, backs up old files
flush_cache.py     permanent: deletes all cached score JSONs from db/
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

## GM Drum Map (selected frets → LilyPond name)

| MIDI | LilyPond     | Description              |
|------|--------------|--------------------------|
| 27   | bassdrum     | CR-78 Bass (Songsterr ext.) |
| 35   | bassdrum     | Bass Drum 2              |
| 36   | bassdrum     | Bass Drum 1              |
| 37   | sidestick    | Side Stick               |
| 38   | acousticsnare| Acoustic Snare           |
| 40   | acousticsnare| Electric Snare           |
| 41   | lowfloortom  | Low Floor Tom            |
| 42   | closedhihat  | Closed Hi-Hat            |
| 43   | highfloortom | High Floor Tom           |
| 44   | pedalhihat   | Pedal Hi-Hat             |
| 45   | lowtom       | Low Tom                  |
| 46   | openhihat    | Open Hi-Hat              |
| 47   | tommh        | Hi-Mid Tom               |
| 48   | tomfh        | High-Mid Tom             |
| 49   | crashcymbal  | Crash Cymbal 1           |
| 50   | lowmidtom    | High Tom                 |
| 51   | ridecymbal   | Ride Cymbal 1            |
| 53   | ridecymbal   | Ride Bell                |
| 57   | crashcymbalb | Crash Cymbal 2           |
| 92   | halfopenhihat| Half Open Hi-Hat (Songsterr ext.) |
| 93   | ridecymbal   | Ride variant (Songsterr ext.) |
| 97   | crashcymbal  | Crash (alt)              |
| 98   | openhihat    | Open Hi-Hat (alt)        |

(Full map in `parser.py`)

## LilyPond typesetting choices

- Single voice, `\stemDown` — no phantom rests, crash+kick share one stem
- `\numericTimeSignature` — shows `4/4` not common-time symbol
- `Beam.damping = +inf` — flat horizontal beams (standard in drum music)
- `ragged-right` — systems not stretched to fill page width
- Section breaks (`\break`) before sections with ≥ 3 measures
- Bar numbers every 4 measures, also at every system start
- Custom `drumStyleTable` — collision-free staff positions validated across 5 songs
- No courtesy time signature at line ends
- Letter paper, zero indent (no instrument name label)
- Header: title, composer (artist), subtitle (drummer name)

## Songs tested successfully

| Song                | Artist       | songId | partId | Notes                             |
|---------------------|--------------|--------|--------|-----------------------------------|
| Gouge Away          | Pixies       | 15960  | 5      | Simple 4/4, v8                    |
| Wave of Mutilation  | Pixies       | 16093  | 3      | v5 format, time sig changes       |
| Slowly We Rot       | Obituary     | 49310  | 4      | v8, blast beats, multi-tempo      |
| Pneuma              | Tool         | 455388 | 8      | v8, complex time sigs, tuplets    |
| Square Hammer       | Ghost        | 412647 | 9      | v8, pickup bar, ties              |
| Smells Like Teen Spirit | Nirvana  | 269    | 5      | v8, 2-tom kit, half-open hi-hat   |
| Money               | Pink Floyd   | 15761  | 9      | v8, 7/4, full tom descent         |
| In the Air Tonight  | Phil Collins | 50420  | 9      | v8, 6-tom concert kit             |
| Rosanna             | Toto         | 19993  | 18     | v8, ride bell, CR-78 bass (part 10)|

## Known issues / not yet implemented

- **CDN URL automation**: still requires manual DevTools for the CDN URL
  (Milestone 5 — next to implement)
- **Ties**: stored in IR, arc rendering validated for same-instrument ties.
  Cross-instrument tie arcs are suppressed (correct behaviour).
- **Repeats**: not seen in any song yet. Unknown encoding.
- **Dynamics**: `velocity` field stored in IR but not emitted to LilyPond.
- **`tripletFeel`**: `"8th"` and `"16th"` fields present in some songs
  (Rosanna, Money) — ignored; low priority.
- **YouTube sync**: `Score.youtube_id` / `Score.youtube_offset` fields exist
  in the IR but are never populated (Milestone 6).

## Planned features

- **CDN URL automation**: `python main.py https://www.songsterr.com/...` works
  without any DevTools (Milestone 5)
- **Browser-based grid editor**: `python editor.py` opens a local web UI
  with a drum grid (rows = instruments, columns = 1/16 beats). Click to
  toggle hits, edit section markers, change time signatures, compile to PDF.
- **Browser playback**: integrated into the editor. Uses Tone.js (Web Audio
  API) with a GM drumkit sample pack. Play/stop/loop controls with a
  scrolling playhead. Accessible from any browser on the local network.
- **YouTube sync**: embed a YouTube player alongside the grid. Paste a
  YouTube URL and set a time offset (where beat 1 falls in the video).
  Drum playback and video play in sync, with independent volume control.
  Offset stored in `Score.youtube_offset` (field already exists in the IR).
