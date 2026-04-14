"""
pipeline.py — Fetch, parse, cache, and compile a Songsterr drum tab to PDF.

This module contains the core pipeline logic extracted from the Colab notebook
(Steps 6-8). It is called by main.py.
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

SCORES_DIR = os.path.join(os.path.dirname(__file__), 'scores')


def fetch_and_parse(cdn_url: str) -> Score:
    """
    Given a Songsterr CDN URL, return a Score IR.
    Uses the local cache if available; otherwise fetches from CDN and caches.
    """
    m = re.search(r'cloudfront\.net/(\d+)/[^/]+/[^/]+/(\d+)\.json', cdn_url)
    if not m:
        raise ValueError(f'Cannot parse song_id/part_id from URL: {cdn_url}')
    song_id = int(m.group(1))
    part_id = int(m.group(2))

    # Try cache first
    score = load_score(song_id, part_id)
    if score is not None:
        print(f'Loaded from cache: {score.artist} - {score.title}')
        return score

    # Fetch tab JSON from CDN
    print('Fetching tab data from CDN...')
    resp = requests.get(cdn_url, timeout=20)
    resp.raise_for_status()
    if not resp.text.startswith('{'):
        raise ValueError(f'Response is not JSON: {resp.text[:80]}')
    tab_data = resp.json()

    if tab_data.get('instrumentId') != 1024:
        print(f'WARNING: instrumentId={tab_data.get("instrumentId")} — may not be drums')

    # Fetch title/artist from Songsterr metadata API
    try:
        meta   = requests.get(
            f'https://www.songsterr.com/api/meta/{song_id}', timeout=10).json()
        title  = meta.get('title', tab_data.get('name', 'Unknown'))
        artist = meta.get('artist', 'Unknown')
    except Exception:
        title  = tab_data.get('name', 'Unknown')
        artist = 'Unknown'

    print(f'Parsing: {artist} - {title}...')
    score = parse_json(tab_data, title=title, artist=artist)
    save_score(score)

    # Print summary
    print(f'  Measures : {len(score.measures)}')
    print(f'  Tempos   : {[(str(t.position), t.bpm) for t in score.tempo_changes]}')
    sigs = {}
    for meas in score.measures:
        sigs[meas.time_sig] = sigs.get(meas.time_sig, 0) + 1
    print(f'  Time sigs: {dict(sigs)}')

    return score


def compile_to_pdf(score: Score, output_dir: str = SCORES_DIR) -> str:
    """
    Emit LilyPond source for score, compile to PDF, return the PDF path.
    Auto-detects the LilyPond binary.
    """
    os.makedirs(output_dir, exist_ok=True)

    lily_bin     = find_lilypond()
    lily_version = get_lilypond_version(lily_bin)
    print(f'Using LilyPond {lily_version} at {lily_bin}')

    ly_source = emit_lilypond(score, version=lily_version)

    safe     = re.sub(r'[^\w\s-]', '', f'{score.artist}_{score.title}').replace(' ', '_')
    ly_path  = os.path.join(output_dir, f'{safe}_drums.ly')
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
        lines     = result.stderr.splitlines()
        errors    = [l for l in lines if 'error' in l.lower()]
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


def run_pipeline(cdn_url: str) -> str:
    """Full pipeline: fetch → parse → cache → emit → compile → PDF path."""
    score    = fetch_and_parse(cdn_url)
    pdf_path = compile_to_pdf(score)
    return pdf_path
