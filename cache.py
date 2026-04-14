"""
cache.py — Save and load Score IR to/from a local JSON database.

Fraction values are serialised as [numerator, denominator] lists.
All other fields serialise naturally to JSON primitives.

Database location is configured by DB_DIR (default: ./db/).
"""

import json
import os
from fractions import Fraction

from ir import Score, Measure, Event, DrumNote, TempoChange

DB_DIR = os.path.join(os.path.dirname(__file__), 'db')


def set_db_dir(path: str):
    """Override the database directory (call before any save/load)."""
    global DB_DIR
    DB_DIR = path
    os.makedirs(DB_DIR, exist_ok=True)


def _cache_path(song_id, part_id):
    os.makedirs(DB_DIR, exist_ok=True)
    return os.path.join(DB_DIR, f'{song_id}_{part_id}.json')


# ── Serialisation helpers ──────────────────────────────────────────────────────

def _frac_to_list(f):
    return [f.numerator, f.denominator]

def _list_to_frac(lst):
    return Fraction(lst[0], lst[1])

def _drum_note_to_dict(dn):
    return {'midi': dn.midi, 'lily': dn.lily, 'voice': dn.voice,
            'ghost': dn.ghost, 'accent': dn.accent}

def _dict_to_drum_note(d):
    return DrumNote(midi=d['midi'], lily=d['lily'], voice=d['voice'],
                    ghost=d['ghost'], accent=d['accent'])

def _event_to_dict(ev):
    return {
        'position':     _frac_to_list(ev.position),
        'duration':     _frac_to_list(ev.duration),
        'notes':        [_drum_note_to_dict(n) for n in ev.notes],
        'grace':        ev.grace,
        'grace_type':   ev.grace_type,
        'tremolo_base': ev.tremolo_base,
        'hairpin':      ev.hairpin,
        'tuplet_n':     ev.tuplet_n,
        'tuplet_m':     ev.tuplet_m,
        'tuplet_group': ev.tuplet_group,
        'dots':         ev.dots,
        'velocity':     ev.velocity,
        'text':         ev.text,
    }

def _dict_to_event(d):
    return Event(
        position=_list_to_frac(d['position']),
        duration=_list_to_frac(d['duration']),
        notes=[_dict_to_drum_note(n) for n in d['notes']],
        grace=d.get('grace', False),
        grace_type=d.get('grace_type', 'before'),
        tremolo_base=d.get('tremolo_base'),
        hairpin=d.get('hairpin'),
        tuplet_n=d.get('tuplet_n'),
        tuplet_m=d.get('tuplet_m'),
        tuplet_group=d.get('tuplet_group'),
        dots=d.get('dots', 0),
        velocity=d.get('velocity'),
        text=d.get('text'),
    )

def _measure_to_dict(m):
    return {
        'index':    m.index,
        'time_sig': list(m.time_sig),
        'position': _frac_to_list(m.position),
        'duration': _frac_to_list(m.duration),
        'marker':   m.marker,
        'events':   [_event_to_dict(e) for e in m.events],
    }

def _dict_to_measure(d):
    return Measure(
        index=d['index'],
        time_sig=tuple(d['time_sig']),
        position=_list_to_frac(d['position']),
        duration=_list_to_frac(d['duration']),
        marker=d.get('marker'),
        events=[_dict_to_event(e) for e in d['events']],
    )

def _tempo_to_dict(tc):
    return {'position': _frac_to_list(tc.position),
            'bpm': tc.bpm, 'linear': tc.linear}

def _dict_to_tempo(d):
    return TempoChange(position=_list_to_frac(d['position']),
                       bpm=d['bpm'], linear=d.get('linear', False))


# ── Public API ─────────────────────────────────────────────────────────────────

def score_to_dict(score: Score) -> dict:
    return {
        'title':          score.title,
        'artist':         score.artist,
        'drummer':        score.drummer,
        'song_id':        score.song_id,
        'part_id':        score.part_id,
        'youtube_id':     score.youtube_id,
        'youtube_offset': score.youtube_offset,
        'tempo_changes':  [_tempo_to_dict(t) for t in score.tempo_changes],
        'measures':       [_measure_to_dict(m) for m in score.measures],
    }

def score_from_dict(d: dict) -> Score:
    return Score(
        title=d['title'],
        artist=d['artist'],
        drummer=d.get('drummer', ''),
        song_id=d['song_id'],
        part_id=d['part_id'],
        youtube_id=d.get('youtube_id'),
        youtube_offset=d.get('youtube_offset', 0.0),
        tempo_changes=[_dict_to_tempo(t) for t in d['tempo_changes']],
        measures=[_dict_to_measure(m) for m in d['measures']],
    )

def save_score(score: Score):
    path = _cache_path(score.song_id, score.part_id)
    with open(path, 'w') as f:
        json.dump(score_to_dict(score), f, indent=2)
    print(f'Saved: {path}')

def load_score(song_id: int, part_id: int):
    path = _cache_path(song_id, part_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return score_from_dict(json.load(f))

def list_cached():
    if not os.path.exists(DB_DIR):
        print('Cache is empty.')
        return
    files = [f for f in os.listdir(DB_DIR) if f.endswith('.json')]
    if not files:
        print('Cache is empty.')
        return
    print(f'Cached scores in {DB_DIR}:')
    for fn in sorted(files):
        path = os.path.join(DB_DIR, fn)
        with open(path) as fh:
            d = json.load(fh)
        drummer = d.get('drummer', '')
        drummer_str = f' ({drummer})' if drummer else ''
        print(f'  {fn:35s}  {d["artist"]} - {d["title"]}{drummer_str}'
              f'  [{len(d["measures"])} measures]')
