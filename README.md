# Songsterr Drum Tab → PDF Pipeline

Fetches drum tab data from Songsterr's CDN, parses it into an internal
representation (IR), caches it locally, and compiles it to a PDF score
via LilyPond.

## Pipeline

```
Songsterr page URL ─┐
                    ├──►  CDN URL  ──►  Songsterr JSON (v5 or v8)  ──►  Score IR  ↔  db/ cache
CDN URL  ───────────┘                                                       │
                                                                            ▼
                                                                       score.ly  ──►  LilyPond  ──►  score.pdf
```

The page-URL → CDN-URL step (Milestone 5) is handled by `cdn_resolver.py`.

## Usage

```
pip install requests
python main.py <PAGE_URL_or_CDN_URL>             # fetch, parse, compile to PDF
python main.py <PAGE_URL_or_CDN_URL> --no-drum-key   # skip the Drum Key legend
python main.py <PAGE_URL> --probe                # diagnostic — dump what the resolver sees
python main.py                                   # list cached scores
```

Either form works:

```
python main.py https://www.songsterr.com/a/wsa/pixies-wave-of-mutilation-drum-tab-s16093
python main.py https://www.songsterr.com/a/wsa/...-drum-tab-s16093t3        # multi-track: explicit partId
python main.py https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json
```

### When the page URL doesn't work

If Songsterr changes the internal JSON shape and the resolver fails:

1. Run `python main.py <PAGE_URL> --probe` to see what each strategy found.
2. As a fallback, grab the CDN URL the old way (DevTools → Network →
   filter `cloudfront` → reload → copy the `<partId>.json` request URL)
   and pass it directly. The pipeline accepts both forms forever.

## CDN URL automation (Milestone 5)

`cdn_resolver.resolve_cdn_url(page_url)` tries two strategies in order:

1. **`/api/meta/{songId}`** (primary). Returns the latest-revision metadata
   directly. Build the CDN URL from `revisionId` + `image` (the per-revision
   token) + the `partId` of the track where `isDrums == true`.
2. **Page HTML scrape via `curl`** (fallback). Songsterr embeds the same
   data in `<script id="state" type="application/json">…</script>` on every
   page; we extract `state.meta.current` and use the same logic. We use
   `curl` (rather than `requests`) because Cloudflare's HTTP 103 Early Hints
   response in front of the page route is mishandled by Python's HTTP
   libraries — `curl` handles it correctly per RFC 8297.

If the URL contains a `t<partId>` suffix (e.g. `...s16093t3`), that hint
overrides drum-track detection — useful for multi-drummer songs or when
you specifically want a non-default percussion track.

### Dependencies for Strategy B

`curl` on PATH. Windows 10+ ships with `curl.exe` by default; macOS and
most Linux distros include it. Strategy B is only used if Strategy A fails,
which has not happened in any tested song.

## Project structure

```
main.py            CLI entry point (--no-drum-key, --probe flags)
pipeline.py        fetch_and_parse(), compile_to_pdf(), run_pipeline()
cdn_resolver.py    resolve_cdn_url(), probe_page(), URL classifiers
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

* Python 3.10+
* `requests` (`pip install requests`)
* LilyPond 2.24+ — <https://lilypond.org/download.html>
* `curl` on PATH (only used by the resolver's Strategy B fallback; Windows
  10+ ships with it)

LilyPond is auto-detected: `LILYPOND_BIN` env var → known platform paths → PATH.

## Songsterr JSON formats

**Version 8** (newer): `fret` = GM MIDI number, `string` = canvas position (ignored),
grace notes via `beat["graceNote"]`, tempo in `automations.tempo`.

**Version 5** (older): same `fret`, inline tempo via `beat["tempo"]["bpm"]`,
grace notes via `note["grace"] = true`, measures have `"index"` field.

## GM Drum Map (key entries)

| MIDI | LilyPond name | Description | Staff pos |
| --- | --- | --- | --- |
| 36 | bassdrum | Bass Drum | -5 |
| 37 | sidestick | Side Stick | -2 |
| 38 | acousticsnare | Snare | +1 |
| 41 | lowfloortom | Low Floor Tom | -4 |
| 42 | closedhihat | Closed Hi-Hat | +5 |
| 43 | highfloortom | High Floor Tom | -3 |
| 44 | pedalhihat | Pedal Hi-Hat | -5 |
| 45 | lowtom | Low Tom | -1 |
| 46 | openhihat | Open Hi-Hat | +5 (xcircle) |
| 47 | tommh | Hi-Mid Tom | +2 |
| 48 | hightom | High-Mid Tom | +3 |
| 49 | crashcymbal | Crash Cymbal 1 | +7 |
| 50 | hightom | High Tom | +3 |
| 51 | ridecymbal | Ride Cymbal 1 | +4 |
| 53 | ridebell | Ride Bell | +4 |
| 57 | crashcymbalb | Crash Cymbal 2 | +6 |
| 92 | halfopenhihat | Half Open Hi-Hat | +5 (xcircle) |

## LilyPond typesetting choices

* Single voice, `\stemDown` — no phantom rests
* `\numericTimeSignature`, flat horizontal beams (`Beam.damping = +inf`)
* Section breaks before sections with ≥ 3 measures
* Bar numbers every 4 measures + every system start
* **Drum Key legend** appended by default (suppress with `--no-drum-key`):
  shows one labeled notehead per instrument used, top→bottom on staff

## Songs tested

| Song | Artist | songId | partId |
| --- | --- | --- | --- |
| Gouge Away | Pixies | 15960 | 5 |
| Wave of Mutilation | Pixies | 16093 | 3 |
| Slowly We Rot | Obituary | 49310 | 4 |
| Pneuma | Tool | 455388 | 8 |
| Square Hammer | Ghost | 412647 | 9 |
| Smells Like Teen Spirit | Nirvana | 269 | 5 |
| Money | Pink Floyd | 15761 | 9 |
| In the Air Tonight | Phil Collins | 50420 | 9 |
| Rosanna | Toto | 19993 | 18 |

## Known issues / not yet implemented

* **Ties**: stored in IR, validated for same-instrument; arcs not yet emitted
* **Dynamics**: `velocity` stored in IR but not emitted to LilyPond
* **`tripletFeel`**: present in Rosanna/Money JSON, ignored (low priority)
* **YouTube sync**: IR fields exist but not populated (Milestone 6)

## Planned features

* **Milestone 6**: Browser grid editor + Tone.js playback + YouTube sync
* **Milestone 7**: Tie arcs, dynamics, notation polish

## About

Produce high-quality drum tabs using LilyPond based on Songsterr data.
