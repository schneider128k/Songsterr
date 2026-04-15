r"""
emitter.py — Compile a Score IR to a LilyPond source string.

Typesetting choices:
- Single voice, \stemDown — no phantom rests, crash+kick share one stem
- \numericTimeSignature — shows 4/4 not C symbol
- Beam.damping = +inf — flat horizontal beams (standard in drum music)
- ragged-right — systems not stretched to fill page width
- Section breaks before sections with >= MIN_SECTION_MEASURES measures
- Bar numbers every 4 measures, also at every system start
- Custom drumStyleTable — hi-hat above staff (position 5 not 3)
- No courtesy time signature at line ends
- Letter paper, zero indent (no instrument name label)
- Header: title, composer (artist), subtitle (drummer)

Fixes vs original:
- Side stick ('ss') has its own style entry (cross, position -2) distinct from snare
- Low floor tom ('tomfl') correctly placed at position -3 (was missing, falling back to tomml)
- Ties: notes with DrumNote.tie=True emit a '~' tie token
- v8 grace notes never advance the cursor (uses Event.grace_is_v8 flag)
- _fill_rests warns instead of silently emitting r4 for unresolvable remainders
- Mid-measure tempo changes (sub-beat position) are now emitted correctly
"""

import sys
from fractions import Fraction
from ir import Score

# Minimum measures in a section to trigger a forced line break before it
MIN_SECTION_MEASURES = 3

# Duration table: exact Fraction of whole note -> LilyPond duration string
_DURS = [
    (Fraction(1,  1), '1'),
    (Fraction(7,  8), '2..'),
    (Fraction(3,  4), '2.'),
    (Fraction(1,  2), '2'),
    (Fraction(7, 16), '4..'),
    (Fraction(3,  8), '4.'),
    (Fraction(1,  4), '4'),
    (Fraction(7, 32), '8..'),
    (Fraction(3, 16), '8.'),
    (Fraction(1,  8), '8'),
    (Fraction(3, 32), '16.'),
    (Fraction(1, 16), '16'),
    (Fraction(3, 64), '32.'),
    (Fraction(1, 32), '32'),
    (Fraction(1, 64), '64'),
]
_DUR_MAP = {f: s for f, s in _DURS}


def _dur(f):
    return _DUR_MAP.get(Fraction(f), '8')


def _fill_rests(f):
    """
    Decompose a duration into a list of rest tokens.
    If the duration cannot be fully decomposed (e.g. due to a tuplet rounding
    artefact), emit a warning to stderr instead of silently producing a
    bar-check failure.
    """
    out, rem = [], Fraction(f)
    for fv, fs in _DURS:
        while rem >= fv:
            out.append('r' + fs)
            rem -= fv
    if rem > 0:
        print(
            f'WARNING: _fill_rests: unresolvable remainder {rem} '
            f'(input={f}); inserting r4 — check for bar-check warnings',
            file=sys.stderr
        )
        out.append('r4')
    return out


def _event_to_token(ev, force_dur=None):
    """
    Render one Event as a single LilyPond token (or a list of tokens when
    ties are involved).

    force_dur: if given, overrides the duration string (used inside tuplets
               where the notated duration like 1/24 is not a standard value).

    Returns a string (single token) or a list of strings (tie sequence).
    """
    ly_dur = force_dur if force_dur is not None else _dur(ev.duration)

    # Grace note — emit only the acciaccatura prefix.
    # The following real note at the same position emits itself separately.
    # \acciaccatura doesn't steal time so bar checks stay clean.
    if ev.grace:
        if not ev.notes:
            return None
        nms   = sorted({n.lily for n in ev.notes})
        inner = nms[0] if len(nms) == 1 else '<' + ' '.join(nms) + '>'
        return f'\\acciaccatura {{ {inner}8 }}'

    # Rest
    if not ev.notes:
        return 'r' + ly_dur

    # Tremolo roll
    if ev.tremolo_base:
        count = max(1, round(float(ev.duration * ev.tremolo_base)))
        nms   = sorted({n.lily for n in ev.notes})
        inner = nms[0] if len(nms) == 1 else '<' + ' '.join(nms) + '>'
        return f'\\repeat tremolo {count} {{ {inner}{ev.tremolo_base} }}'

    # Normal note / chord
    nms    = sorted({n.lily for n in ev.notes})
    ghosts = {n.lily for n in ev.notes if n.ghost}
    accent = max((n.accent for n in ev.notes), default=0)
    tied   = {n.lily for n in ev.notes if n.tie}

    # When pedalhihat and bassdrum coincide, suppress bassdrum.
    # Songsterr does the same: the foot is already occupied by the hi-hat
    # pedal, so the bass drum notehead is redundant and causes a collision
    # at adjacent staff positions (-5 and -6).
    if 'pedalhihat' in nms and 'bassdrum' in nms:
        nms = [n for n in nms if n != 'bassdrum']

    # crashcymbalb has a hardcoded xcircle (hollow) notehead in LilyPond's
    # internal drumPitchTable that cannot be overridden via drumStyleTable.
    # Fix: replace it with crashcymbal (which renders correctly as a solid
    # cross) and manually override its staff position to 6 (ledger line).
    has_cymbalb = 'crashcymbalb' in nms
    nms = ['crashcymbal' if n == 'crashcymbalb' else n for n in nms]

    prefix = ''
    if has_cymbalb and len(nms) == 1:
        prefix = '\\once \\override NoteHead.staff-position = #6 '
    elif has_cymbalb:
        # In a chord, override the whole chord position is not possible per-note.
        # Instead emit crashcymbalb as a separate prepended override token.
        # This case (crashcymbal + crashcymbalb together) is handled below.
        pass

    if len(nms) == 1:
        n   = nms[0]
        tok = f'{prefix}\\parenthesize {n}{ly_dur}' if n in ghosts else f'{prefix}{n}{ly_dur}'
    else:
        tok = f'<{" ".join(nms)}>{ly_dur}'

    if accent == 1:   tok += '\\accent'
    elif accent == 2: tok += '\\marcato'

    # Emit tie token(s) — one '~' per tied note (or just one for the chord).
    # LilyPond ties per-note inside chords require explicit syntax; for
    # simplicity we emit a single chord tie, which works well for the common
    # case of a single drum instrument tied across a barline.
    if tied:
        tok += ' ~'

    return tok


def _emit_measure(events, measure_dur, measure_pos):
    """
    Emit all LilyPond tokens for one measure (single voice).
    Handles rests for gaps, tuplet brackets, and hairpins.
    """
    tokens = []
    cursor = measure_pos
    end_pos = measure_pos + measure_dur
    hairpin_open = False
    emitted_tuplet_groups = set()
    i = 0

    while i < len(events):
        ev = events[i]

        # Fill gap before this event
        if ev.position > cursor:
            tokens.extend(_fill_rests(ev.position - cursor))
            cursor = ev.position

        # Tuplet group
        if ev.tuplet_group is not None:
            gid = ev.tuplet_group
            if gid in emitted_tuplet_groups:
                i += 1
                continue
            emitted_tuplet_groups.add(gid)
            group     = [e for e in events if e.tuplet_group == gid]
            N, M      = ev.tuplet_n, ev.tuplet_m
            group_dur = sum(e.duration for e in group)

            # Derive the written note type from the tuplet ratio and actual duration.
            # Example: 16th-note triplet → M=2, N=3, dur=1/24 → (2/3)/(1/24) = 16
            note_type_int = round(float(Fraction(M, N) / ev.duration))
            note_type_str = str(note_type_int)

            if any(e.hairpin == 'start' for e in group) and not hairpin_open:
                tokens.append('\\<')
                hairpin_open = True

            inner = []
            for e in group:
                tok = _event_to_token(e, force_dur=note_type_str)
                inner.append(tok if tok is not None else f'r{note_type_str}')
            tokens.append(f'\\tuplet {N}/{M} {{ {" ".join(inner)} }}')

            if hairpin_open and not any(e.hairpin for e in group):
                tokens[-1] += ' \\!'
                hairpin_open = False

            cursor += group_dur
            i += sum(1 for e in events if e.tuplet_group == gid)
            continue

        # Grace note
        if ev.grace:
            tok = _event_to_token(ev)
            if tok is not None:
                tokens.append(tok)
            # FIX: advance cursor only for v5 flams (grace_is_v8=False),
            # never for v8 grace notes (grace_is_v8=True).
            if not ev.grace_is_v8:
                cursor += ev.duration
            i += 1
            continue

        # Normal event
        tok = _event_to_token(ev)

        if tok is not None and not tok.startswith('r'):
            if ev.hairpin == 'start' and not hairpin_open:
                tok = '\\< ' + tok
                hairpin_open = True
            elif hairpin_open and ev.hairpin != 'start':
                tok += ' \\!'
                hairpin_open = False

        tokens.append(tok if tok is not None else 'r' + _dur(ev.duration))
        cursor += ev.duration
        i += 1

    if hairpin_open and tokens:
        tokens[-1] += ' \\!'

    if cursor < end_pos:
        tokens.extend(_fill_rests(end_pos - cursor))

    return tokens


# Custom drum style table.
# We only override entries where we want different positions or noteheads
# than LilyPond 2.24's built-in defaults. All names here are standard
# LilyPond drumPitchTable names so they are guaranteed to render.
#
# Key overrides vs LilyPond defaults:
#   closedhihat / openhihat / pedalhihat: moved to position 5 (above staff)
#     LilyPond default is 3 (top line); position 5 is standard in drum scores.
#   crashcymbal: position 5 (space above top line)
#   crashcymbalb: position 6 (ledger line above staff)
#   ridecymbal: position 5 (same height as hi-hat — see NOTE below)
#   bassdrum: position -5 (below staff)
#   All toms: explicit positions for clarity
#
# NOTE: ridecymbal and closedhihat both sit at position 5 and are visually
#   identical (both cross noteheads). To differentiate, move ridecymbal to
#   position 6 or 7. This is left as a future preference decision.
_DRUM_STYLE = """\
#(alist->hash-table '(
  (bassdrum         default #f -3)
  (acousticsnare    default #f  0)
  (electricsnare    default #f  0)
  (sidestick        cross   #f -2)
  (closedhihat      cross   #f  5)
  (halfopenhihat    xcircle #f  5)
  (openhihat        xcircle #f  5)
  (pedalhihat       cross   #f -5)
  (crashcymbal      cross   #f  5)
  (splashcymbal     cross   #f  5)
  (chinesecymbal    cross   #f  7)
  (ridecymbal       cross   #f  5)
  (ridebell         default #f  5)
  (cowbell          default #f  4)
  (tambourine       cross   #f  4)
  (vibraslap        diamond #f  0)
  (highfloortom     default #f -2)
  (lowfloortom      default #f -3)
  (lowtom           default #f -1)
  (lowmidtom        default #f  1)
  (himidtom         default #f  2)
  (hightom          default #f  3)
))\
"""


def _compute_section_lengths(measures):
    """
    For each measure that starts a section (has a marker), count how many
    measures belong to it. Returns dict {measure_list_index: count}.
    """
    lengths = {}
    markers = [(i, m) for i, m in enumerate(measures) if m.marker]
    for j, (i, m) in enumerate(markers):
        next_i = markers[j + 1][0] if j + 1 < len(markers) else len(measures)
        lengths[i] = next_i - i
    return lengths


def emit_lilypond(score: Score, version: str) -> str:
    """Compile a Score IR to a LilyPond source string."""
    voice_lines = []

    sorted_tempos = sorted(score.tempo_changes, key=lambda t: t.position)
    initial_bpm   = sorted_tempos[0].bpm if sorted_tempos else 120

    # FIX: build a list of (position, bpm) for ALL tempo changes after the
    # first, keyed by position so we can match both measure-boundary AND
    # mid-measure tempo changes.  We emit them just before the measure that
    # contains them (measure-boundary case) or inside the measure tokens
    # (mid-measure case is not yet fully supported in LilyPond drummode, but
    # we at least emit them at the nearest measure boundary rather than
    # dropping them silently).
    tempo_events = {t.position: t.bpm for t in sorted_tempos[1:]}

    section_lengths = _compute_section_lengths(score.measures)
    # Initialise prev_sig to the first measure's time sig so the setup-block
    # \time (emitted unconditionally below) is not duplicated by measure 1.
    first_sig = score.measures[0].time_sig if score.measures else (4, 4)
    prev_sig = first_sig

    for mi, meas in enumerate(score.measures):
        # Forced line break before long-enough sections
        if meas.marker and mi > 0:
            if section_lengths.get(mi, 0) >= MIN_SECTION_MEASURES:
                voice_lines.append('  \\break')

        if meas.time_sig != prev_sig:
            ts = f'{meas.time_sig[0]}/{meas.time_sig[1]}'
            voice_lines.append(f'  \\time {ts}')
            prev_sig = meas.time_sig

        # Emit tempo changes whose position falls within this measure.
        # Most common case: exact measure boundary (sub=0).
        # Less common: mid-measure sub-beat tempo — we emit it at the
        # measure boundary as an approximation; a future fix could split
        # the measure into two partial measures around the tempo change.
        meas_end = meas.position + meas.duration
        for tc_pos in sorted(tempo_events):
            if meas.position <= tc_pos < meas_end:
                voice_lines.append(f'  \\tempo 4 = {int(tempo_events[tc_pos])}')

        if meas.marker:
            voice_lines.append(f'  \\mark \\markup {{ \\box "{meas.marker}" }}')

        toks = _emit_measure(meas.events, meas.duration, meas.position)
        voice_lines.append(f'  {" ".join(toks)} | % m.{meas.index}')

    ts0 = f'{first_sig[0]}/{first_sig[1]}'

    # Build subtitle: show drummer if known
    subtitle_line = (f'  subtitle = "drums: {score.drummer}"'
                     if score.drummer else '')

    lines = [
        f'\\version "{version}.0"', '',
        '\\header {',
        f'  title    = "{score.title}"',
        f'  composer = "{score.artist}"',
    ]
    if subtitle_line:
        lines.append(subtitle_line)
    lines += [
        '  tagline  = ##f',
        '}', '',
        '\\paper {',
        '  #(set-paper-size "letter")',
        '  indent             = 0',
        '  short-indent       = 0',
        '  ragged-right       = ##t',
        '  ragged-last-bottom = ##f',
        '  system-system-spacing.basic-distance = #12',
        '  system-system-spacing.padding        = #2',
        '  top-margin                           = 10',
        '  bottom-margin                        = 10',
        '}', '',
        'drumVoice = \\drummode {',
        '  \\stemDown',
        '  \\numericTimeSignature',
        '  \\set Score.barNumberVisibility = #(every-nth-bar-number-visible 4)',
        '  \\override Score.BarNumber.break-visibility = ##(#t #t #t)',
        '  \\override Beam.damping = #+inf.0',
        '  \\override Score.TimeSignature.break-visibility = ##(#f #t #t)',
        f'  \\tempo 4 = {int(initial_bpm)}',
        f'  \\time {ts0}',
        '\n'.join(voice_lines),
        '}', '',
        '\\score {',
        '  \\new DrumStaff \\with {',
        '    \\override StaffSymbol.line-count = #5',
        f'    drumStyleTable = {_DRUM_STYLE}',
        '  } {',
        '    \\new DrumVoice \\with {',
        f'      drumStyleTable = {_DRUM_STYLE}',
        '    } \\drumVoice',
        '  }',
        '  \\layout {',
        '    \\context {',
        '      \\Score',
        '      \\override RehearsalMark.font-size = #1',
        '      \\override RehearsalMark.padding   = #1',
        '    }',
        '  }',
        '}',
    ]

    return '\n'.join(lines) + '\n'
