"""
ir.py — Internal Representation for drum scores.

All time positions are stored as exact Fraction values (rational multiples
of a whole note from the score start). Wall-clock seconds are derived on
demand from the tempo map via Score.seconds_at().
"""

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional


@dataclass
class TempoChange:
    """A tempo event at an absolute score position."""
    position: Fraction   # whole notes from score start
    bpm: float           # quarter-note beats per minute
    linear: bool = False # True = gradual ramp to the next tempo


@dataclass
class DrumNote:
    """A single drum stroke within an Event."""
    midi: int            # GM drum MIDI number (35-81)
    lily: str            # LilyPond drum name e.g. 'hh', 'bd', 'sn'
    voice: int           # 1 = stems up (cymbals/hats), 2 = stems down (kick/snare/toms)
    ghost: bool = False
    accent: int = 0      # 0 = none, 1 = accent (>), 2 = marcato (^)


@dataclass
class Event:
    """A single rhythmic event (note chord or rest) with absolute position."""
    position: Fraction       # whole notes from score start
    duration: Fraction       # notated duration in whole notes
    notes: list              # list[DrumNote], empty = rest
    # Articulation
    grace: bool = False              # is this a grace note?
    grace_type: str = 'before'       # 'before' = acciaccatura, 'on' = appoggiatura
    tremolo_base: Optional[int] = None   # e.g. 32 means \repeat tremolo N { note32 }
    hairpin: Optional[str] = None        # 'start' | 'stop'
    # Notation hints (used by engraving backends)
    tuplet_n: Optional[int] = None   # N in \tuplet N/M
    tuplet_m: Optional[int] = None   # M in \tuplet N/M
    tuplet_group: Optional[int] = None  # events sharing same group ID form one bracket
    dots: int = 0
    velocity: Optional[str] = None   # 'pp','p','mp','mf','f','ff'
    text: Optional[str] = None       # performance annotation e.g. 'Flam'


@dataclass
class Measure:
    """One bar of music."""
    index: int               # 1-based measure number
    time_sig: tuple          # e.g. (4, 4)
    position: Fraction       # absolute position of measure start
    duration: Fraction       # total notated duration
    marker: Optional[str]    # section label e.g. 'Intro', 'Chorus'
    events: list             # list[Event], sorted by position


@dataclass
class Score:
    """Complete parsed drum score."""
    title: str
    artist: str
    drummer: str
    song_id: int
    part_id: int
    tempo_changes: list      # list[TempoChange], sorted by position
    measures: list           # list[Measure]

    # Optional YouTube sync (populated separately when available)
    youtube_id: Optional[str] = None
    youtube_offset: float = 0.0  # video seconds corresponding to score position 0

    def seconds_at(self, position: Fraction) -> float:
        """Convert absolute score position to wall-clock seconds."""
        t = 0.0
        prev_pos = Fraction(0)
        prev_bpm = self.tempo_changes[0].bpm if self.tempo_changes else 120.0
        for tc in sorted(self.tempo_changes, key=lambda x: x.position):
            if tc.position >= position:
                break
            t += float(tc.position - prev_pos) * 4 * 60 / prev_bpm
            prev_pos = tc.position
            prev_bpm = tc.bpm
        t += float(position - prev_pos) * 4 * 60 / prev_bpm
        return t

    def position_at(self, seconds: float) -> Fraction:
        """Inverse: wall-clock seconds -> score position (for YouTube sync)."""
        remaining = seconds
        prev_pos = Fraction(0)
        prev_bpm = self.tempo_changes[0].bpm if self.tempo_changes else 120.0
        for tc in sorted(self.tempo_changes, key=lambda x: x.position):
            seg = float(tc.position - prev_pos) * 4 * 60 / prev_bpm
            if remaining <= seg:
                break
            remaining -= seg
            prev_pos = tc.position
            prev_bpm = tc.bpm
        return prev_pos + Fraction(remaining * prev_bpm / (4 * 60)).limit_denominator(10000)
