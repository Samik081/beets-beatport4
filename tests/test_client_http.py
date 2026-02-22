"""HTTP-level tests for Beatport4Client using the responses library."""

import time
from unittest.mock import MagicMock

import pytest
import responses

from beetsplug.beatport4 import (
    Beatport4Client,
    BeatportAPIError,
    BeatportMyAccount,
    BeatportOAuthToken,
    BeatportRelease,
    BeatportTrack,
)
from tests.conftest import load_fixture

API_BASE = "https://api.beatport.com/v4"


def _make_token(expired=False):
    """Create a valid BeatportOAuthToken for testing."""
    data = {
        "access_token": "test_access_token",
        "expires_at": 0 if expired else time.time() + 9999,
        "refresh_token": "test_refresh_token",
    }
    return BeatportOAuthToken(**data)


def _make_client(token=None):
    """Create a Beatport4Client without triggering __init__."""
    client = object.__new__(Beatport4Client)
    client._api_base = API_BASE
    client._api_client_id = "test_client_id"
    client._beatport_redirect_uri = f"{API_BASE}/auth/o/post-message/"
    client.username = "testuser"
    client.password = "testpass"
    client.beatport_token = token or _make_token()
    client._log = MagicMock()
    return client


# ──────────────────────────────────────────────────────────────
# Client ID scraping
# ──────────────────────────────────────────────────────────────


class TestFetchClientId:
    @responses.activate
    def test_scrapes_client_id_from_docs(self):
        docs_html = load_fixture("docs_page.html")
        docs_js = load_fixture("docs_script.js")

        responses.add(
            responses.GET,
            f"{API_BASE}/docs/",
            body=docs_html,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.beatport.com/v4/docs/static/js/swagger-bundle.js",
            body=docs_js,
            status=200,
        )

        client = _make_client()
        result = client._fetch_beatport_client_id()
        assert result == "test_client_id_12345"

    @responses.activate
    def test_raises_when_no_client_id_found(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/docs/",
            body="<html><body>no scripts</body></html>",
            status=200,
        )

        client = _make_client()
        with pytest.raises(
            BeatportAPIError, match="Could not fetch API_CLIENT_ID"
        ):
            client._fetch_beatport_client_id()


# ──────────────────────────────────────────────────────────────
# Authorization flow
# ──────────────────────────────────────────────────────────────


class TestAuthorize:
    @responses.activate
    def test_full_auth_flow(self):
        login_data = load_fixture("auth_login.json")
        token_data = load_fixture("auth_token.json")

        # Step 1: login
        responses.add(
            responses.POST,
            f"{API_BASE}/auth/login/",
            json=login_data,
            status=200,
        )
        # Step 2: authorize -> redirect with code
        responses.add(
            responses.GET,
            f"{API_BASE}/auth/o/authorize/",
            headers={"Location": "/auth/o/post-message/?code=test_auth_code"},
            status=302,
        )
        # Step 3: exchange code for token
        responses.add(
            responses.POST,
            f"{API_BASE}/auth/o/token/",
            json=token_data,
            status=200,
        )

        client = _make_client()
        token = client._authorize()
        assert isinstance(token, BeatportOAuthToken)
        assert token.access_token == "new_access_tok_abc123"

    @responses.activate
    def test_auth_login_failure(self):
        responses.add(
            responses.POST,
            f"{API_BASE}/auth/login/",
            json={"error": "Invalid credentials"},
            status=200,
        )

        client = _make_client()
        with pytest.raises(BeatportAPIError):
            client._authorize()

    @responses.activate
    def test_auth_invalid_request(self):
        login_data = load_fixture("auth_login.json")

        responses.add(
            responses.POST,
            f"{API_BASE}/auth/login/",
            json=login_data,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/auth/o/authorize/",
            body="<html><p>invalid_request: bad redirect_uri</p></html>",
            status=200,
        )

        client = _make_client()
        with pytest.raises(BeatportAPIError):
            client._authorize()


# ──────────────────────────────────────────────────────────────
# get_my_account
# ──────────────────────────────────────────────────────────────


class TestGetMyAccount:
    @responses.activate
    def test_returns_account(self):
        account_data = load_fixture("my_account.json")
        responses.add(
            responses.GET,
            f"{API_BASE}/my/account",
            json=account_data,
            status=200,
        )

        client = _make_client()
        acc = client.get_my_account()
        assert isinstance(acc, BeatportMyAccount)
        assert acc.username == "testuser"
        assert acc.email == "testuser@example.com"


# ──────────────────────────────────────────────────────────────
# search
# ──────────────────────────────────────────────────────────────


class TestSearch:
    @responses.activate
    def test_search_tracks(self):
        search_data = load_fixture("search_tracks.json")
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json=search_data,
            status=200,
        )

        client = _make_client()
        results = list(client.search("Synthwave Runner", model="tracks"))
        assert len(results) == 2
        assert all(isinstance(t, BeatportTrack) for t in results)
        assert results[0].name == "Midnight Circuit"
        assert results[1].name == "Digital Sunrise"

    @responses.activate
    def test_search_releases_without_details(self):
        search_data = load_fixture("search_releases.json")
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json=search_data,
            status=200,
        )

        client = _make_client()
        results = list(client.search("Neon Dreams", details=False))
        assert len(results) == 2
        assert all(isinstance(r, BeatportRelease) for r in results)

    @responses.activate
    def test_search_releases_with_details(self):
        """Search with details=True fetches full release for each result."""
        search_data = load_fixture("search_releases.json")
        release_detail = load_fixture("release_detail.json")
        release_tracks_data = load_fixture("release_tracks.json")
        track_3001 = load_fixture("track_detail_3001.json")
        track_3002 = load_fixture("track_detail_3002.json")

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/search",
            json=search_data,
            status=200,
        )
        # For each release in search results, get_release is called
        # Release 4001
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4001/",
            json=release_detail,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4001/tracks/",
            json=release_tracks_data,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_3001,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3002/",
            json=track_3002,
            status=200,
        )
        # Release 4002 - reuse same detail for simplicity
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4002/",
            json=release_detail,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4002/tracks/",
            json=release_tracks_data,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_3001,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3002/",
            json=track_3002,
            status=200,
        )

        client = _make_client()
        results = list(client.search("Neon Dreams"))
        assert len(results) == 2
        assert all(isinstance(r, BeatportRelease) for r in results)
        # Each release should have tracks populated
        assert len(results[0].tracks) == 2


# ──────────────────────────────────────────────────────────────
# get_release
# ──────────────────────────────────────────────────────────────


class TestGetRelease:
    @responses.activate
    def test_returns_release_with_tracks(self):
        release_detail = load_fixture("release_detail.json")
        release_tracks_data = load_fixture("release_tracks.json")
        track_3001 = load_fixture("track_detail_3001.json")
        track_3002 = load_fixture("track_detail_3002.json")

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4001/",
            json=release_detail,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4001/tracks/",
            json=release_tracks_data,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_3001,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3002/",
            json=track_3002,
            status=200,
        )

        client = _make_client()
        release = client.get_release(4001)
        assert isinstance(release, BeatportRelease)
        assert release.id == "4001"
        assert release.name == "Neon Dreams EP"
        assert len(release.tracks) == 2

    @responses.activate
    def test_returns_none_on_404(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/9999/",
            json={"detail": "Not found"},
            status=404,
        )

        client = _make_client()
        result = client.get_release(9999)
        assert result is None


# ──────────────────────────────────────────────────────────────
# get_track
# ──────────────────────────────────────────────────────────────


class TestGetTrack:
    @responses.activate
    def test_returns_track(self):
        track_data = load_fixture("track_detail_3001.json")
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_data,
            status=200,
        )

        client = _make_client()
        track = client.get_track(3001)
        assert isinstance(track, BeatportTrack)
        assert track.id == "3001"
        assert track.name == "Midnight Circuit"
        assert track.bpm == 126

    @responses.activate
    def test_returns_none_on_404(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/9999/",
            json={"detail": "Not found"},
            status=404,
        )

        client = _make_client()
        result = client.get_track(9999)
        assert result is None


# ──────────────────────────────────────────────────────────────
# get_image
# ──────────────────────────────────────────────────────────────


class TestGetImage:
    @responses.activate
    def test_fetches_image_without_dimensions(self):
        track_data = load_fixture("track_detail_3001.json")
        image_bytes = b"\x89PNG\r\n\x1a\nfake_image_data"

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_data,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://geo-media.beatport.com/image/neon-dreams.jpg",
            body=image_bytes,
            status=200,
        )

        client = _make_client()
        result = client.get_image(3001)
        assert result == image_bytes

    @responses.activate
    def test_fetches_image_with_dimensions(self):
        track_data = load_fixture("track_detail_3001.json")
        image_bytes = b"\x89PNG\r\n\x1a\nfake_image_500x500"

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_data,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://geo-media.beatport.com/image/neon-dreams/500x500.jpg",
            body=image_bytes,
            status=200,
        )

        client = _make_client()
        result = client.get_image(3001, width=500, height=500)
        assert result == image_bytes

    @responses.activate
    def test_returns_none_when_track_not_found(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/9999/",
            json={"detail": "Not found"},
            status=404,
        )

        client = _make_client()
        result = client.get_image(9999)
        assert result is None

    @responses.activate
    def test_zero_dimensions_treated_as_none(self):
        track_data = load_fixture("track_detail_3001.json")
        image_bytes = b"image_data"

        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/3001/",
            json=track_data,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://geo-media.beatport.com/image/neon-dreams.jpg",
            body=image_bytes,
            status=200,
        )

        client = _make_client()
        result = client.get_image(3001, width=0, height=0)
        assert result == image_bytes


# ──────────────────────────────────────────────────────────────
# Error handling
# ──────────────────────────────────────────────────────────────


class TestErrorHandling:
    @responses.activate
    def test_connection_error_raises_api_error(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/my/account",
            body=ConnectionError("connection refused"),
        )

        client = _make_client()
        with pytest.raises(BeatportAPIError, match="Error connecting"):
            client._get("/my/account")

    @responses.activate
    def test_500_raises_api_error(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/tracks/1/",
            json={"error": "internal"},
            status=500,
        )

        client = _make_client()
        with pytest.raises(BeatportAPIError):
            client._get("/catalog/tracks/1/")

    @responses.activate
    def test_get_release_tracks_error_returns_empty(self):
        responses.add(
            responses.GET,
            f"{API_BASE}/catalog/releases/4001/tracks/",
            json={"error": "internal"},
            status=500,
        )

        client = _make_client()
        result = client.get_release_tracks(4001)
        assert result == []


# ──────────────────────────────────────────────────────────────
# Client __init__ with valid token
# ──────────────────────────────────────────────────────────────


class TestClientInit:
    @responses.activate
    def test_init_with_valid_token(self):
        account_data = load_fixture("my_account.json")
        responses.add(
            responses.GET,
            f"{API_BASE}/my/account",
            json=account_data,
            status=200,
        )

        token = _make_token()
        client = Beatport4Client(
            log=MagicMock(),
            client_id="test_id",
            beatport_token=token,
        )
        assert client.beatport_token is token

    def test_init_no_credentials_raises(self):
        with pytest.raises(BeatportAPIError, match="Neither"):
            Beatport4Client(log=MagicMock())

    @responses.activate
    def test_init_expired_token_reauthorizes(self):
        """When token is expired, client should authorize with username/password."""
        login_data = load_fixture("auth_login.json")
        token_data = load_fixture("auth_token.json")

        responses.add(
            responses.POST,
            f"{API_BASE}/auth/login/",
            json=login_data,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/auth/o/authorize/",
            headers={"Location": "/auth/o/post-message/?code=test_code"},
            status=302,
        )
        responses.add(
            responses.POST,
            f"{API_BASE}/auth/o/token/",
            json=token_data,
            status=200,
        )

        expired_token = _make_token(expired=True)
        client = Beatport4Client(
            log=MagicMock(),
            client_id="test_id",
            username="testuser",
            password="testpass",
            beatport_token=expired_token,
        )
        # Should have gotten a new token
        assert client.beatport_token.access_token == "new_access_tok_abc123"
