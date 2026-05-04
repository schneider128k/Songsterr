"""test_cdn_smoke.py — sanity-check that resolve_cdn_url produces working URLs.

The CDN host is hardcoded in cdn_resolver (DEFAULT_CLOUDFRONT_HOST) because
Songsterr does not expose it via any API or page metadata. When Songsterr
migrates the host (as in mid-2026, breaking v34/v35/v36/v37 silently),
this test is the early warning.

Run it after touching networking code, or any time a fresh fetch hits 403.

Usage:
    python test_cdn_smoke.py

Exits 0 on full pass, 1 on any failure.
"""
import sys

import requests

from cdn_resolver import resolve_cdn_url

# Three diverse songs: different songIds, different revisions, different
# image-token shapes (Wave of Mutilation has the old 21-character opaque
# token, Square Hammer has the new structured 'v0-3-2-...-stage' shape).
# If a single global host change breaks the resolver, all three will
# fail at the fetch stage with HTTP 403.
KNOWN_SONGS = [
    ("https://www.songsterr.com/a/wsa/pixies-wave-of-mutilation-drum-tab-s16093",
     "Wave of Mutilation"),
    ("https://www.songsterr.com/a/wsa/ghost-square-hammer-drum-tab-s412647",
     "Square Hammer"),
    ("https://www.songsterr.com/a/wsa/survivor-eye-of-the-tiger-drum-tab-s89089",
     "Eye of the Tiger"),
]


def main() -> int:
    failures = []
    for page_url, name in KNOWN_SONGS:
        print(f"--- {name} ---")
        try:
            cdn_url = resolve_cdn_url(page_url)
        except Exception as e:  # noqa: BLE001 — exhaustive on purpose
            print(f"  resolve failed: {e}")
            failures.append((name, "resolve", str(e)))
            continue

        try:
            resp = requests.head(cdn_url, timeout=15, allow_redirects=True)
            status = resp.status_code
        except Exception as e:  # noqa: BLE001
            print(f"  HEAD failed: {e}")
            failures.append((name, "fetch", str(e)))
            continue

        if status == 200:
            print(f"  OK ({status})")
        else:
            print(f"  BAD ({status}) — {cdn_url}")
            failures.append((name, "status", f"HTTP {status}"))

    print()
    if failures:
        print(f"FAIL: {len(failures)}/{len(KNOWN_SONGS)} song(s) broken")
        for name, stage, detail in failures:
            print(f"  - {name} ({stage}): {detail}")
        # Most common cause: host migration. Surface the diagnosis hint.
        if any(stage == "status" and "403" in detail
               for _, stage, detail in failures):
            print()
            print("HTTP 403 on multiple songs almost always means Songsterr")
            print("migrated the CloudFront host. Find the new host via")
            print("DevTools (Network, filter cloudfront, reload page) and")
            print("update DEFAULT_CLOUDFRONT_HOST in cdn_resolver.py.")
        return 1

    print(f"PASS: all {len(KNOWN_SONGS)} songs resolved and serve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
