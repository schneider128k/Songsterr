"""
player.py — browser-based playback for cached drum scores via Tone.js.

Reads a Score IR (cached or freshly fetched), precomputes a wall-clock
schedule, and serves a single-page UI that synthesises the drum part in
the browser using Tone.js.

This is read-only: the IR is not modified. Purpose is twofold —
(a) ear-check the parsed IR (audible bugs are louder than visual ones)
and (b) MVP for the Milestone 6 browser tooling.

Usage
-----
    python player.py <songsterr-page-url>     # fetch+parse if not cached, then play
    python player.py <cdn-url>                # same, with explicit CDN URL
    python player.py <songId>_<partId>        # play a specific cached score
    python player.py <songId>                 # play, if exactly one part is cached
    python player.py --list                   # list cached scores and exit

Server runs on http://127.0.0.1:8765 by default. The browser opens
automatically. Press Ctrl+C in the terminal to stop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import cache
from cache import load_score
from ir import Score
from pipeline import fetch_and_parse


HOST = '127.0.0.1'
PORT = 8765
HERE = os.path.dirname(os.path.abspath(__file__))


# ── Schedule construction ─────────────────────────────────────────────────────

def build_schedule(score: Score) -> dict:
    """
    Walk the IR once and produce a JSON-clean dict the browser can play.

    The browser never sees Fractions — every time is a float in seconds,
    derived from Score.seconds_at(). Tempo-map walking is therefore
    server-side and always consistent with the LilyPond emitter's view of
    time. This is intentional: the browser's job is purely audio
    scheduling, not music theory.

    Output schema:
        {
          'title', 'artist', 'song_id', 'part_id',
          'total_seconds': float,
          'events':   [{'seconds': float, 'midi': [int, ...], 'grace_v8': bool}, ...],
          'measures': [{'index': int, 'seconds_start': float,
                        'time_sig': [num, den], 'marker': str | None}, ...],
          'tempos':   [{'seconds': float, 'bpm': float}, ...],
        }
    """
    events: list[dict] = []
    for measure in score.measures:
        for ev in measure.events:
            if not ev.notes:
                # Pure rest — nothing to play. The bar counter still
                # advances because it keys off Tone.Transport.seconds,
                # not off our event list.
                continue
            events.append({
                'seconds': score.seconds_at(ev.position),
                'midi': [n.midi for n in ev.notes],
                # grace_v8 = True means the parser flagged this as a v8
                # acciaccatura ornament. Browser may apply a small
                # negative offset so it sounds before the beat. v5 flams
                # already have real durations; their position is the
                # correct sounding time as-is.
                'grace_v8': bool(ev.grace and ev.grace_is_v8),
            })

    measures: list[dict] = []
    for m in score.measures:
        measures.append({
            'index': m.index,
            'seconds_start': score.seconds_at(m.position),
            'time_sig': list(m.time_sig),
            'marker': m.marker,
        })

    tempos: list[dict] = []
    for tc in score.tempo_changes:
        tempos.append({
            'seconds': score.seconds_at(tc.position),
            'bpm': tc.bpm,
        })

    if score.measures:
        last = score.measures[-1]
        total_seconds = score.seconds_at(last.position + last.duration)
    else:
        total_seconds = 0.0

    return {
        'title': score.title,
        'artist': score.artist,
        'song_id': score.song_id,
        'part_id': score.part_id,
        'total_seconds': total_seconds,
        'events': events,
        'measures': measures,
        'tempos': tempos,
    }


# ── Target resolution (URL | id_id | id) ──────────────────────────────────────

def resolve_target(arg: str) -> Score:
    """Turn a CLI argument into a Score. See module docstring for forms."""
    arg = arg.strip()

    if arg.startswith('http://') or arg.startswith('https://'):
        return fetch_and_parse(arg)

    m = re.fullmatch(r'(\d+)_(\d+)', arg)
    if m:
        song_id, part_id = int(m.group(1)), int(m.group(2))
        score = load_score(song_id, part_id)
        if score is None:
            sys.exit(f'No cached score for {arg} in {cache.DB_DIR}')
        print(f'Loaded from cache: {score.artist} - {score.title}')
        return score

    if arg.isdigit():
        song_id = int(arg)
        if not os.path.isdir(cache.DB_DIR):
            sys.exit(f'Cache directory does not exist: {cache.DB_DIR}')
        matches = [
            f for f in os.listdir(cache.DB_DIR)
            if re.fullmatch(rf'{song_id}_(\d+)\.json', f)
        ]
        if not matches:
            sys.exit(f'No cached score for songId {song_id}')
        if len(matches) > 1:
            sys.exit(
                f'Multiple cached parts for songId {song_id}: '
                f'{sorted(matches)}\n'
                f'Specify one as <songId>_<partId>.'
            )
        m2 = re.fullmatch(r'(\d+)_(\d+)\.json', matches[0])
        score = load_score(int(m2.group(1)), int(m2.group(2)))
        print(f'Loaded from cache: {score.artist} - {score.title}')
        return score

    sys.exit(
        f'Unrecognized target: {arg!r}\n'
        f'Expected a Songsterr URL, <songId>_<partId>, or <songId>.'
    )


# ── HTTP server ───────────────────────────────────────────────────────────────

class PlayerHandler(BaseHTTPRequestHandler):
    """One score per server instance — set on the class before serving."""
    schedule_json: bytes = b'{}'

    def _send(self, status: int, content_type: str, body: bytes,
              cache_control: str = 'no-store') -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache_control)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, content_type: str) -> None:
        try:
            with open(path, 'rb') as f:
                body = f.read()
        except FileNotFoundError:
            self._send(404, 'text/plain; charset=utf-8',
                       f'Not found: {path}'.encode('utf-8'))
            return
        self._send(200, content_type, body)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        # Strip query string — we don't use it.
        path = self.path.split('?', 1)[0]

        if path == '/' or path == '/index.html':
            self._send_file(os.path.join(HERE, 'player.html'),
                            'text/html; charset=utf-8')
        elif path == '/player.js':
            self._send_file(os.path.join(HERE, 'player.js'),
                            'application/javascript; charset=utf-8')
        elif path == '/api/score':
            self._send(200, 'application/json; charset=utf-8',
                       PlayerHandler.schedule_json)
        else:
            self._send(404, 'text/plain; charset=utf-8',
                       f'Not found: {path}'.encode('utf-8'))

    def log_message(self, fmt: str, *args) -> None:
        # Quieter than the default — one line per request, no IP.
        sys.stderr.write(f'  {fmt % args}\n')


def serve(schedule: dict, host: str = HOST, port: int = PORT,
          open_browser: bool = True) -> None:
    PlayerHandler.schedule_json = json.dumps(schedule).encode('utf-8')
    server = ThreadingHTTPServer((host, port), PlayerHandler)

    url = f'http://{host}:{port}/'
    print(f'\nPlayer ready: {url}')
    print(f'  Title : {schedule["artist"]} - {schedule["title"]}')
    print(f'  Length: {schedule["total_seconds"]:.1f} s '
          f'({len(schedule["events"])} events, '
          f'{len(schedule["measures"])} measures)')
    print('Press Ctrl+C to stop.\n')

    if open_browser:
        # Defer so the server is actually listening when the browser hits it.
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
        server.shutdown()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Browser playback for cached drum scores.')
    parser.add_argument(
        'target', nargs='?',
        help='Songsterr URL, <songId>_<partId>, or <songId>.')
    parser.add_argument(
        '--list', action='store_true',
        help='List cached scores and exit.')
    parser.add_argument(
        '--no-browser', action='store_true',
        help='Do not auto-open the browser.')
    parser.add_argument(
        '--port', type=int, default=PORT,
        help=f'HTTP port (default {PORT}).')
    args = parser.parse_args()

    if args.list:
        cache.list_cached()
        return

    if not args.target:
        parser.print_help()
        sys.exit(1)

    score = resolve_target(args.target)
    schedule = build_schedule(score)
    serve(schedule, port=args.port, open_browser=not args.no_browser)


if __name__ == '__main__':
    main()
