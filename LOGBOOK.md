# Logbook

## Milestone 1 — Colab prototype (completed)

Built a working end-to-end pipeline in a Google Colab notebook:
`ir.py`, `parser.py`, `cache.py`, `emitter.py`. Tested on 5 songs.

---

## Milestone 2 — Desktop project (completed)

`lilypond_utils.py`, `pipeline.py`, `main.py`, `.gitignore`, `requirements.txt`,
`README.md`. Pushed to <https://github.com/schneider128k/Songsterr>

---

## Milestone 3 — Windows end-to-end verification (completed)

LilyPond 2.24.4 at `C:\LilyPond\lilypond-2.24.4\`, `LILYPOND_BIN` env var set.
Tested Wave of Mutilation and Into the Fire — clean PDFs, no bar check warnings.

---

## Milestone 4 — Systematic testing and parser/emitter fixes (completed)

### Utility scripts

* `apply_update.py`: applies versioned `update_vN.zip`, backs up replaced files
* `flush_cache.py`: deletes all cached score JSONs from `db/`

### Songs tested and confirmed working

Square Hammer (Ghost), Smells Like Teen Spirit (Nirvana), Wave of Mutilation (Pixies)

### parser.py fixes (updates v1–v15, v19, v27)

* Full GM map rewritten with canonical LilyPond drum names throughout
* MIDI 37 → `sidestick`, MIDI 41 → `lowfloortom`, MIDI 92 → `halfopenhihat`
* MIDI 48 → `hightom`, MIDI 50 → `hightom`
* Fret 27 → `bassdrum` (CR-78 bass), Fret 93 → `ridecymbal` (Songsterr ext.)
* `anacrusis`/pickup bar duration fixed
* Ties: `DrumNote.tie` field added; parser reads it
* v8 grace note cursor handling fixed

### emitter.py fixes (updates v1–v27)

* Single voice `\stemDown`, flat beams — no phantom rests
* Snare position: `+1` (space between lines 3 and 4)
* Pickup bar: rest-only measure with different time sig emits `\partial`
* Tie validation: only emit `~` when tied note's lily name in next event
* onBeat grace notes: emit `\appoggiatura { note8 }` only (no double note)
* Drum Key legend appended by default (suppress with `--no-drum-key`)

---

## Milestone 4 continued — Layout polish (updates v29–v32)

* `ragged-right = ##t`, `MAX_MEASURES_PER_LINE = 4` forced `\break` after every
  4 measures, section breaks for sections of ≥ 3 measures.

---

## Milestone 5 attempt #1 — CDN URL automation (update v33, failed live test)

Two-strategy resolver shipped speculatively without live API access. Both
strategies missed the actual data path:

* `/api/meta/{songId}/revisions` revision summaries don't carry the token.
* Songsterr is not Next.js — there is no `__NEXT_DATA__` script tag.

---

## Milestone 5 — CDN URL automation (completed, update v34)

The 21-character revision token is the `image` field on the song's
current-revision metadata, returned by `GET /api/meta/{songId}` (the same
endpoint already used to fetch title/artist).

Resolver rewritten with Strategy A on `/api/meta/{songId}` plus a curl-based
page-HTML fallback (Strategy B) that reads `<script id="state">` to get the
same fields when the API ever drifts again.

Live-tested on Wave of Mutilation (Pixies): produces the expected CDN URL
byte-for-byte in one API call.

---

## Milestone 5 follow-ups (completed, update v35)

### Bug 1: Strategy A missing partId on raw API responses

Eye of the Tiger exposed an inconsistency between two shapes of meta data
that v34 had assumed were equivalent:

* The page-state form (`<script id="state">.meta.current.tracks`) injects an
  explicit `partId` field on each track entry — that's what we tested v34
  against.
* The raw API form (`/api/meta/{songId}.tracks`) does NOT include `partId`.
  Songsterr's frontend code synthesises it from the array index when it
  hydrates the page state.

v34's resolver returned `None` from `_build_cdn_url_from_meta` when the drum
track had no `partId`, forcing fallback to Strategy B. v35 mirrors the
frontend's behaviour: a new `_track_part_id(track, index)` helper returns
the explicit partId if present, otherwise the array index.

### Bug 2: v8 acciaccatura duplicate-note emission

Eye of the Tiger triggered 6 bar-check warnings. Tracing m.38: the v8 grace
event has duration 1/64, which the cursor logic correctly skipped, but
`_event_to_token` for `grace_type='before'` always emitted both the
`\acciaccatura { ... }` prefix AND a real note of `ev.duration` length —
the same fix v32 applied to `'on'` was never carried over to `'before'`.

v35: `_event_to_token` distinguishes v5 flam (real duration → grace + real
note) from v8 acciaccatura (near-zero duration → grace only) at the
shared `V8_GRACE_DUR_THRESHOLD = 1/32`.

### Layout: auto_layout default

`emit_lilypond` gains `auto_layout: bool = True`. Default produces compact
output that fills page width naturally. `--with-breaks` restores the v32
section-aware behaviour.

### Validation

* 18 offline tests (test_v35.py).
* End-to-end re-emit of Eye of the Tiger from cached IR: 0 forced breaks
  with auto_layout=True (vs 29 with auto_layout=False); no duplicate-note
  pattern in any of the 6 previously-warning measures.
* **Live test on Windows: confirmed.** Eye of the Tiger via Strategy A in
  one API call (partId=8, no Strategy B fallback), PDF compiled with no
  bar-check warnings on any of the 6 previously-warning measures.
  Wave of Mutilation regression check clean (auto-layout default).

### Files changed in v35

* `emitter.py`, `pipeline.py`, `main.py`, `cdn_resolver.py`.

---

## Milestone 6a — Browser playback MVP (completed, update v36)

First Milestone 6 deliverable: read-only browser playback of any cached
score, intended both as a standalone listening tool and as an audible
audit of the parsed IR.

### Architecture

* `python player.py <target>` resolves URL / `<songId>_<partId>` / `<songId>`,
  loads via `pipeline.fetch_and_parse()` or `cache.load_score()`, builds
  a flat schedule, serves a single-page UI from `http.server`.
* Schedule walks IR once, calls `Score.seconds_at()` for each event,
  outputs `{seconds, midi: [int, ...], grace_v8: bool}`. Fractions never
  reach the browser.
* Browser uses Tone.js 14.8 from cdnjs. One synth per category (kick,
  snare, sidestick, hatClosed, hatOpen, tom, crash, ride). Synth-based,
  not sampled — diagnostic, not realistic.
* v8 acciaccaturas (`grace_v8: true`) scheduled 30 ms early so they
  sound before the beat.

### Validation (v36)

* 6 offline `build_schedule` tests + 3 HTTP-layer tests, all pass.
* **Live test on Windows: confirmed.** *Wave of Mutilation* through its
  four time signatures (1/4, 4/4, 6/4, 2/4); *Eye of the Tiger* via
  Strategy A fresh-fetch; bar counter, time signature, and tempo display
  track correctly during playback.

### Files added in v36

`player.py`, `player.html`, `player.js`. `ir.py`, `parser.py`, `cache.py`,
`emitter.py`, `pipeline.py`, `main.py`, `cdn_resolver.py`,
`lilypond_utils.py`, `apply_update.py`, `flush_cache.py` unchanged.

---

## Milestone 6b — Sheet music in the browser (completed, update v37)

Second Milestone 6 deliverable: render the LilyPond-engraved score as
SVG and display it in the player UI, alongside the existing playback
controls. The user can now hear and see the score simultaneously.

### Why LilyPond SVG (not AlphaTab / VexFlow / OSMD)

LilyPond's own SVG backend reuses 100% of the existing engraving logic —
including all v35 fixes (acciaccatura/flam distinction, drum positions,
tie validation, the Drum Key legend). The on-screen score is byte-equal
to the PDF a user would print.

The alternatives (AlphaTab, VexFlow, OpenSheetMusicDisplay) would each
require a new IR-to-format emitter, re-deriving the bug fixes that the
LilyPond emitter has accumulated. Net effort: significantly larger; net
quality: no better than LilyPond's. Deferred.

### Why `-dbackend=svg` (not `-dbackend=cairo`)

LilyPond 2.24 ships two SVG backends. The Cairo backend produces nicer
SVG and is faster, but doesn't yet support the `output-attributes`
property — the mechanism for tagging individual noteheads with stable
IDs/classes for future JS interactivity (Milestone 6c, playback cursor).
We accept slightly less polished SVG today to keep that door open.

### Architecture

```
python player.py <target>
  ├── resolve_target()          (unchanged from v36)
  ├── pipeline.compile_to_svg() ── lilypond -dbackend=svg → N SVG pages
  ├── build_schedule(svg_pages=N)
  └── ThreadingHTTPServer
        ├── /              → player.html  (sheet music + dark control panel)
        ├── /player.js     → player.js    (Tone.js + SVG fetch+inline)
        ├── /api/score     → schedule JSON, includes svg_pages count
        └── /svg/<i>       → i-th LilyPond SVG, image/svg+xml
```

`pipeline.py` gains:
* `compile_to_svg(score, output_dir, drum_key, auto_layout) -> list[str]`,
  invokes LilyPond once with `-dbackend=svg -dno-point-and-click`, globs
  the output directory for `<basename>*.svg`, returns paths in page order.
* `_emit_ly_file()` and `_report_lily_output()` helpers shared between
  `compile_to_pdf` and `compile_to_svg`. Guarantees the PDF and the
  on-screen SVG are compiled from byte-identical .ly source.
* `_svg_page_index()` sort key handles both LilyPond filename forms:
  `<base>.svg` (single-page) sorts as 0, `<base>-N.svg` (multi-page)
  sorts as N.

`player.py` invokes `compile_to_svg` after resolving the score and before
starting the HTTP server, then pins the resulting paths to the handler
class. New CLI flags:
* `--no-svg`: skip LilyPond compilation (fast startup, no sheet music)
* `--no-drum-key`: forwarded to the emitter
* `--with-breaks`: forwarded to the emitter

If LilyPond compilation fails for any reason, the server still starts and
serves playback — the sheet-music panel shows an error message.

### Browser side

* SVG pages fetched in parallel via `Promise.all` after `/api/score`
  returns. Inlined into `<div class="sheet-page">` containers via
  `innerHTML`, so 6c can later attach event handlers to noteheads.
* Light "paper" panel under the dark controls — sheet-music-on-a-desk
  feel. CSS `max-width: 100%; height: auto` lets each SVG scale to fit.

### Validation (v37)

* 7 SVG-specific tests (test_v37_svg.py): sort key for both single- and
  multi-page filenames; `compile_to_svg` glob+sort behaviour; stale-page
  cleanup between runs; LilyPond command-line includes `-dbackend=svg`
  and `-dno-point-and-click` (and excludes `-dbackend=cairo`); raises
  cleanly if LilyPond produces no output; `/svg/<i>` HTTP endpoint
  serves the right file with `image/svg+xml`, returns 404 for
  out-of-range and non-numeric indices.
* 6 v36 tests still pass against the new `build_schedule(svg_pages=...)`
  signature (default 0 preserves old behaviour).
* 3 HTTP-layer tests still pass.
* **Live test on Windows: confirmed in the v38/v39 session** —
  `python player.py 16093_3` (Wave of Mutilation) renders the engraved
  sheet music under the dark control panel with audio playback running
  alongside, no errors at SVG-compile or runtime.

### Files changed in v37

* `pipeline.py` — `compile_to_svg`, `_emit_ly_file`, `_report_lily_output`,
  `_svg_page_index` helpers, `compile_to_pdf` refactored to use them
* `player.py` — invokes `compile_to_svg` at startup, serves `/svg/<i>`,
  threading-safe class state for `svg_pages`, new CLI flags
* `player.html` — sheet-music light panel below the dark control panel
* `player.js` — `loadSheetMusic()` fetches and inlines SVG pages

`ir.py`, `parser.py`, `cache.py`, `emitter.py`, `main.py`,
`cdn_resolver.py`, `lilypond_utils.py`, `apply_update.py`,
`flush_cache.py` unchanged. **Cache flush not required** — IR layout
unchanged.

### Known approximations

* Per LilyPond docs: SVG output does not embed text fonts. Tempo numbers,
  bar numbers, and section markers render in the browser's default font;
  music glyphs are full vector. Less elegant than the PDF for text but
  legible.
* Compilation cost is paid at every player startup (~1–3 s on a
  modern machine). `--no-svg` opts out for fast launches.

---

## v38 attempt — single-host migration (partial fix, retracted in v39)

This update was applied locally but never pushed to git. It hardcoded a
single new CloudFront host — `d3d3l6a6rcgkaf.cloudfront.net` — replacing
the v34 host `dqsljvtekg760.cloudfront.net`. The hypothesis was that
Songsterr had performed a global migration. That hypothesis was wrong.

### How v38's smoke test caught its own bug

`test_cdn_smoke.py` (introduced in v38, retained in v39) HEAD-probes
three reference songs after resolving them. Output of the first run:

```
--- Wave of Mutilation ---
  BAD (403) — https://d3d3l6a6rcgkaf.cloudfront.net/.../3.json
--- Square Hammer ---
  OK (200)
--- Eye of the Tiger ---
  BAD (403) — https://d3d3l6a6rcgkaf.cloudfront.net/.../8.json
FAIL: 2/3 song(s) broken
```

This is exactly the value the smoke test was designed to provide: it
caught the regression before the patch was committed. The v38 design
itself was the bug, not the smoke test.

### What v38 got wrong

Two architectural flaws revealed by `diagnose8.py`:

1. **Songsterr's CDN migration is gradual, not global.** Some songs
   live on the new host, others on the old; both serve concurrently.
   Wave of Mutilation, Eye of the Tiger → old host. Square Hammer →
   new host.
2. **There is no field anywhere that signals which host serves a given
   song.** Not in `/api/meta`, not in `state.meta.current`, not in
   dns-prefetch. The SPA's JS bundle hardcodes the host list and probes
   them at runtime. We must mirror that approach.

### What we learned about the data shape (still useful)

`diagnose8.py` also confirmed two pieces of v34/v35 lore:

* The `/api/meta/{songId}.tracks` and
  `state.meta.current.tracks` lists are byte-equivalent for a given
  song; the only difference is that the page-state form synthesises
  `partId = array_index` while the API form omits the field.
  `_track_part_id(track, index)`'s index fallback (v35) is correct.
* Eye of the Tiger now has 10 tracks, not 9 — Songsterr added a
  Tambourine track at index 9, also `instrumentId=1024`. The resolver's
  "first instrumentId==1024" heuristic still picks the kit at index 8,
  which is what we want for a "drum tab." A user who specifically wants
  the tambourine can pass `s89089t9` in the URL.

---

## v39 — CDN host migration hotfix (completed, supersedes v38)

### Fix

Replace the single `DEFAULT_CLOUDFRONT_HOST` constant with a
`KNOWN_CDN_HOSTS` tuple, ordered newest-first. Add `_validate_cdn_url`
(HEAD probe → bool) and `_try_hosts_for(song_id, rev, image, partId)`
helpers. Refactor `_build_cdn_url_from_meta` to remove its `host`
parameter and instead probe each host in `KNOWN_CDN_HOSTS` until one
returns 200, returning the URL on that host.

`DEFAULT_CLOUDFRONT_HOST` is retained as an alias pointing at
`KNOWN_CDN_HOSTS[0]` for backwards compatibility with any external code
that imports it.

When Songsterr migrates again — adds a third host, drops the old one,
or anything else — the maintenance steps are:

1. `python test_cdn_smoke.py` to confirm the problem.
2. Open a song page in DevTools → Network → filter cloudfront → reload;
   note the host of any `<songId>/.../<partId>.json` request.
3. Prepend that host to `KNOWN_CDN_HOSTS` in `cdn_resolver.py`.
4. Re-run the smoke test.

When the older host eventually goes dark (returns 4xx for everything),
remove it from the tuple. Until then, leaving it in costs nothing
beyond a single failed HEAD per first-fetch on new-host songs.

### Validation

* 11 unit tests (test_v39_resolver.py): try-hosts ordering, fall-back on
  404, both-hosts-fail returns None, network-unreachable returns None,
  URL path layout, six end-to-end shape tests against synthesized
  `meta` dicts representing Wave of Mutilation / Square Hammer /
  Eye of the Tiger, including the Eye-of-Tiger kit-vs-tambourine
  default-and-hint distinction.
* `test_cdn_smoke.py` (live, 3 songs) — pending live confirmation on
  Windows.

### The v38 → v39 lesson

The v38 smoke test caught the bug in its own patch, in 2 seconds, before
the bug shipped. That's the value: not "tests prevent bugs" but "tests
shorten the discovery loop." The v34 design treated the CDN host as
implicitly constant; v38 treated it as a single mutable value;
v39 treats it as a list to probe. Each step is a more honest model
of what Songsterr actually does. Architecture that mirrors the true
shape of the world doesn't need to be re-fixed every six months.

The diagnostic chain (diagnose4 → diagnose6 → diagnose7 → diagnose8)
also worked as the project's debugging rule prescribes: each probe
narrowed the hypothesis space using read-only data, and the patch
was written only after the hypothesis was nailed down. v33's
"shipped speculatively" mistake was not repeated.

### Files changed in v39

* `cdn_resolver.py` — v38's host change retained; `_build_cdn_url_from_meta`
  now probes `KNOWN_CDN_HOSTS` in order via the new `_validate_cdn_url`
  and `_try_hosts_for` helpers. The `host` parameter is removed.
* `test_v39_resolver.py` — new, 11 unit tests with mocked HTTP.
* `test_cdn_smoke.py` — same as v38 (carried in this zip so v39 is
  self-sufficient when applied directly from a v37 baseline).

`ir.py`, `parser.py`, `cache.py`, `emitter.py`, `pipeline.py`,
`main.py`, `player.py`, `player.html`, `player.js`,
`lilypond_utils.py` are unchanged. **Cache flush not required.**

---

## Current milestone — Milestone 6c: Playback cursor on the SVG (next)

Now that sheet music and audio coexist in one window, the natural next
step is synchronising them: as playback advances, highlight the current
notehead (or the current measure barline) so the eye can follow the ear.

Architecture sketch:

* In `emitter.py`, override `NoteHead.output-attributes` (or attach a
  `before-line-breaking` engraver hook) to tag each notehead with
  `class="note"` and `data-pos="{position}"` (whole-notes from score
  start, as a Fraction-as-string). Bar lines get tagged similarly with
  `data-bar="{index}"`.
* `player.js` reads the running `Tone.Transport.seconds`, binary-searches
  the schedule's `events[]` to find the active event index, and toggles
  CSS classes on the matching SVG group. Active event = `seconds <=
  transport.seconds < next_event.seconds`.
* CSS: `.sheet-page g.note.active { fill: var(--accent); }` — a colour
  change on the LilyPond fill.

Risks/uncertainties to investigate before coding:

1. Does `output-attributes` survive through the multi-page page break?
   I.e., do all noteheads on page 2 also get the attribute?
2. Tempo-map drift: `Score.seconds_at()` and the emitter agree on event
   ordering, but not necessarily on per-event start times if the parser's
   notion of `Event.position` differs subtly from the emitter's notation
   width. May need a small tolerance.
3. Performance: 800-event songs with 60fps update are fine, but DOM
   class toggling on every animation frame is wasteful. The right thing
   is to attach the class only on event boundary crossings.

## Planned future milestones

**Milestone 6d — Sample-based playback (optional)**

Replace Tone.js synth dispatch with `Tone.Sampler`/`Tone.Players` reading
from a CC0 drum kit. Source kit selection and distribution (samples in
repo vs lazy download from a CDN) need decisions; code change is
modest. Cosmetic improvement, not a correctness one.

**Milestone 6e — Editing surface**

Either via clicking noteheads in the inlined SVG (with `output-attributes`
already in place from 6c, this becomes accessible), or via a separate
grid pane. Decision deferred until 6c is in.

**Milestone 6f — Structural edits**

Section markers, time-signature changes, insert/delete measure, change
tempo. Requires the inverse of `cache.score_to_dict()` (`dict_to_score()`
already exists) and a write path through the cache.

**Milestone 6g — YouTube sync**

Embedded player + playhead synchronised with the score timeline.
`Score.youtube_id` and `Score.youtube_offset` IR fields exist already.

**Milestone 7 — Notation polish**

* Tie arcs emitted to LilyPond
* Dynamics (`velocity`) emitted
