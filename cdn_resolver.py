"""
cdn_resolver.py — Resolve a Songsterr page URL to its drum-track CDN JSON URL.

Songsterr's CDN URL has the form:

    https://<dist>.cloudfront.net/{songId}/{revisionId}/{token}/{partId}.json

The 21-character token used to be opaque ("must be reverse-engineered from
DevTools" was the v32 README's stance). It is in fact the value of the
`image` field on the song's current-revision metadata — Songsterr stores
the per-revision asset identifier under that name (the same token also
identifies the revision's preview images and audio asset paths).

A user-visible page URL gives us only songId (and sometimes a t<partId> hint):

    https://www.songsterr.com/a/wsa/<artist>-<song>-drum-tab-s<songId>
    https://www.songsterr.com/a/wsa/<artist>-<song>-drum-tab-s<songId>t<partId>

To bridge the gap, we try, in order:

  Strategy A — /api/meta/{songId}
      Single GET. Returns the latest-revision metadata as a JSON object
      with `image` (token), `revisionId`, and `tracks[]` (each entry has
      `partId`, `instrumentId`, `isDrums`, `name`, ...). Build the CDN URL
      directly from these fields. This is the same endpoint pipeline.py
      already calls to fetch title/artist — Songsterr was always returning
      the token to us, just under a non-obvious name.

  Strategy B — page HTML scrape via `curl`
      Fallback. Songsterr's page route is fronted by Cloudflare, which
      sends an HTTP 103 Early Hints response that breaks Python's `requests`
      and `urllib.request` (both treat 103 as final). curl handles 103
      correctly, so we shell out. The page embeds its full server-side
      state in <script id="state" type="application/json">; we extract
      state.meta.current and use the same logic as Strategy A.

Strategy A is preferred whenever it works because it's a single small JSON
fetch with no subprocess and no HTML parsing. B exists so that if the API
shape ever changes again we have a second source for the same data.

Public API:
    parse_songsterr_url(url) -> (song_id: int, part_id_hint: Optional[int])
    is_songsterr_page_url(url) -> bool
    is_cdn_url(url) -> bool
    resolve_cdn_url(page_url) -> str   # raises ResolveError on failure
    probe_page(url) -> dict            # diagnostic dump

Drum-track identification, in order of preference:
    1. explicit t<partId> hint in the page URL
    2. tracks[i].isDrums == true   (Songsterr's own derived field)
    3. tracks[i].instrumentId == 1024   (GM drum kit)
    4. 'drum' substring in the track name (last-resort fallback)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any, Optional

import requests

# ── Constants ─────────────────────────────────────────────────────────────────

DRUM_INSTRUMENT_ID = 1024

# Default cloudfront subdomain seen in observed CDN URLs and in the page's
# <link rel="dns-prefetch" href="//dqsljvtekg760.cloudfront.net/"> tag.
# Strategy B can also discover the host from the page <head>; A falls back
# to this constant.
DEFAULT_CLOUDFRONT_HOST = 'dqsljvtekg760.cloudfront.net'

# Browser-ish UA: Songsterr's CDN doesn't care, but the page route's bot
# protection is friendlier to browser-shaped requests.
_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)

_REQUEST_HEADERS = {
    'User-Agent': _BROWSER_UA,
    'Accept': 'application/json, text/html;q=0.9, */*;q=0.5',
    'Accept-Language': 'en-US,en;q=0.9',
}


class ResolveError(RuntimeError):
    """Raised when no strategy could produce a CDN URL."""


# ── URL classification ────────────────────────────────────────────────────────

# Page URL ends in -s<songId>[t<partId>]. The slug ("pixies-wave-of-mutilation-
# drum-tab-") is decorative and variable; we only anchor on the suffix.
_PAGE_URL_RE = re.compile(
    r'^https?://(?:www\.)?songsterr\.com/a/wsa/[^?#]*?-s(\d+)(?:t(\d+))?/?(?:[?#].*)?$'
)
_PAGE_URL_FALLBACK_RE = re.compile(
    r'songsterr\.com/[^\s]*?-s(\d+)(?:t(\d+))?(?:[/?#]|$)'
)

_CDN_URL_RE = re.compile(
    r'^https?://[^/]+\.cloudfront\.net/(\d+)/(\d+)/([^/]+)/(\d+)\.json'
)


def is_cdn_url(url: str) -> bool:
    """True iff url looks like a Songsterr cloudfront tab JSON URL."""
    return bool(_CDN_URL_RE.match(url.strip()))


def is_songsterr_page_url(url: str) -> bool:
    """True iff url looks like a Songsterr song page URL (any instrument)."""
    u = url.strip()
    return bool(_PAGE_URL_RE.match(u) or _PAGE_URL_FALLBACK_RE.search(u))


def parse_songsterr_url(url: str) -> tuple[int, Optional[int]]:
    """
    Extract (song_id, part_id_hint) from a Songsterr page URL.

    part_id_hint is None unless the URL contains an explicit t<N> suffix.
    Raises ValueError if no song ID can be found.
    """
    u = url.strip()
    m = _PAGE_URL_RE.match(u) or _PAGE_URL_FALLBACK_RE.search(u)
    if not m:
        raise ValueError(f'Not a recognisable Songsterr page URL: {url!r}')
    song_id = int(m.group(1))
    part_id = int(m.group(2)) if m.group(2) else None
    return song_id, part_id


# ── Drum-track identification (shared by both strategies) ────────────────────

def _track_part_id(track: dict, index: int) -> int:
    """
    Return the partId of a track entry.

    Prefer the track's explicit `partId` field if present; otherwise fall
    back to its index in the tracks array. The page-state form of the data
    has explicit partIds, but the raw `/api/meta/{songId}` form does not —
    Songsterr's frontend code synthesises partId from the array index, so
    we mirror that.
    """
    pid = track.get('partId') if isinstance(track, dict) else None
    return int(pid) if pid is not None else index


def _find_drum_track(tracks: list, hint: Optional[int]) -> Optional[dict]:
    """
    Locate the drum track entry in a tracks[] list.

    If `hint` is given (from a t<partId> URL suffix), find the track whose
    effective partId (explicit or index-derived) matches the hint.

    Otherwise, prefer tracks where Songsterr has explicitly set isDrums=True,
    then fall back to instrumentId==1024, then to 'drum' in the track name.
    """
    if not isinstance(tracks, list):
        return None

    if hint is not None:
        for i, t in enumerate(tracks):
            if isinstance(t, dict) and _track_part_id(t, i) == hint:
                return t
        return None

    # Pass 1: explicit isDrums flag
    for t in tracks:
        if isinstance(t, dict) and t.get('isDrums') is True:
            return t

    # Pass 2: GM drum instrument ID
    for t in tracks:
        if isinstance(t, dict):
            try:
                if int(t.get('instrumentId', -1)) == DRUM_INSTRUMENT_ID:
                    return t
            except (ValueError, TypeError):
                pass

    # Pass 3: name contains 'drum'
    for t in tracks:
        if isinstance(t, dict):
            name = t.get('name') or t.get('title') or t.get('instrument') or ''
            if isinstance(name, str) and 'drum' in name.lower():
                return t

    return None


def _build_cdn_url_from_meta(meta: dict, song_id: int,
                             hint: Optional[int],
                             host: str = DEFAULT_CLOUDFRONT_HOST) -> Optional[str]:
    """
    Given a meta-current dict (from /api/meta/{songId} or state.meta.current),
    build the drum-track CDN URL. Returns None if any required field is missing.

    Logs which field was missing so probe output is useful when shapes drift.
    """
    revision_id = meta.get('revisionId')
    token = meta.get('image')
    tracks = meta.get('tracks')

    missing = []
    if revision_id is None: missing.append('revisionId')
    if token is None:       missing.append('image (token)')
    if not tracks:          missing.append('tracks[]')
    if missing:
        keys = sorted(meta.keys()) if isinstance(meta, dict) else []
        print(f'    Could not locate {", ".join(missing)} in meta object.')
        if keys:
            print(f'    meta keys present: {keys}')
        return None

    track = _find_drum_track(tracks, hint)
    if track is None:
        if hint is not None:
            print(f'    No track found with partId={hint} (URL hint).')
        else:
            print('    No drum track identifiable in tracks[].')
        return None

    # Find the track's index in case its partId is missing (raw API form).
    try:
        track_index = tracks.index(track)
    except ValueError:
        track_index = 0
    part_id = _track_part_id(track, track_index)

    try:
        return (f'https://{host}/{int(song_id)}/{int(revision_id)}/'
                f'{str(token)}/{int(part_id)}.json')
    except (ValueError, TypeError) as e:
        print(f'    Could not assemble CDN URL: {e}')
        return None


# ── Strategy A: /api/meta/{songId} ───────────────────────────────────────────

def _fetch_meta(song_id: int, timeout: float = 15.0) -> dict:
    """Call /api/meta/{songId} and return the parsed JSON dict."""
    url = f'https://www.songsterr.com/api/meta/{song_id}'
    resp = requests.get(url, headers=_REQUEST_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _resolve_via_meta_api(page_url: str) -> Optional[str]:
    """Strategy A. Returns CDN URL or None on failure."""
    song_id, hint = parse_songsterr_url(page_url)
    try:
        meta = _fetch_meta(song_id)
    except (requests.RequestException, ValueError) as e:
        print(f'  [A] /api/meta/{song_id} failed: {e}')
        return None

    if not isinstance(meta, dict):
        print(f'  [A] /api/meta/{song_id} returned non-dict: {type(meta).__name__}')
        return None

    url = _build_cdn_url_from_meta(meta, song_id, hint)
    if url:
        print(f'  [A] Built: {url}')
    return url


# ── Strategy B: page HTML scrape via curl ────────────────────────────────────

# The page response from Songsterr embeds a JSON state blob in
#   <script id="state" type="application/json" data-integrity="...">…</script>
# (note: NOT __NEXT_DATA__ — Songsterr is not Next.js). The blob root has a
# top-level 'meta' key with a 'current' subkey that is shape-equivalent to
# the /api/meta/{songId} response above.
_STATE_SCRIPT_RE = re.compile(
    r'<script[^>]*\bid=["\']state["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)
_DNS_PREFETCH_HOST_RE = re.compile(
    r'<link[^>]*rel=["\']dns-prefetch["\'][^>]*href=["\']//([\w-]+\.cloudfront\.net)/?["\']'
)


class _CurlError(RuntimeError):
    pass


def _curl_available() -> bool:
    return shutil.which('curl') is not None


def _fetch_page_via_curl(url: str, timeout: float = 30.0) -> str:
    """
    Fetch a page HTML body using the system curl binary.

    We use curl because Cloudflare in front of songsterr.com's page route
    sends an HTTP 103 Early Hints response that Python's requests/urllib
    both incorrectly treat as final, returning length=0. curl handles 103
    transparently per RFC 8297.
    """
    if not _curl_available():
        raise _CurlError(
            'curl not found on PATH. Strategy B (page HTML scrape) requires '
            'curl, which ships with Windows 10+ and macOS by default. Either '
            'install curl, or rely on Strategy A (the meta API) — which works '
            'in most cases.'
        )
    cmd = [
        'curl', '-sSL', '--compressed',
        '--max-time', str(int(timeout)),
        '-A', _BROWSER_UA,
        '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        '-H', 'Accept-Language: en-US,en;q=0.9',
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
    except subprocess.TimeoutExpired as e:
        raise _CurlError(f'curl timed out after {timeout}s') from e
    if proc.returncode != 0:
        stderr = proc.stderr.decode('utf-8', errors='replace')[:200]
        raise _CurlError(f'curl exited {proc.returncode}: {stderr}')
    return proc.stdout.decode('utf-8', errors='replace')


def _extract_state_blob(html: str) -> Optional[dict]:
    """Pull state JSON out of <script id="state" type="application/json">…</script>."""
    m = _STATE_SCRIPT_RE.search(html)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f'    state script found but JSON parse failed: {e}')
        return None


def _extract_cdn_host(html: str) -> str:
    """Discover the cloudfront host from the page's dns-prefetch hint."""
    m = _DNS_PREFETCH_HOST_RE.search(html)
    return m.group(1) if m else DEFAULT_CLOUDFRONT_HOST


def _resolve_via_page_scrape(page_url: str) -> Optional[str]:
    """Strategy B. Returns CDN URL or None on failure."""
    song_id, hint = parse_songsterr_url(page_url)

    try:
        html = _fetch_page_via_curl(page_url)
    except _CurlError as e:
        print(f'  [B] curl fetch failed: {e}')
        return None

    if not html:
        print('  [B] curl returned empty body.')
        return None

    state = _extract_state_blob(html)
    if state is None:
        print('  [B] No <script id="state"> JSON blob found in page HTML.')
        return None

    meta_current = (state.get('meta') or {}).get('current')
    if not isinstance(meta_current, dict):
        print(f'  [B] state.meta.current is not a dict: '
              f'{type(meta_current).__name__}')
        return None

    host = _extract_cdn_host(html)
    url = _build_cdn_url_from_meta(meta_current, song_id, hint, host=host)
    if url:
        print(f'  [B] Built (via state.meta.current, host={host}): {url}')
    return url


# ── Public entry point ────────────────────────────────────────────────────────

def resolve_cdn_url(page_url: str) -> str:
    """
    Resolve a Songsterr page URL to a drum-track CDN JSON URL.

    Tries strategies in order; returns the first that succeeds.
    Raises ResolveError if all fail.
    """
    if is_cdn_url(page_url):
        # Already a CDN URL — pass through, no network cost.
        return page_url
    if not is_songsterr_page_url(page_url):
        raise ResolveError(
            f'Not a Songsterr page URL or CDN URL: {page_url!r}\n'
            f'Examples accepted:\n'
            f'  https://www.songsterr.com/a/wsa/<slug>-s<songId>\n'
            f'  https://www.songsterr.com/a/wsa/<slug>-s<songId>t<partId>\n'
            f'  https://dqsljvtekg760.cloudfront.net/<songId>/<rev>/<token>/<part>.json'
        )

    print(f'Resolving CDN URL for: {page_url}')

    for label, strategy in (
        ('A: /api/meta/{songId}', _resolve_via_meta_api),
        ('B: page HTML via curl', _resolve_via_page_scrape),
    ):
        print(f'  Trying strategy {label}...')
        try:
            url = strategy(page_url)
        except Exception as e:  # noqa: BLE001 — strategies should never raise
            print(f'  Strategy {label} crashed: {e!r}')
            url = None
        if url:
            return url

    raise ResolveError(
        'All resolution strategies failed. Run `python main.py <PAGE_URL> '
        '--probe` to dump what each strategy saw, and paste the output to a '
        'follow-up session — Songsterr probably changed an internal JSON shape.'
    )


# ── Diagnostic mode ───────────────────────────────────────────────────────────

def probe_page(page_url: str) -> dict:
    """
    Diagnostic dump for a Songsterr page URL — does NOT raise.

    Returns a dict with structured info about what each strategy saw.
    Intended for paste-back when the resolver breaks: a future session can
    diagnose and patch from this output without needing to re-derive the
    API shape from scratch.
    """
    out: dict[str, Any] = {
        'page_url': page_url,
        'song_id': None,
        'part_id_hint': None,
        'meta_api_status': None,
        'meta_api_keys': None,
        'meta_api_has_image': None,
        'meta_api_has_revisionId': None,
        'meta_api_tracks_count': None,
        'meta_api_drum_partId': None,
        'curl_available': _curl_available(),
        'page_status': None,
        'page_state_found': False,
        'page_state_keys': None,
        'page_meta_current_image': None,
        'page_dns_prefetch_host': None,
        'attempted_cdn_url': None,
        'errors': [],
    }

    try:
        sid, hint = parse_songsterr_url(page_url)
        out['song_id'] = sid
        out['part_id_hint'] = hint
    except ValueError as e:
        out['errors'].append(f'parse_songsterr_url: {e}')
        return out

    # Probe meta API
    try:
        meta = _fetch_meta(sid)
        if isinstance(meta, dict):
            out['meta_api_status'] = 'ok'
            out['meta_api_keys'] = sorted(meta.keys())
            out['meta_api_has_image'] = 'image' in meta
            out['meta_api_has_revisionId'] = 'revisionId' in meta
            tracks = meta.get('tracks')
            if isinstance(tracks, list):
                out['meta_api_tracks_count'] = len(tracks)
                drum = _find_drum_track(tracks, hint)
                if drum:
                    try:
                        idx = tracks.index(drum)
                    except ValueError:
                        idx = 0
                    out['meta_api_drum_partId'] = _track_part_id(drum, idx)
        else:
            out['meta_api_status'] = f'non-dict: {type(meta).__name__}'
    except Exception as e:  # noqa: BLE001
        out['meta_api_status'] = f'error: {e}'

    # Probe page HTML via curl
    if out['curl_available']:
        try:
            html = _fetch_page_via_curl(page_url)
            out['page_status'] = f'ok ({len(html)} chars)'
            state = _extract_state_blob(html)
            if state is not None:
                out['page_state_found'] = True
                out['page_state_keys'] = sorted(state.keys())[:20]
                meta_current = (state.get('meta') or {}).get('current') or {}
                if isinstance(meta_current, dict):
                    out['page_meta_current_image'] = meta_current.get('image')
            out['page_dns_prefetch_host'] = _extract_cdn_host(html)
        except Exception as e:  # noqa: BLE001
            out['errors'].append(f'page scrape: {e}')
    else:
        out['errors'].append('curl not on PATH; strategy B unavailable')

    # Try the full resolver
    try:
        out['attempted_cdn_url'] = resolve_cdn_url(page_url)
    except Exception as e:  # noqa: BLE001
        out['errors'].append(f'resolve_cdn_url: {e}')

    return out
