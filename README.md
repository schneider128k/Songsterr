# Songsterr drum-tab pipeline

Convert a Songsterr drum tab into a LilyPond-engraved PDF, or play it back
in the browser with the engraved score visible alongside.

## What this does

Given either a Songsterr song-page URL or a CDN JSON URL, the pipeline
walks the tab data, builds an intermediate representation (IR), caches
it, and emits LilyPond source. From the same IR it can produce:

* a **PDF** (via `main.py`) — for printing or filing;
* an **interactive browser player** (via `player.py`) — Tone.js synth
  audio with the LilyPond-engraved sheet music shown on the same page.

The PDF and the browser SVG are compiled from byte-identical .ly source,
so what you hear and what you see match exactly.

## Requirements

* Python 3.10+
* LilyPond 2.24+ on the path, or set `LILYPOND_BIN` to its location
* `pip install -r requirements.txt`

On Windows, with LilyPond installed at `C:\LilyPond\lilypond-2.24.4\`:

```cmd
set LILYPOND_BIN=C:\LilyPond\lilypond-2.24.4\bin\lilypond.exe
```

## CLI: PDF compilation (`main.py`)

```
python main.py <songsterr-page-url-or-cdn-url>           # compile to PDF
python main.py <url> --no-drum-key                       # suppress legend
python main.py <url> --with-breaks                       # legacy section layout
```

The PDF lands in `scores/<Artist>_<Title>_drums.pdf` and the .ly source
next to it.

## CLI: browser player (`player.py`)

```
python player.py <songsterr-page-url-or-cdn-url>         # fetch+parse, play
python player.py <songId>_<partId>                       # play cached score
python player.py <songId>                                # play if 1 cached part
python player.py --list                                  # list cached scores
```

Flags:

| Flag             | Effect                                                    |
|------------------|-----------------------------------------------------------|
| `--no-svg`       | skip LilyPond SVG compilation (fast startup, no score UI) |
| `--no-drum-key`  | suppress the Drum Key legend in the rendered score        |
| `--with-breaks`  | legacy section-aware layout (forced break every 4 bars)   |
| `--no-browser`   | don't auto-open the browser                               |
| `--port <N>`     | listen on `<N>` instead of 8765                           |

The server runs on `http://127.0.0.1:8765` and opens automatically. The
page shows a dark control panel (Play / Pause / Stop, bar counter,
section marker, time signature, tempo, progress bar) above a white sheet
of LilyPond-engraved music.

Press Ctrl+C in the terminal to stop the server.

### Caveats

* Drum sounds are Tone.js synthesisers, not samples — diagnostic, not
  realistic. Sample-based playback is on the roadmap (Milestone 6d).
* SVG compilation costs ~1–3 s per startup. Use `--no-svg` to skip.
* LilyPond's SVG output does not embed text fonts; tempo numbers and
  bar labels render in the browser's default font. Music glyphs (note-
  heads, beams, clefs) are full vector — pixel-identical to the PDF.

## Project structure

```
.
├── ir.py            IR dataclasses (Score, Measure, Event, DrumNote, TempoChange)
├── parser.py        Songsterr JSON → IR
├── cache.py         IR persistence to db/<songId>_<partId>.json
├── emitter.py       IR → LilyPond source
├── lilypond_utils.py LilyPond binary discovery and version probe
├── cdn_resolver.py  Songsterr page URL → CDN JSON URL (M5)
├── pipeline.py      orchestrator: fetch_and_parse, compile_to_pdf, compile_to_svg
├── main.py          PDF CLI
├── player.py        browser-player HTTP server (M6a/6b)
├── player.html      player UI: dark controls + light sheet-music panel
├── player.js        Tone.js scheduling, UI loop, SVG fetch+inline
├── apply_update.py  apply update_vN.zip with backups
├── flush_cache.py   wipe db/
├── requirements.txt
├── db/              cached IR JSON, gitignored
└── scores/          generated .ly, .pdf, .svg, gitignored
```

## How it works (pipeline)

1. `fetch_and_parse(url)` — accepts a CDN URL or page URL. Page URLs go
   through `cdn_resolver.resolve_cdn_url()` first. Returns a `Score`
   IR, caching to `db/<songId>_<partId>.json` on first fetch.
2. `compile_to_pdf(score)` or `compile_to_svg(score)` — both call the
   shared `_emit_ly_file()` helper to produce a single .ly file, then
   invoke LilyPond. PDF mode uses the default backend; SVG mode uses
   `-dbackend=svg -dno-point-and-click` (not the Cairo backend, which
   would block forward compatibility with Milestone 6c).
3. `player.py` precomputes a JSON-clean schedule with `seconds_at()`
   for every event, sends it to the browser, and serves SVG pages on
   `/svg/<i>`.

## Testing

```
python test_player_smoke.py      # 6 build_schedule tests
python test_player_http.py       # 3 HTTP layer tests
python test_v37_svg.py           # 7 SVG-specific tests
```

All 16 tests should pass without LilyPond installed (LilyPond is mocked
in the SVG tests).

## Roadmap

| Milestone | Status   | Description                                    |
|-----------|----------|------------------------------------------------|
| 1–5       | done     | IR, parser, emitter, cache, CDN resolution    |
| 6a        | done     | Browser playback (synth audio)                |
| 6b        | done     | LilyPond SVG sheet music in player            |
| 6c        | next     | Playback cursor highlighting current notehead |
| 6d        | optional | Sample-based playback                         |
| 6e        | planned  | Editing surface (note clicks or grid)         |
| 6f        | planned  | Structural edits                              |
| 6g        | planned  | YouTube playback sync                         |
| 7         | planned  | Notation polish (tie arcs, dynamics)          |

See [`LOGBOOK.md`](LOGBOOK.md) for the detailed history.
