"""
player.py — browser-based playback for cached drum scores via Tone.js,
            with sheet music rendered alongside via LilyPond SVG (M6b).

Reads a Score IR (cached or freshly fetched), precomputes a wall-clock
schedule, compiles the score to SVG via LilyPond, and serves a
single-page UI that synthesises the drum part in the browser using
Tone.js while displaying the engraved score above the controls.

This is read-only: the IR is not modified. Purpose is twofold —
(a) ear-and-eye-check the parsed IR (audible AND visible bugs)
and (b) MVP for Milestone 6 browser tooling.

Usage
-----
    python player.py <songsterr-page-url>     # fetch+parse if not cached, then play
    python player.py <cdn-url>                # same, with explicit CDN URL
    python player.py <songId>_<partId>        # play a specific cached score
    python player.py <songId>                 # play, if exactly one part is cached
    python player.py --list                   # list cached scores and exit

    Add --no-svg to skip the LilyPond SVG compilation (faster startup,
    no sheet music in the UI).

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
from pipeline import fetch_and_parse, compile_to_svg


HOST = '127.0.0.1'
PORT = 8765
HERE = os.path.dirname(os.path.abspath(__file__))


# ── Schedule construction ─────────────────────────────────────────────────────

def build_schedule(score: Score, svg_pages: int = 0) -> dict:
    """
    Walk the IR once and produce a JSON-clean dict the browser can play.

    The browser never sees Fractions — every time is a float in seconds,
    derived from Score.seconds_at(). Tempo-map walking is therefore
    server-side and always consistent with the LilyPond emitter's view of
    time. This is intentional: the browser's job is purely audio
    scheduling, not music theory.

    `svg_pages` is the count of LilyPond-compiled SVG pages available at
    /svg/<i> for i in [0, svg_pages). Zero means no sheet music
    (compilation skipped or failed).

    Output schema:
        {
          'title', 'artist', 'song_id', 'part_id',
          'total_seconds': float,
          'svg_pages': int,
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
                continue
            events.append({
                'seconds': score.seconds_at(ev.position),
                'midi': [n.midi for n in ev.notes],
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
        'svg_pages': svg_pages,
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
    svg_pages: list[str] = []  # absolute filesystem paths, in page order

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
        elif path.startswith('/svg/'):
            tail = path[len('/svg/'):]
            try:
                idx = int(tail)
            except ValueError:
                self._send(404, 'text/plain; charset=utf-8',
                           b'Bad SVG index')
                return
            if 0 <= idx < len(PlayerHandler.svg_pages):
                # image/svg+xml is the registered media type. The charset
                # matters because LilyPond's SVG includes UTF-8 (e.g. the
                # ♩ glyph in tempo markings).
                self._send_file(PlayerHandler.svg_pages[idx],
                                'image/svg+xml; charset=utf-8')
            else:
                self._send(404, 'text/plain; charset=utf-8',
                           f'No SVG page {idx}'.encode('utf-8'))
        else:
            self._send(404, 'text/plain; charset=utf-8',
                       f'Not found: {path}'.encode('utf-8'))

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f'  {fmt % args}\n')


def serve(schedule: dict, svg_pages: list[str],
          host: str = HOST, port: int = PORT,
          open_browser: bool = True) -> None:
    PlayerHandler.schedule_json = json.dumps(schedule).encode('utf-8')
    PlayerHandler.svg_pages = svg_pages
    server = ThreadingHTTPServer((host, port), PlayerHandler)

    url = f'http://{host}:{port}/'
    print(f'\nPlayer ready: {url}')
    print(f'  Title : {schedule["artist"]} - {schedule["title"]}')
    print(f'  Length: {schedule["total_seconds"]:.1f} s '
          f'({len(schedule["events"])} events, '
          f'{len(schedule["measures"])} measures)')
    print(f'  Sheet : {len(svg_pages)} SVG page(s)'
          if svg_pages else '  Sheet : (none)')
    print('Press Ctrl+C to stop.\n')

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
        server.shutdown()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Browser playback for cached drum scores, with '
                    'LilyPond-rendered sheet music.')
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
        '--no-svg', action='store_true',
        help='Skip LilyPond SVG compilation (faster startup, no sheet music).')
    parser.add_argument(
        '--no-drum-key', action='store_true',
        help='Suppress the Drum Key legend in the rendered score.')
    parser.add_argument(
        '--with-breaks', action='store_true',
        help='Use the legacy section-aware layout (forced \\break every 4 '
             'measures + section breaks). Default is auto layout.')
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

    # Compile SVG before starting the server so the page-count is known
    # when the browser asks for /api/score. If compilation fails we still
    # serve playback — sheet music is a feature, not a hard requirement.
    svg_pages: list[str] = []
    if not args.no_svg:
        try:
            svg_pages = compile_to_svg(
                score,
                drum_key=not args.no_drum_key,
                auto_layout=not args.with_breaks,
            )
        except Exception as exc:
            print(f'\nWARNING: SVG compilation failed — {exc}')
            print('         Continuing without sheet music.\n')

    schedule = build_schedule(score, svg_pages=len(svg_pages))
    serve(schedule, svg_pages,
          port=args.port, open_browser=not args.no_browser)


if __name__ == '__main__':
    main()
