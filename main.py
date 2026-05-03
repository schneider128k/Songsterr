"""
main.py — CLI entry point for the Songsterr drum tab → PDF pipeline.

Usage:
    python main.py <URL>                 Fetch, parse, and compile to PDF.
    python main.py <URL> --no-drum-key   Skip the Drum Key legend.
    python main.py <URL> --with-breaks   Force section + every-4-measure
                                         line breaks (pre-v35 layout).
                                         Default is auto-layout — LilyPond
                                         decides line breaks.
    python main.py <URL> --probe         Diagnostic: show what the resolver
                                         can see for this URL (no compile).
    python main.py                       List all locally cached scores.

<URL> may be either:

  • a Songsterr song page URL, e.g.
        https://www.songsterr.com/a/wsa/pixies-wave-of-mutilation-drum-tab-s16093
        https://www.songsterr.com/a/wsa/...-drum-tab-s16093t3   (multi-track)

  • a direct Songsterr CDN URL, e.g.
        https://dqsljvtekg760.cloudfront.net/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json

If the resolver fails (Songsterr changed an internal JSON shape), run with
--probe to dump a diagnostic and paste it into a follow-up session.
"""

import json
import sys

from cache import list_cached
from pipeline import run_pipeline


def _do_probe(url: str) -> int:
    from cdn_resolver import probe_page
    info = probe_page(url)
    print()
    print('=== PROBE RESULT ===')
    print(json.dumps(info, indent=2, default=str))
    print('=== END PROBE ===')
    return 0 if info.get('attempted_cdn_url') else 1


def main():
    args = sys.argv[1:]

    drum_key = '--no-drum-key' not in args
    auto_layout = '--with-breaks' not in args
    probe = '--probe' in args
    args = [a for a in args
            if a not in ('--no-drum-key', '--probe', '--with-breaks')]

    if not args:
        print('Cached scores:')
        print()
        list_cached()
        print()
        print('Usage: python main.py <PAGE_URL_or_CDN_URL> '
              '[--no-drum-key] [--with-breaks] [--probe]')
        sys.exit(0)

    url = args[0]

    if probe:
        sys.exit(_do_probe(url))

    try:
        pdf_path = run_pipeline(url, drum_key=drum_key, auto_layout=auto_layout)
        print()
        print(f'Done! PDF saved to: {pdf_path}')
    except Exception as e:
        print(f'Error: {e}')
        print()
        print('Tip: run with --probe to see what the CDN resolver could find,')
        print('     or pass a direct cloudfront.net/.../<partId>.json URL to bypass it.')
        sys.exit(1)


if __name__ == '__main__':
    main()
