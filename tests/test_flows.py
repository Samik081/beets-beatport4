"""End-to-end plugin flow tests with HTTP mocking.

Tests complete plugin method flows: search → parse → beets objects.
"""

import time
from unittest.mock import MagicMock

import responses
from beets.autotag.hooks import AlbumInfo, TrackInfo

from beetsplug.beatport4 import (
    Beatport4Client,
    BeatportOAuthToken,
)
from tests.conftest import load_fixture

API_BASE = "https://api.beatport.com/v4"


def _make_token():
    return BeatportOAuthToken(
        access_token="tok",
        expires_at=time.time() + 9999,
        refresh_token="ref",
    )


def _make_authed_client():
    """Create a client stub bypassing __init__."""
    client = object.__new__(Beatport4Client)
    client._api_base = API_BASE
    client._api_client_id = "test_id"
    client._beatport_redirect_uri = f"{API_BASE}/auth/o/post-message/"
    client.username = "testuser"
    client.password = "testpass"
    client.beatport_token = _make_token()
    client._log = MagicMock()
    return client


def _register_release_endpoints():
    """Register responses for fetching release 4001 with its tracks."""
    responses.add(
        responses.GET,
        f"{API_BASE}/catalog/releases/4001/",
        json=load_fixture("release_detail.json"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/catalog/releases/4001/tracks/",
        json=load_fixture("release_tracks.json"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/catalog/tracks/3001/",
        json=load_fixture("track_detail_3001.json"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/catalog/tracks/3002/",
        json=load_fixture("track_detail_3002.json"),
        status=200,
    )


# ──────────────────────────────────────────────────────────────
# candidates() flow
# ──────────────────────────────────────────────────────────────


class TestCandidatesFlow:
    @responses.activate
    def test_candidates_returns_album_info_list(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        # search returns releases
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json=load_fixture("search_releases.json"),
            status=200,
        )
        # get_release for release 4001
        _register_release_endpoints()
        # get_release for release 4002 (reuse same data)
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4002/",
            json=load_fixture("release_detail.json"),
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4002/tracks/",
            json=load_fixture("release_tracks.json"),
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=load_fixture("track_detail_3001.json"),
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3002/",
            json=load_fixture("track_detail_3002.json"),
            status=200,
        )

        results = plugin.candidates([], "Synthwave Runner", "Neon Dreams", False)
        assert len(results) == 2
        assert all(isinstance(r, AlbumInfo) for r in results)
        assert results[0].album == "Neon Dreams EP"
        assert results[0].data_source == "Beatport"
        assert len(results[0].tracks) == 2

    @responses.activate
    def test_candidates_va_likely_omits_artist(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json={"releases": [], "tracks": []},
            status=200,
        )

        results = plugin.candidates([], "Artist", "Album", va_likely=True)
        assert results == []
        # Verify the search query only contained the album name
        req = responses.calls[0].request
        assert "Artist" not in req.url
        assert "Album" in req.url

    @responses.activate
    def test_candidates_api_error_returns_empty(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json={"error": "internal"},
            status=500,
        )

        results = plugin.candidates([], "Artist", "Album", False)
        assert results == []


# ──────────────────────────────────────────────────────────────
# item_candidates() flow
# ──────────────────────────────────────────────────────────────


class TestItemCandidatesFlow:
    @responses.activate
    def test_item_candidates_returns_track_info_list(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json=load_fixture("search_tracks.json"),
            status=200,
        )

        results = plugin.item_candidates(None, "Synthwave Runner", "Midnight Circuit")
        assert len(results) == 2
        assert all(isinstance(t, TrackInfo) for t in results)
        assert results[0].title == "Midnight Circuit"
        assert results[0].data_source == "Beatport"
        # Second track has non-Original mix, so title includes mix name
        assert "Extended Mix" in results[1].title

    @responses.activate
    def test_item_candidates_api_error_returns_empty(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            body=ConnectionError("timeout"),
        )

        results = plugin.item_candidates(None, "Artist", "Track")
        assert results == []


# ──────────────────────────────────────────────────────────────
# album_for_id() flow
# ──────────────────────────────────────────────────────────────


class TestAlbumForIdFlow:
    @responses.activate
    def test_album_for_id_with_url(self, plugin):
        client = _make_authed_client()
        plugin.client = client
        _register_release_endpoints()

        url = "https://beatport.com/release/neon-dreams-ep/4001"
        result = plugin.album_for_id(url)
        assert isinstance(result, AlbumInfo)
        assert result.album == "Neon Dreams EP"
        assert result.year == 2024
        assert result.label == "Future Sounds"

    @responses.activate
    def test_album_for_id_with_numeric_id(self, plugin):
        client = _make_authed_client()
        plugin.client = client
        _register_release_endpoints()

        result = plugin.album_for_id("4001")
        assert isinstance(result, AlbumInfo)
        assert result.album_id == "4001"

    def test_album_for_id_invalid_returns_none(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        result = plugin.album_for_id("not-an-id")
        assert result is None

    def test_album_for_id_empty_returns_none(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        result = plugin.album_for_id("")
        assert result is None

    @responses.activate
    def test_album_for_id_not_found_returns_none(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/9999/",
            json={"detail": "Not found"},
            status=404,
        )

        result = plugin.album_for_id("9999")
        assert result is None


# ──────────────────────────────────────────────────────────────
# track_for_id() flow
# ──────────────────────────────────────────────────────────────


class TestTrackForIdFlow:
    @responses.activate
    def test_track_for_id_with_url(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=load_fixture("track_detail_3001.json"),
            status=200,
        )

        url = "https://beatport.com/track/midnight-circuit/3001"
        result = plugin.track_for_id(url)
        assert isinstance(result, TrackInfo)
        assert result.title == "Midnight Circuit"
        assert result.bpm == 126

    @responses.activate
    def test_track_for_id_with_numeric_id(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3002/",
            json=load_fixture("track_detail_3002.json"),
            status=200,
        )

        result = plugin.track_for_id("3002")
        assert isinstance(result, TrackInfo)
        # Extended Mix should be in title
        assert "Extended Mix" in result.title

    def test_track_for_id_invalid_returns_none(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        result = plugin.track_for_id("not-valid")
        assert result is None

    @responses.activate
    def test_track_for_id_not_found_returns_none(self, plugin):
        client = _make_authed_client()
        plugin.client = client

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/9999/",
            json={"detail": "Not found"},
            status=404,
        )

        result = plugin.track_for_id("9999")
        assert result is None


# ──────────────────────────────────────────────────────────────
# Singleton enrichment flow
# ──────────────────────────────────────────────────────────────


class TestSingletonEnrichmentFlow:
    @responses.activate
    def test_singleton_gets_album_metadata(self, plugin):
        """When singletons_with_album_metadata is enabled, track_for_id
        enriches TrackInfo with album-level fields."""
        client = _make_authed_client()
        plugin.client = client

        # Enable singleton enrichment
        plugin.config["singletons_with_album_metadata"]["enabled"].set(True)

        # Track detail (has release with no tracks -> triggers enrichment)
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=load_fixture("track_detail_3001.json"),
            status=200,
        )
        # Fetching full release for enrichment
        _register_release_endpoints()

        result = plugin.track_for_id("3001")
        assert isinstance(result, TrackInfo)
        # Should have album-level metadata from the release
        assert result.album == "Neon Dreams EP"
        assert result.label == "Future Sounds"
        assert result.catalognum == "FS042"
        assert result.year == 2024
        assert result.albumartist == "Synthwave Runner"

    @responses.activate
    def test_singleton_without_enrichment(self, plugin):
        """Without enrichment enabled, no album metadata is populated."""
        client = _make_authed_client()
        plugin.client = client

        # Disabled by default
        assert plugin.config["singletons_with_album_metadata"]["enabled"].get() is False

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=load_fixture("track_detail_3001.json"),
            status=200,
        )

        result = plugin.track_for_id("3001")
        assert isinstance(result, TrackInfo)
        assert not hasattr(result, "album") or result.album is None
