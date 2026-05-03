# Songsterr Drum Tab → PDF Pipeline

Fetches drum tab data from Songsterr's CDN, parses it into an internal
representation (IR), caches it locally, and compiles it to a PDF score
via LilyPond. Also provides browser-based playback of cached scores
(Milestone 6a).

## Pipeline

```
Songsterr page URL ─┐
                    ├──▶  CDN URL  ──▶  Songsterr JSON (v5 or v8)  ──▶  Score IR  ↔  db/ cache
CDN URL  ───────────┘                                                          │
                                                                               ▼
                                                                        score.ly  ──▶  LilyPond  ──▶  score.pdf
                                                                               │
                                                                               └──▶  player.py  ──▶  browser playback
```

The page-URL → CDN-URL step (Milestone 5) is handled by `cdn_resolver.py`.
Browser playback (Milestone 6a) is handled by `player.py`.

## Usage

### PDF generation

```
pip install requests
python main.py <URL>                     # fetch, parse, compile to PDF
python main.py <URL> --no-drum-key       # skip the Drum Key legend
python main.py <URL> --with-breaks       # legacy layout: forced section breaks
                                         # + every-4-measures (pre-v35)
python main.py <URL> --probe             # diagnostic — dump what the resolver sees
python main.py                           # list cached scores
```

`<URL>` may be either a Songsterr page URL or a direct CDN URL:

```
python main.py https://www.songsterr.com/a/wsa/pixies-wave-of-mutilation-drum-tab-s16093
python main.py https://www.songsterr.com/a/wsa/...-drum-tab-s16093t3        # multi-track: explicit partId
python main.py https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json
```

### Browser playback (Milestone 6a)

```
python player.py <URL>                   # fetch+parse if not cached, then play
python player.py <songId>_<partId>       # play a specific cached score
python player.py <songId>                # play, if exactly one part is cached
python player.py --list                  # list cached scores and exit
python player.py <URL> --no-browser      # don't auto-open the browser
python player.py <URL> --port 9000       # use a different port (default 8765)
```

Opens a local UI at `http://127.0.0.1:8765/` with play/pause/stop, a bar
counter, current time signature, current tempo, and a progress bar.
Drum sounds are Tone.js synths, not samples — the audio is diagnostic
(useful for ear-checking the parsed IR), not realistic. Press Ctrl+C
in the terminal to stop the server.

#### Layout — auto vs manual breaks (PDF)

Default (v35+): LilyPond decides line breaking based on page width, fitting
as many measures per line as fit naturally. Produces compact scores.

`--with-breaks` restores the pre-v35 behaviour: a forced `\break` before
every section of ≥ 3 measures, plus a forced break after every 4 measures.
Useful when you want every section on its own line(s) for readability.

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
   token) + the drum track's `partId` (or its array-index, if the API
   response omits the explicit field — Songsterr's frontend synthesises it
   from the index).
2. **Page HTML scrape via `curl`** (fallback). Songsterr embeds the same
   data in `<script id="state" type="application/json">…</script>` on every
   page; we extract `state.meta.current` and use the same logic. We use
   `curl` rather than `requests` because Cloudflare's HTTP 103 Early Hints
   in front of the page route is mishandled by Python's HTTP libraries.

If the URL contains a `t<partId>` suffix (e.g. `...s16093t3`), that hint
overrides drum-track auto-detection — useful for multi-drummer songs.

## Project structure

```
main.py             CLI entry point (--no-drum-key, --with-breaks, --probe)
pipeline.py         fetch_and_parse(), compile_to_pdf(), run_pipeline()
cdn_resolver.py     resolve_cdn_url(), probe_page(), URL classifiers
lilypond_utils.py   auto-detect LilyPond binary + version
ir.py               Score / Measure / Event / DrumNote / TempoChange dataclasses
parser.py           parse_json() — handles Songsterr JSON v5 and v8
cache.py            save_score() / load_score() / list_cached() / score_to_dict()
emitter.py          emit_lilypond() — Score IR → LilyPond source
player.py           local web server: browser playback of cached scores (M6a)
player.html         playback UI (single page, loads Tone.js from cdnjs)
player.js           Tone.js scheduling + synth dispatch + UI loop
apply_update.py     permanent: applies update_vN.zip, backs up old files
flush_cache.py      permanent: deletes all cached score JSONs from db/
db/                 local JSON cache (gitignored)
scores/             output PDFs and .ly files (gitignored)
```

## Dependencies

* Python 3.10+
* `requests` (`pip install requests`)
* LilyPond 2.24+ — <https://lilypond.org/download.html>
* `curl` on PATH (only used by the resolver's Strategy B fallback;
  Windows 10+ ships with it)
* Modern browser (for `player.py`) — uses Tone.js loaded from cdnjs, no
  bundler or local install needed.

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
* Bar numbers every 4 measures + every system start
* **Drum Key legend** appended by default (suppress with `--no-drum-key`):
  shows one labeled notehead per instrument used, top→bottom on staff
* **Auto-layout** by default: LilyPond chooses line breaks
  (use `--with-breaks` for the legacy section-aware layout)

## Browser playback synth choices (Milestone 6a)

| Drum category | MIDI | Tone.js synth | Notes |
| --- | --- | --- | --- |
| Kick | 35, 36 | MembraneSynth (C1) | low fundamental, fast pitch decay |
| Snare | 38, 40 | NoiseSynth + 2.2 kHz HP | white noise burst |
| Sidestick | 37 | MembraneSynth (C4) | very short click |
| Closed hat | 42, 44 | NoiseSynth + 7 kHz HP | very short envelope |
| Open hat | 46, 92 | NoiseSynth + 6 kHz HP | longer decay |
| Toms | 41–50 | MembraneSynth, varying pitch | F1 (low floor) → C3 (high) |
| Crash | 49, 52, 55, 57, 59 | MetalSynth | bright, long decay |
| Ride | 51, 53 | MetalSynth | brighter, shorter than crash |

Synthesised, not sampled. Audio is diagnostic, not realistic.

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
| Eye of the Tiger | Survivor | 89089 | 8 |

## Known issues / not yet implemented

* **Ties**: stored in IR, validated for same-instrument; arcs not yet emitted
* **Dynamics**: `velocity` stored in IR but not emitted to LilyPond, ignored in playback
* **`tripletFeel`**: present in Rosanna/Money JSON, ignored (low priority)
* **Tempo ramps** (`TempoChange.linear`): stored, not honoured by `seconds_at`;
  ignored in both PDF and playback. Step-tempo only.
* **YouTube sync**: IR fields exist but not populated (Milestone 6e)
* **Playback realism**: synth-only; no sample kit option (Milestone 6 follow-up if needed)

## Planned features

* **Milestone 6b**: Read-only grid viewer (IR → instrument-row grid in browser)
* **Milestone 6c**: Hit toggling + recompile (first write path)
* **Milestone 6d**: Structural edits (sections, time sigs, measure insert/delete, tempos)
* **Milestone 6e**: YouTube sync — embedded player + playhead synchronisation
* **Milestone 7**: Tie arcs, dynamics, notation polish

## About

Produce high-quality drum tabs using LilyPond based on Songsterr data,
plus browser-based playback of the parsed scores.
