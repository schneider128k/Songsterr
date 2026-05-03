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
track had no `partId`, forcing fallback to Strategy B — which worked but is
slower (subprocess + HTML parse). v35 mirrors the frontend's behaviour: a
new `_track_part_id(track, index)` helper returns the explicit partId if
present, otherwise the array index. Strategy A now succeeds on songs in
either shape.

### Bug 2: v8 acciaccatura duplicate-note emission

Eye of the Tiger triggered 6 bar-check warnings (LilyPond reporting the bar
overflowed by 1/64, 1/32, 3/64, 1/16, 5/64, 3/32 in different measures).
Tracing m.38 through the IR:

```
events: 6 × 1/8 (regular hits) + grace[1/64] + 1/4 (final hit)
expected bar duration: 1
```

The grace event has duration 1/64 — Songsterr's v8 representation marks pure
ornaments with a "near-zero" duration the emitter must NOT advance through.
`_emit_measure` already had this logic for cursor management
(`GRACE_DUR_THRESHOLD = 1/32`).

But `_event_to_token` for `grace_type='before'` always emitted both the
`\acciaccatura { ... }` prefix AND a real note of `ev.duration` length.
The same fix v32 applied to `grace_type='on'` (emit only the prefix, no
duplicate note) was never carried over to the `'before'` case.

v35: `_event_to_token` now distinguishes v5 flam (real duration → grace +
real note, the original behaviour) from v8 acciaccatura (near-zero
duration → grace only). Threshold is the same `V8_GRACE_DUR_THRESHOLD =
1/32` shared with `_emit_measure` so the two stay consistent.

End-to-end check: re-emitting Eye of the Tiger from the cached IR with v35
produces a clean .ly with no acciaccatura/duplicate-small-note pattern in
any of the 6 previously-warning measures.

### Layout: auto_layout default

User feedback: the v32 layout (forced `\break` every 4 measures plus
section breaks) was producing scores too long to be useful — multiple
nearly-empty lines and visible "stubs" at the end of each forced break.

v35: `emit_lilypond` gains an `auto_layout: bool = True` parameter. When
`True` (default), no `\break` is emitted and LilyPond decides line-breaking
based on page width. This produces compact output that fills each line
naturally.

When `False`, the v32 behaviour is restored (section breaks ≥ 3 measures,
break every 4 measures). Available via `python main.py <URL> --with-breaks`.

The "stub at end of line" the user observed was an artifact of the forced
`\break`: with `ragged-right = ##t` and a forced break, the staff is drawn
to its content width plus a small terminating segment. Without forced
breaks, LilyPond chooses break points where the staff fills the line, and
the artifact disappears.

### Validation

* 18 offline tests (test_v35.py): emitter auto_layout flag both ways,
  v8/v5 grace distinction at the 1/32 threshold, m.38 bar-duration
  regression, partId-from-index fallback, explicit-partId precedence.
* End-to-end re-emit of Eye of the Tiger from cached IR: 0 forced breaks
  with auto_layout=True (vs 29 with auto_layout=False); no duplicate-note
  pattern in any of the 6 previously-warning measures.
* Live test on Windows pending.

### Files changed in v35

* `emitter.py` — auto_layout param + V8_GRACE_DUR_THRESHOLD constant +
  acciaccatura/flam distinction in `_event_to_token`
* `pipeline.py` — auto_layout pass-through to compile_to_pdf
* `main.py` — `--with-breaks` flag
* `cdn_resolver.py` — `_track_part_id` helper, used by `_find_drum_track`
  and `_build_cdn_url_from_meta`

`ir.py`, `parser.py`, `cache.py`, `lilypond_utils.py`, `apply_update.py`,
`flush_cache.py` are unchanged. **Cache flush not required** — IR layout
unchanged.

---

## Current milestone — Milestone 6: Browser-based grid editor (next)

* `python editor.py` opens a local web UI with a drum grid
* Toggle hits, edit section markers, change time signatures, compile to PDF
* Browser playback (Tone.js), YouTube sync

## Planned future milestones

**Milestone 7 — Notation polish**

* Tie arcs emitted to LilyPond
* Dynamics (`velocity`) emitted
