"""
parser.py — Parse Songsterr JSON into Score IR.

Handles both format version 5 (integer strings, inline tempo, grace=true on notes)
and version 8 (fractional strings, graceNote on beat, tempo in automations).

Key insight: fret = GM MIDI number. The string field is only needed by
Songsterr's canvas renderer and is ignored here.
"""

from fractions import Fraction
from ir import (
    Score, Measure, Event, DrumNote, TempoChange
)


# GM drum map: MIDI note -> (LilyPond name, voice, description)
# Voice 1 = stems up (cymbals, hi-hats)
# Voice 2 = stems down (kick, snare, toms, pedal)
GM = {
    35: ('bd',    2, 'Bass Drum 2'),
    36: ('bd',    2, 'Bass Drum 1'),
    37: ('sn',    2, 'Side Stick'),
    38: ('sn',    2, 'Acoustic Snare'),
    39: ('sn',    2, 'Hand Clap'),
    40: ('sn',    2, 'Electric Snare'),
    41: ('tomml', 2, 'Low Floor Tom'),
    42: ('hh',    1, 'Closed Hi-Hat'),
    43: ('toml',  2, 'High Floor Tom'),
    44: ('hhp',   2, 'Pedal Hi-Hat'),
    45: ('tommh', 2, 'Low Tom'),
    46: ('hho',   1, 'Open Hi-Hat'),
    47: ('tomh',  2, 'Low-Mid Tom'),
    48: ('tomfh', 2, 'High-Mid Tom'),
    49: ('cymca', 1, 'Crash Cymbal 1'),
    50: ('tomml', 2, 'High Tom'),
    51: ('cymr',  1, 'Ride Cymbal 1'),
    52: ('cymca', 1, 'Chinese Cymbal'),
    53: ('cymr',  1, 'Ride Bell'),
    54: ('tamb',  1, 'Tambourine'),
    55: ('cymca', 1, 'Splash Cymbal'),
    56: ('cb',    1, 'Cowbell'),
    57: ('cymcb', 1, 'Crash Cymbal 2'),
    58: ('vibs',  1, 'Vibraslap'),
    59: ('cymr',  1, 'Ride Cymbal 2'),
    60: ('tomh',  2, 'Hi Bongo'),
    61: ('toml',  2, 'Low Bongo'),
    62: ('tomfh', 2, 'Mute Hi Conga'),
    63: ('tomh',  2, 'Open Hi Conga'),
    64: ('toml',  2, 'Low Conga'),
    65: ('tommh', 2, 'High Timbale'),
    66: ('tomml', 2, 'Low Timbale'),
    # Songsterr-specific extensions beyond standard GM
    97: ('cymca', 1, 'Crash (alt)'),
    98: ('hho',   1, 'Open Hi-Hat (alt)'),
}


def _drum_note(midi: int, ghost=False, accent=0):
    entry = GM.get(midi)
    if entry is None:
        return None
    lily, voice, _ = entry
    return DrumNote(midi=midi, lily=lily, voice=voice, ghost=ghost, accent=accent)


def _parse_notes(beat_notes, include_grace=False):
    """Convert raw beat notes list to list[DrumNote]."""
    out = []
    for n in beat_notes:
        if n.get('rest') or 'fret' not in n:
            continue
        if n.get('grace') and not include_grace:
            continue
        dn = _drum_note(
            midi=int(n['fret']),
            ghost=bool(n.get('ghost', False)),
            accent=int(n.get('accentuated', 0))
        )
        if dn is not None:
            out.append(dn)
    return out


def _hairpin(beat):
    gv = beat.get('gradualVelocity')
    if gv == 'crescendo':   return 'start'
    if gv == 'decrescendo': return 'stop'
    return None


def parse_json(data: dict, title: str, artist: str) -> Score:
    """
    Parse a Songsterr tab JSON dict into a Score IR.
    Handles both format version 5 (integer strings) and version 8 (fractional strings).
    """
    song_id  = data.get('songId', 0)
    part_id  = data.get('partId', 0)
    drummer  = data.get('name', '')
    raw_measures = data.get('measures', [])

    # ── Build tempo map ────────────────────────────────────────────────────────
    raw_tempos = list(data.get('automations', {}).get('tempo', []))
    seen = {t['measure'] for t in raw_tempos}

    # Also scan beats for inline tempo (v5 format)
    for mi, meas in enumerate(raw_measures):
        for b in meas.get('voices', [{}])[0].get('beats', []):
            t = b.get('tempo', {})
            if t.get('bpm'):
                idx = meas.get('index', mi + 1)
                if idx not in seen:
                    raw_tempos.append({'measure': idx, 'bpm': t['bpm'],
                                       'linear': False, 'position': 0})
                    seen.add(idx)
                break

    # Normalise measure index to 0-based
    offset = min(t['measure'] for t in raw_tempos) if raw_tempos else 1

    # Two-pass: compute cumulative measure positions first
    cur_sig = [4, 4]
    meas_positions = []
    pos = Fraction(0)
    for meas in raw_measures:
        if 'signature' in meas:
            cur_sig = meas['signature']
        meas_positions.append(pos)
        pos += Fraction(cur_sig[0], cur_sig[1])

    def _measure_pos(norm_idx):
        i = norm_idx
        if 0 <= i < len(meas_positions):
            return meas_positions[i]
        return Fraction(0)

    tempo_changes = []
    for t in sorted(raw_tempos, key=lambda x: x['measure']):
        norm    = t['measure'] - offset
        tc_pos  = _measure_pos(norm)
        sub     = Fraction(t.get('position', 0), 4)
        tempo_changes.append(TempoChange(
            position=tc_pos + sub,
            bpm=float(t['bpm']),
            linear=bool(t.get('linear', False))
        ))

    if not tempo_changes:
        tempo_changes = [TempoChange(position=Fraction(0), bpm=120.0)]

    # ── Parse measures ─────────────────────────────────────────────────────────
    cur_sig = [4, 4]
    measures = []
    tuplet_group_counter = 0

    for mi, raw in enumerate(raw_measures):
        meas_idx = raw.get('index', mi + 1)
        if 'signature' in raw:
            cur_sig = raw['signature']
        meas_dur = Fraction(cur_sig[0], cur_sig[1])
        meas_pos = meas_positions[mi]
        marker   = raw.get('marker', {}).get('text', None)
        events   = []

        if raw.get('rest'):
            events.append(Event(
                position=meas_pos,
                duration=meas_dur,
                notes=[]
            ))
            measures.append(Measure(
                index=meas_idx,
                time_sig=tuple(cur_sig),
                position=meas_pos,
                duration=meas_dur,
                marker=marker,
                events=events
            ))
            continue

        beats    = raw.get('voices', [{}])[0].get('beats', [])
        beat_pos = meas_pos
        i        = 0

        while i < len(beats):
            beat       = beats[i]
            beat_notes = beat.get('notes', [])
            dur_frac   = Fraction(beat['duration'][0], beat['duration'][1])

            # v8 grace note beat
            if beat.get('graceNote'):
                notes = _parse_notes(beat_notes)
                if notes:
                    events.append(Event(
                        position=beat_pos,
                        duration=dur_frac,
                        notes=notes,
                        grace=True,
                        grace_type=('on' if beat['graceNote'] == 'onBeat' else 'before')
                    ))
                i += 1
                continue

            # v5 flam: all real notes carry grace=true
            real = [n for n in beat_notes if not n.get('rest') and 'fret' in n]
            if real and all(n.get('grace') for n in real):
                notes = _parse_notes(beat_notes, include_grace=True)
                events.append(Event(
                    position=beat_pos,
                    duration=dur_frac,
                    notes=notes,
                    grace=True,
                    grace_type='before',
                    text=(beat.get('text', {}).get('text')
                          if isinstance(beat.get('text'), dict) else None)
                ))
                beat_pos += dur_frac
                i += 1
                continue

            # Tuplet group
            if beat.get('tupletStart'):
                tuplet_group_counter += 1
                group_id  = tuplet_group_counter
                N         = beat.get('tuplet', 3)
                group, j  = [], i
                while j < len(beats):
                    b = beats[j]
                    if not b.get('graceNote'):
                        group.append(b)
                        j += 1
                        if b.get('tupletStop'):
                            break
                    else:
                        j += 1
                group_dur = sum(
                    Fraction(b['duration'][0], b['duration'][1]) for b in group)
                M = max(1, round(float(group_dur * beat.get('type', 8))))
                for b in group:
                    b_dur = Fraction(b['duration'][0], b['duration'][1])
                    notes = _parse_notes(b.get('notes', []))
                    ev = Event(
                        position=beat_pos,
                        duration=b_dur,
                        notes=notes,
                        tuplet_n=N,
                        tuplet_m=M,
                        tuplet_group=group_id,
                        dots=b.get('dots', 0),
                        velocity=b.get('velocity'),
                        hairpin=_hairpin(b),
                    )
                    events.append(ev)
                    beat_pos += b_dur
                i = j
                continue

            # Normal beat
            notes = [] if beat.get('rest') else _parse_notes(beat_notes)
            ev = Event(
                position=beat_pos,
                duration=dur_frac,
                notes=notes,
                dots=beat.get('dots', 0),
                velocity=beat.get('velocity'),
                tremolo_base=(beat['tremolo'][1] if beat.get('tremolo') else None),
                hairpin=_hairpin(beat),
                text=(beat.get('text', {}).get('text')
                      if isinstance(beat.get('text'), dict) else None)
            )
            events.append(ev)
            beat_pos += dur_frac
            i += 1

        measures.append(Measure(
            index=meas_idx,
            time_sig=tuple(cur_sig),
            position=meas_pos,
            duration=meas_dur,
            marker=marker,
            events=events
        ))

    return Score(
        title=title,
        artist=artist,
        drummer=drummer,
        song_id=song_id,
        part_id=part_id,
        tempo_changes=tempo_changes,
        measures=measures
    )
