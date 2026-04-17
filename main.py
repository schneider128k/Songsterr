"""
main.py — CLI entry point for the Songsterr drum tab → PDF pipeline.

Usage:
    python main.py <CDN_URL>      Fetch, parse, and compile a drum tab to PDF.
    python main.py                List all locally cached scores.
    python main.py <CDN_URL> --no-drum-key   Skip the Drum Key legend.

How to get a CDN URL from Songsterr:
    1. Open the song page on songsterr.com
    2. Open DevTools (F12) → Network tab → filter 'cloudfront' → Fetch/XHR
    3. Reload the page
    4. Find the request ending in /<partId>.json for the drum track
    5. Right-click → Copy → Copy URL

Example URL:
    https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json
"""

import sys

from cache import list_cached
from pipeline import run_pipeline


def main():
    args = sys.argv[1:]
    drum_key = '--no-drum-key' not in args
    args = [a for a in args if a != '--no-drum-key']

    if not args:
        print('Cached scores:')
        print()
        list_cached()
        print()
        print('Usage: python main.py <CDN_URL> [--no-drum-key]')
        sys.exit(0)

    cdn_url = args[0]
    try:
        pdf_path = run_pipeline(cdn_url, drum_key=drum_key)
        print()
        print(f'Done! PDF saved to: {pdf_path}')
    except Exception as e:
        print(f'Error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
