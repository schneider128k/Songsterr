"""
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
"""

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
    """Decompose a duration into a list of rest tokens."""
    out, rem = [], Fraction(f)
    for fv, fs in _DURS:
        while rem >= fv:
            out.append('r' + fs)
            rem -= fv
    if rem > 0:
        out.append('r4')
    return out


def _event_to_token(ev, force_dur=None):
    """
    Render one Event as a single LilyPond token.
    force_dur: if given, overrides the duration string (used inside tuplets
               where the notated duration like 1/24 is not a standard value).
    """
    ly_dur = force_dur if force_dur is not None else _dur(ev.duration)

    # Grace note
    if ev.grace:
        if not ev.notes:
            return None
        cmd   = '\\appoggiatura' if ev.grace_type == 'on' else '\\acciaccatura'
        nms   = sorted({n.lily for n in ev.notes})
        inner = nms[0] if len(nms) == 1 else '<' + ' '.join(nms) + '>'
        return f'{cmd} {{ {inner}8 }} {inner}{ly_dur}'

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

    if len(nms) == 1:
        n   = nms[0]
        tok = f'\\parenthesize {n}{ly_dur}' if n in ghosts else f'{n}{ly_dur}'
    else:
        tok = f'<{" ".join(nms)}>{ly_dur}'

    if accent == 1:   tok += '\\accent'
    elif accent == 2: tok += '\\marcato'
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
    # v8 grace notes have duration ~1/128 (near zero, don't advance cursor)
    # v5 flams have a real duration (1/8, 1/4 etc, do advance cursor)
    GRACE_DUR_THRESHOLD = Fraction(1, 32)
    i = 0

    # Build a flat list of non-grace events for tie look-ahead
    non_grace = [e for e in events if not e.grace]

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
            # Advance cursor for v5 flams (real duration) but not v8 grace notes
            if ev.duration >= GRACE_DUR_THRESHOLD:
                cursor += ev.duration
            i += 1
            continue

        # Normal event
        tok = _event_to_token(ev)

        if tok is not None and tok[0] != 'r':
            if ev.hairpin == 'start' and not hairpin_open:
                tok = '\\< ' + tok
                hairpin_open = True
            elif hairpin_open and ev.hairpin != 'start':
                tok += ' \\!'
                hairpin_open = False

            # FIX 3: Tie validation — only emit ~ if a tied note's lily name
            # also appears in the next non-grace event. This prevents spurious
            # tie arcs connecting e.g. crashcymbal to openhihat.
            tied_lily_names = {n.lily for n in ev.notes if getattr(n, 'tie', False)}
            if tied_lily_names:
                # Find the next non-grace event after this one
                ng_idx = next(
                    (k for k, e in enumerate(non_grace) if e is ev), None)
                next_ev = non_grace[ng_idx + 1] if (
                    ng_idx is not None and ng_idx + 1 < len(non_grace)) else None
                next_lily = {n.lily for n in next_ev.notes} if next_ev else set()
                # Only tie notes that actually appear in the next event
                valid_ties = tied_lily_names & next_lily
                if valid_ties:
                    tok += ' ~'

        tokens.append(tok if tok is not None else 'r' + _dur(ev.duration))
        cursor += ev.duration
        i += 1

    if hairpin_open and tokens:
        tokens[-1] += ' \\!'

    if cursor < end_pos:
        tokens.extend(_fill_rests(end_pos - cursor))

    return tokens


# Custom drum style table.
# Positions: 0=middle line, 4=top line, 5=space above top line,
# 6=first ledger line above, -4=bottom line, -5=space below bottom.
# FIX 1: acousticsnare/snare/electricsnare/sn moved from 0 to -1
# (space between lines 2 and 3 — standard snare drum position).
_DRUM_STYLE = """\
#(alist->hash-table '(
  (acousticbassdrum default #f -5)
  (bassdrum         default #f -5)
  (bd               default #f -5)
  (acousticsnare    default #f  1)
  (snare            default #f  1)
  (electricsnare    default #f  1)
  (sn               default #f  1)
  (sidestick        cross   #f -2)
  (hihat            cross   #f  5)
  (closedhihat      cross   #f  5)
  (hh               cross   #f  5)
  (halfopenhihat    xcircle #f  5)
  (openhihat        xcircle #f  5)
  (hho              xcircle #f  5)
  (pedalhihat       cross   #f -5)
  (hhp              cross   #f -5)
  (crashcymbal      cross   #f  7)
  (cymca            cross   #f  7)
  (crashcymbalb     cross   #f  6)
  (cymcb            cross   #f  6)
  (ridecymbal       cross   #f  5)
  (ridecymbalb      cross   #f  5)
  (cymr             cross   #f  5)
  (ridebell         default #f  5)
  (chinesecymbal    cross   #f  7)
  (splashcymbal     cross   #f  7)
  (cowbell          default #f  4)
  (cb               default #f  4)
  (tambourine       cross   #f  4)
  (tamb             cross   #f  4)
  (vibraslap        diamond #f  0)
  (vibs             diamond #f  0)
  (handclap         default #f  4)
  (highfloortom     default #f -2)
  (tomfh            default #f -2)
  (lowfloortom      default #f -3)
  (tomfl            default #f -3)
  (lowtom           default #f -1)
  (toml             default #f -1)
  (lowmidtom        default #f  1)
  (tomml            default #f  1)
  (himidtom         default #f  2)
  (tommh            default #f  2)
  (hightom          default #f  3)
  (tomh             default #f  3)
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


def _is_pickup(measures):
    """
    Return True if the first measure is a pickup bar: a rest-only measure
    whose time signature differs from the second measure's time signature.
    This handles songs like Square Hammer where Songsterr prepends a half-bar
    rest before the main 4/4 content.
    """
    if len(measures) < 2:
        return False
    m0 = measures[0]
    m1 = measures[1]
    if m0.time_sig == m1.time_sig:
        return False
    # Check all events in m0 are rests (empty notes list)
    all_rests = all(len(ev.notes) == 0 for ev in m0.events)
    return all_rests


def emit_lilypond(score: Score, version: str) -> str:
    """Compile a Score IR to a LilyPond source string."""
    voice_lines = []

    sorted_tempos = sorted(score.tempo_changes, key=lambda t: t.position)
    initial_bpm   = sorted_tempos[0].bpm if sorted_tempos else 120
    tempo_at_pos  = {t.position: t.bpm for t in sorted_tempos[1:]}

    section_lengths = _compute_section_lengths(score.measures)
    prev_sig = None

    # FIX 2: Detect pickup bar and determine the main time signature.
    # If the first measure is a pickup, we suppress its \time directive and
    # emit \partial instead, so LilyPond numbers the first full bar as bar 1
    # (matching Songsterr's bar numbering).
    pickup = _is_pickup(score.measures)
    if pickup:
        main_sig = score.measures[1].time_sig
    else:
        main_sig = score.measures[0].time_sig if score.measures else (4, 4)

    for mi, meas in enumerate(score.measures):
        # Forced line break before long-enough sections
        if meas.marker and mi > 0:
            if section_lengths.get(mi, 0) >= MIN_SECTION_MEASURES:
                voice_lines.append('  \\break')

        # FIX 2: For the pickup measure, emit \partial instead of \time.
        # For all other measures, emit \time only when the signature changes.
        if pickup and mi == 0:
            partial_dur = _dur(meas.duration)
            voice_lines.append(f'  \\partial {partial_dur}')
            # Do NOT emit \time here; set prev_sig so the next measure's
            # \time fires normally.
            prev_sig = meas.time_sig
        else:
            if meas.time_sig != prev_sig:
                ts = f'{meas.time_sig[0]}/{meas.time_sig[1]}'
                voice_lines.append(f'  \\time {ts}')
                prev_sig = meas.time_sig

        if meas.position in tempo_at_pos:
            voice_lines.append(f'  \\tempo 4 = {int(tempo_at_pos[meas.position])}')

        if meas.marker:
            voice_lines.append(f'  \\mark \\markup {{ \\box "{meas.marker}" }}')

        toks = _emit_measure(meas.events, meas.duration, meas.position)
        voice_lines.append(f'  {" ".join(toks)} | % m.{meas.index}')

    ts0 = f'{main_sig[0]}/{main_sig[1]}'

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
        '    \\new DrumVoice \\drumVoice',
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
