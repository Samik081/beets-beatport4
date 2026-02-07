"""Tests for Beatport4Client URL construction."""

from beetsplug.beatport4 import Beatport4Client


class TestMakeUrl:
    def setup_method(self):
        """Create a minimal client stub without triggering __init__."""
        self.client = object.__new__(Beatport4Client)
        self.client._api_base = 'https://api.beatport.com/v4'

    def test_endpoint_with_leading_slash(self):
        url = self.client._make_url('/catalog/releases/')
        assert url == 'https://api.beatport.com/v4/catalog/releases/'

    def test_endpoint_without_leading_slash(self):
        url = self.client._make_url('catalog/releases/')
        assert url == 'https://api.beatport.com/v4/catalog/releases/'

    def test_endpoint_with_query_params(self):
        url = self.client._make_url('/search', query={'q': 'test', 'page': 1})
        assert 'q=test' in url
        assert 'page=1' in url
        assert url.startswith('https://api.beatport.com/v4/search?')

    def test_endpoint_without_query_params(self):
        url = self.client._make_url('/catalog/tracks/123/')
        assert '?' not in url
