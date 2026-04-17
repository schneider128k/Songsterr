# Songsterr Drum Tab → PDF Pipeline

Fetches drum tab data from Songsterr's CDN, parses it into an internal
representation (IR), caches it locally, and compiles it to a PDF score
via LilyPond.

## Pipeline

```
CDN URL  →  Songsterr JSON (v5 or v8)  →  Score IR  ↔  db/ cache
                                              ↓
                                        score.ly  →  LilyPond  →  score.pdf
```

## Usage

```bash
pip install requests
python main.py <CDN_URL>                # fetch, parse, compile to PDF
python main.py <CDN_URL> --no-drum-key  # skip the Drum Key legend
python main.py                          # list cached scores
```

### How to get a CDN URL from Songsterr (until Milestone 5 is done)

1. Open the song page on songsterr.com
2. Open DevTools (F12) → Network tab → filter `cloudfront` → Fetch/XHR
3. Reload the page
4. Find the request ending in `/<partId>.json` for the drum track
5. Right-click → Copy → Copy URL

## Project structure

```
main.py            CLI entry point (--no-drum-key flag supported)
pipeline.py        fetch_and_parse(), compile_to_pdf(), run_pipeline()
lilypond_utils.py  auto-detect LilyPond binary + version
ir.py              Score / Measure / Event / DrumNote / TempoChange dataclasses
parser.py          parse_json() — handles Songsterr JSON v5 and v8
cache.py           save_score() / load_score() / list_cached()
emitter.py         emit_lilypond() — Score IR → LilyPond source
apply_update.py    permanent: applies update_vN.zip, backs up old files
flush_cache.py     permanent: deletes all cached score JSONs from db/
db/                local JSON cache (gitignored)
scores/            output PDFs and .ly files (gitignored)
```

## Dependencies

- Python 3.10+
- `requests` (`pip install requests`)
- LilyPond 2.24+ — https://lilypond.org/download.html

LilyPond is auto-detected: `LILYPOND_BIN` env var → known platform paths → PATH.

## Songsterr JSON formats

**Version 8** (newer): `fret` = GM MIDI number, `string` = canvas position (ignored),
grace notes via `beat["graceNote"]`, tempo in `automations.tempo`.

**Version 5** (older): same `fret`, inline tempo via `beat["tempo"]["bpm"]`,
grace notes via `note["grace"] = true`, measures have `"index"` field.

## GM Drum Map (key entries)

| MIDI | LilyPond name  | Description              | Staff pos |
|------|----------------|--------------------------|-----------|
| 36   | bassdrum       | Bass Drum                | -5        |
| 37   | sidestick      | Side Stick               | -2        |
| 38   | acousticsnare  | Snare                    | +1        |
| 41   | lowfloortom    | Low Floor Tom            | -4        |
| 42   | closedhihat    | Closed Hi-Hat            | +5        |
| 43   | highfloortom   | High Floor Tom           | -3        |
| 44   | pedalhihat     | Pedal Hi-Hat             | -5        |
| 45   | lowtom         | Low Tom                  | -1        |
| 46   | openhihat      | Open Hi-Hat              | +5 (xcircle) |
| 47   | tommh          | Hi-Mid Tom               | +2        |
| 48   | hightom        | High-Mid Tom             | +3        |
| 49   | crashcymbal    | Crash Cymbal 1           | +7        |
| 50   | hightom        | High Tom                 | +3        |
| 51   | ridecymbal     | Ride Cymbal 1            | +4        |
| 53   | ridebell       | Ride Bell                | +4        |
| 57   | crashcymbalb   | Crash Cymbal 2           | +6        |
| 92   | halfopenhihat  | Half Open Hi-Hat         | +5 (xcircle) |

## LilyPond typesetting choices

- Single voice, `\stemDown` — no phantom rests
- `\numericTimeSignature`, flat horizontal beams (`Beam.damping = +inf`)
- Section breaks before sections with ≥ 3 measures
- Bar numbers every 4 measures + every system start
- **Drum Key legend** appended by default (suppress with `--no-drum-key`):
  shows one labeled notehead per instrument used, top→bottom on staff

## Songs tested

| Song                    | Artist       | songId | partId |
|-------------------------|--------------|--------|--------|
| Gouge Away              | Pixies       | 15960  | 5      |
| Wave of Mutilation      | Pixies       | 16093  | 3      |
| Slowly We Rot           | Obituary     | 49310  | 4      |
| Pneuma                  | Tool         | 455388 | 8      |
| Square Hammer           | Ghost        | 412647 | 9      |
| Smells Like Teen Spirit | Nirvana      | 269    | 5      |
| Money                   | Pink Floyd   | 15761  | 9      |
| In the Air Tonight      | Phil Collins | 50420  | 9      |
| Rosanna                 | Toto         | 19993  | 18     |

## Known issues / not yet implemented

- **CDN URL automation**: still requires manual DevTools (Milestone 5 — next)
- **Ties**: stored in IR, validated for same-instrument; arcs not yet emitted
- **Dynamics**: `velocity` stored in IR but not emitted to LilyPond
- **`tripletFeel`**: present in Rosanna/Money JSON, ignored (low priority)
- **YouTube sync**: IR fields exist but not populated (Milestone 6)

## Planned features

- **Milestone 5**: `python main.py https://www.songsterr.com/...` — no DevTools needed
- **Milestone 6**: Browser grid editor + Tone.js playback + YouTube sync
- **Milestone 7**: Tie arcs, dynamics, notation polish
