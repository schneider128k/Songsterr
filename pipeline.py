"""
pipeline.py — Fetch, parse, cache, and compile a Songsterr drum tab to PDF.

Accepts either:
  - a Songsterr CDN URL (cloudfront.net/.../<partId>.json), or
  - a Songsterr song page URL (songsterr.com/a/wsa/...).

For page URLs, cdn_resolver.resolve_cdn_url() is invoked first to discover
the actual CDN URL automatically (Milestone 5).
"""

import os
import re
import subprocess

import requests

from ir import Score
from parser import parse_json
from cache import save_score, load_score, list_cached
from emitter import emit_lilypond
from lilypond_utils import find_lilypond, get_lilypond_version
from cdn_resolver import (
    resolve_cdn_url, is_cdn_url, is_songsterr_page_url, ResolveError,
)

SCORES_DIR = os.path.join(os.path.dirname(__file__), 'scores')


def _ensure_cdn_url(url: str) -> str:
    """Accept either a CDN URL or a Songsterr page URL; return a CDN URL."""
    url = url.strip()
    if is_cdn_url(url):
        return url
    if is_songsterr_page_url(url):
        return resolve_cdn_url(url)
    raise ValueError(
        f'Input is neither a Songsterr CDN URL nor a page URL: {url!r}\n'
        f'Examples accepted:\n'
        f'  https://www.songsterr.com/a/wsa/pixies-wave-of-mutilation-drum-tab-s16093\n'
        f'  https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json'
    )


def fetch_and_parse(url: str) -> Score:
    """Given a Songsterr CDN URL or song page URL, return a Score IR."""
    cdn_url = _ensure_cdn_url(url)

    m = re.search(r'cloudfront\.net/(\d+)/[^/]+/[^/]+/(\d+)\.json', cdn_url)
    if not m:
        raise ValueError(f'Cannot parse song_id/part_id from URL: {cdn_url}')
    song_id = int(m.group(1))
    part_id = int(m.group(2))

    score = load_score(song_id, part_id)
    if score is not None:
        print(f'Loaded from cache: {score.artist} - {score.title}')
        return score

    print('Fetching tab data from CDN...')
    resp = requests.get(cdn_url, timeout=20)
    resp.raise_for_status()
    if not resp.text.startswith('{'):
        raise ValueError(f'Response is not JSON: {resp.text[:80]}')

    tab_data = resp.json()
    if tab_data.get('instrumentId') != 1024:
        print(f'WARNING: instrumentId={tab_data.get("instrumentId")} — may not be drums')

    try:
        meta = requests.get(
            f'https://www.songsterr.com/api/meta/{song_id}', timeout=10).json()
        title = meta.get('title', tab_data.get('name', 'Unknown'))
        artist = meta.get('artist', 'Unknown')
    except Exception:
        title = tab_data.get('name', 'Unknown')
        artist = 'Unknown'

    print(f'Parsing: {artist} - {title}...')
    score = parse_json(tab_data, title=title, artist=artist)
    save_score(score)

    print(f'  Measures : {len(score.measures)}')
    print(f'  Tempos   : {[(str(t.position), t.bpm) for t in score.tempo_changes]}')
    sigs = {}
    for meas in score.measures:
        sigs[meas.time_sig] = sigs.get(meas.time_sig, 0) + 1
    print(f'  Time sigs: {dict(sigs)}')

    return score


def compile_to_pdf(score: Score, output_dir: str = SCORES_DIR,
                   drum_key: bool = True, auto_layout: bool = True) -> str:
    """
    Emit LilyPond source for score, compile to PDF, return the PDF path.

    auto_layout=True: no forced line breaks; LilyPond decides layout (default,
                      v35+). Produces compact output that fills page width.
    auto_layout=False: emit \\break before each section and after every 4
                      measures (pre-v35 layout).
    """
    os.makedirs(output_dir, exist_ok=True)

    lily_bin = find_lilypond()
    lily_version = get_lilypond_version(lily_bin)
    print(f'Using LilyPond {lily_version} at {lily_bin}')

    ly_source = emit_lilypond(score, version=lily_version,
                              drum_key=drum_key, auto_layout=auto_layout)

    safe = re.sub(r'[^\w\s-]', '', f'{score.artist}_{score.title}').replace(' ', '_')
    ly_path = os.path.join(output_dir, f'{safe}_drums.ly')
    pdf_path = os.path.join(output_dir, f'{safe}_drums.pdf')

    with open(ly_path, 'w') as f:
        f.write(ly_source)
    print(f'Written: {ly_path} ({len(ly_source):,} chars)')

    print('Compiling with LilyPond...')
    result = subprocess.run(
        [lily_bin, f'--output={output_dir}', ly_path],
        capture_output=True, text=True
    )

    if result.stderr:
        lines = result.stderr.splitlines()
        errors = [l for l in lines if 'error' in l.lower()]
        barchecks = [l for l in lines if 'barcheck' in l.lower()]
        if errors:
            print('ERRORS:')
            print('\n'.join(errors[:20]))
        if barchecks:
            print(f'{len(barchecks)} bar check warning(s):')
            for l in barchecks[:10]:
                print(l)

    if not os.path.exists(pdf_path):
        raise RuntimeError('PDF not produced — check errors above')

    print(f'PDF ready: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)')
    return pdf_path


def run_pipeline(url: str, drum_key: bool = True,
                 auto_layout: bool = True) -> str:
    """Full pipeline: fetch -> parse -> cache -> emit -> compile -> PDF path.

    url may be either a Songsterr CDN URL or a Songsterr song page URL.
    auto_layout: see compile_to_pdf.
    """
    score = fetch_and_parse(url)
    pdf_path = compile_to_pdf(score, drum_key=drum_key, auto_layout=auto_layout)
    return pdf_path
