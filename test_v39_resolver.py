"""test_v39_resolver.py — unit tests for v39's host-probing logic.

Mocks `requests.head` to verify _try_hosts_for and _build_cdn_url_from_meta
without touching the network. Live verification is in test_cdn_smoke.py.
"""
import unittest
from unittest.mock import patch, MagicMock

import cdn_resolver


def _mock_head(status_map):
    """
    Build a fake `requests.head` whose status code depends on the URL.

    Keys of status_map are substrings to match in the URL; value is the
    status code to return. First match wins. URLs not matching any key
    raise a connection error to simulate "host unreachable."
    """
    def head(url, headers=None, timeout=None, allow_redirects=False):
        for needle, status in status_map.items():
            if needle in url:
                m = MagicMock()
                m.status_code = status
                return m
        # Default: raise so _validate_cdn_url returns False without
        # confusing a real network timeout with a real 404.
        raise cdn_resolver.requests.RequestException(f'no match for {url}')
    return head


class TryHostsTests(unittest.TestCase):
    """Verify _try_hosts_for tries hosts in order and picks the first 200."""

    def test_returns_new_host_url_when_new_host_serves(self):
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 200,
                                      'dqsljvtekg760': 200})):
            url = cdn_resolver._try_hosts_for(
                song_id=412647, revision_id=6421553,
                image='v0-3-2-x-stage', part_id=8,
            )
        self.assertIsNotNone(url)
        self.assertIn('d3d3l6a6rcgkaf', url)
        # Should be the first host in KNOWN_CDN_HOSTS, not a later one,
        # even though the older host would also serve.
        self.assertNotIn('dqsljvtekg760', url)

    def test_falls_back_to_old_host_when_new_host_404s(self):
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 404,
                                      'dqsljvtekg760': 200})):
            url = cdn_resolver._try_hosts_for(
                song_id=16093, revision_id=418898,
                image='qE0QIyDkUuju6PtZ-Hg3I', part_id=3,
            )
        self.assertIsNotNone(url)
        self.assertIn('dqsljvtekg760', url)

    def test_returns_none_when_all_hosts_404(self):
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 403,
                                      'dqsljvtekg760': 404})):
            url = cdn_resolver._try_hosts_for(
                song_id=99999, revision_id=1,
                image='nonexistent', part_id=0,
            )
        self.assertIsNone(url)

    def test_returns_none_when_network_unreachable(self):
        # No URL matches → mock always raises RequestException.
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({})):
            url = cdn_resolver._try_hosts_for(
                song_id=16093, revision_id=418898,
                image='qE0QIyDkUuju6PtZ-Hg3I', part_id=3,
            )
        self.assertIsNone(url)

    def test_url_path_matches_documented_layout(self):
        """`<host>/<songId>/<revisionId>/<image>/<partId>.json`"""
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 200})):
            url = cdn_resolver._try_hosts_for(
                song_id=412647, revision_id=6421553,
                image='v0-3-2-lbH6AfE7HKqgxgX4-stage', part_id=8,
            )
        self.assertEqual(
            url,
            'https://d3d3l6a6rcgkaf.cloudfront.net/'
            '412647/6421553/v0-3-2-lbH6AfE7HKqgxgX4-stage/8.json',
        )


class BuildCdnUrlFromMetaTests(unittest.TestCase):
    """Smoke-test _build_cdn_url_from_meta against the three reference shapes."""

    WAVE_OF_MUTILATION_META = {
        'revisionId': 418898,
        'image': 'qE0QIyDkUuju6PtZ-Hg3I',
        'tracks': [
            {'instrumentId': 30, 'name': 'Joey Santiago'},
            {'instrumentId': 30, 'name': 'Black Francis'},
            {'instrumentId': 34, 'name': 'Kim Deal'},
            {'instrumentId': 1024, 'name': 'David Lovering'},  # drums @ idx 3
        ],
    }

    SQUARE_HAMMER_META = {
        'revisionId': 6421553,
        'image': 'v0-3-2-lbH6AfE7HKqgxgX4-stage',
        'tracks': [
            {'instrumentId': 53}, {'instrumentId': 53}, {'instrumentId': 30},
            {'instrumentId': 30}, {'instrumentId': 34}, {'instrumentId': 8},
            {'instrumentId': 4},  {'instrumentId': 18},
            {'instrumentId': 1024, 'name': 'Earth'},  # drums @ idx 8
        ],
    }

    EYE_OF_TIGER_META = {
        'revisionId': 5112810,
        'image': 'v5-2-1-JBCoObK1mkX_PcW0',
        'tracks': [
            {'instrumentId': 68}, {'instrumentId': 30}, {'instrumentId': 30},
            {'instrumentId': 29}, {'instrumentId': 34}, {'instrumentId': 50},
            {'instrumentId': 0},  {'instrumentId': 119},
            {'instrumentId': 1024, 'name': 'Ludwig Drums'},   # drums @ idx 8
            {'instrumentId': 1024, 'name': 'Tambourine'},     # drums @ idx 9
        ],
    }

    def test_old_host_song_resolves_to_old_host(self):
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 404,
                                      'dqsljvtekg760': 200})):
            url = cdn_resolver._build_cdn_url_from_meta(
                self.WAVE_OF_MUTILATION_META, song_id=16093, hint=None,
            )
        self.assertIsNotNone(url)
        self.assertIn('dqsljvtekg760', url)
        self.assertIn('/16093/418898/qE0QIyDkUuju6PtZ-Hg3I/3.json', url)

    def test_new_host_song_resolves_to_new_host(self):
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 200,
                                      'dqsljvtekg760': 200})):
            url = cdn_resolver._build_cdn_url_from_meta(
                self.SQUARE_HAMMER_META, song_id=412647, hint=None,
            )
        self.assertIsNotNone(url)
        self.assertIn('d3d3l6a6rcgkaf', url)
        self.assertIn('/412647/6421553/v0-3-2-lbH6AfE7HKqgxgX4-stage/8.json', url)

    def test_eye_of_tiger_picks_kit_not_tambourine_by_default(self):
        """Without a hint, the resolver picks the first instrumentId==1024
        track — the Ludwig kit at index 8, not the Tambourine at index 9."""
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 404,
                                      'dqsljvtekg760': 200})):
            url = cdn_resolver._build_cdn_url_from_meta(
                self.EYE_OF_TIGER_META, song_id=89089, hint=None,
            )
        self.assertIsNotNone(url)
        self.assertIn('/8.json', url)
        self.assertNotIn('/9.json', url)

    def test_explicit_partid_hint_picks_tambourine(self):
        """`...s89089t9` URL hint overrides the kit-default heuristic."""
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'dqsljvtekg760': 200})):
            url = cdn_resolver._build_cdn_url_from_meta(
                self.EYE_OF_TIGER_META, song_id=89089, hint=9,
            )
        self.assertIsNotNone(url)
        self.assertIn('/9.json', url)

    def test_returns_none_when_no_known_host_serves(self):
        with patch.object(cdn_resolver.requests, 'head',
                          _mock_head({'d3d3l6a6rcgkaf': 403,
                                      'dqsljvtekg760': 403})):
            url = cdn_resolver._build_cdn_url_from_meta(
                self.SQUARE_HAMMER_META, song_id=412647, hint=None,
            )
        self.assertIsNone(url)

    def test_returns_none_when_meta_missing_required_field(self):
        bad_meta = {'image': 'x', 'tracks': [{'instrumentId': 1024}]}
        # No mock needed — should bail out before any HTTP call.
        url = cdn_resolver._build_cdn_url_from_meta(
            bad_meta, song_id=1, hint=None,
        )
        self.assertIsNone(url)


if __name__ == '__main__':
    unittest.main(verbosity=2)
