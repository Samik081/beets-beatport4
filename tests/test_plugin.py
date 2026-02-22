"""Tests for Beatport4Plugin methods with mocked client."""

from datetime import datetime, timedelta

from beets.autotag.hooks import AlbumInfo, TrackInfo

from beetsplug.beatport4 import (
    BeatportAPIError,
    BeatportArtist,
    BeatportLabel,
    BeatportRelease,
    BeatportTrack,
)


def _make_bp_artist(id_, name):
    return BeatportArtist(id=str(id_), name=name)


def _make_bp_label(id_, name):
    return BeatportLabel(id=str(id_), name=name)


def _make_bp_track(
    id_=300,
    name="Test Track",
    mix_name="Original Mix",
    artists=None,
    length_seconds=360,
    number=1,
    bpm=128,
    initial_key="D#maj",
    genre="Tech House",
    url="https://beatport.com/track/test-track/300",
):
    return BeatportTrack(
        id=str(id_),
        name=name,
        mix_name=mix_name,
        artists=artists or [_make_bp_artist(100, "Test Artist")],
        length=timedelta(seconds=length_seconds),
        number=number,
        bpm=bpm,
        initial_key=initial_key,
        genre=genre,
        url=url,
    )


def _make_bp_release(
    id_=400,
    name="Test Release",
    artists=None,
    tracks=None,
    label=None,
    catalog_number="TL001",
    type_="Album",
    publish_date=None,
    url="https://beatport.com/release/test-release/400",
):
    return BeatportRelease(
        id=str(id_),
        name=name,
        artists=artists or [_make_bp_artist(100, "Test Artist")],
        tracks=tracks if tracks is not None else [_make_bp_track()],
        label=label or _make_bp_label(200, "Test Label"),
        catalog_number=catalog_number,
        type=type_,
        publish_date=publish_date or datetime(2024, 6, 15),
        url=url,
    )


# ──────────────────────────────────────────────────────────────
# _get_track_info
# ──────────────────────────────────────────────────────────────


class TestGetTrackInfo:
    def test_original_mix_title_unchanged(self, plugin):
        track = _make_bp_track(mix_name="Original Mix")
        info = plugin._get_track_info(track)
        assert info.title == "Test Track"

    def test_non_original_mix_appended(self, plugin):
        track = _make_bp_track(mix_name="Dub Mix")
        info = plugin._get_track_info(track)
        assert info.title == "Test Track (Dub Mix)"

    def test_all_track_info_fields(self, plugin):
        track = _make_bp_track()
        info = plugin._get_track_info(track)
        assert isinstance(info, TrackInfo)
        assert info.track_id == "300"
        assert info.artist == "Test Artist"
        assert info.artist_id == "100"
        assert info.length == 360.0
        assert info.index == 1
        assert info.medium_index == 1
        assert info.data_source == "Beatport"
        assert info.bpm == 128
        assert info.initial_key == "D#maj"
        assert info.genre == "Tech House"
        assert info.data_url is not None

    def test_multiple_artists_joined(self, plugin):
        artists = [
            _make_bp_artist(1, "Alice"),
            _make_bp_artist(2, "Bob"),
        ]
        track = _make_bp_track(artists=artists)
        info = plugin._get_track_info(track)
        assert "Alice" in info.artist
        assert "Bob" in info.artist


# ──────────────────────────────────────────────────────────────
# _get_album_info
# ──────────────────────────────────────────────────────────────


class TestGetAlbumInfo:
    def test_all_album_info_fields(self, plugin):
        release = _make_bp_release()
        info = plugin._get_album_info(release)
        assert isinstance(info, AlbumInfo)
        assert info.album == "Test Release"
        assert info.album_id == "400"
        assert info.artist == "Test Artist"
        assert info.artist_id == "100"
        assert info.albumtype == "Album"
        assert info.year == 2024
        assert info.month == 6
        assert info.day == 15
        assert info.label == "Test Label"
        assert info.catalognum == "TL001"
        assert info.media == "Digital"
        assert info.data_source == "Beatport"
        assert info.va is False
        assert len(info.tracks) == 1

    def test_va_detection(self, plugin):
        artists = [_make_bp_artist(i, f"A{i}") for i in range(5)]
        release = _make_bp_release(artists=artists)
        info = plugin._get_album_info(release)
        assert info.va is True
        assert info.artist == "Various Artists"


# ──────────────────────────────────────────────────────────────
# album_for_id
# ──────────────────────────────────────────────────────────────


class TestAlbumForId:
    def test_valid_numeric_id(self, plugin_with_client, mock_client):
        mock_client.get_release.return_value = _make_bp_release()
        result = plugin_with_client.album_for_id("12345")
        assert isinstance(result, AlbumInfo)
        mock_client.get_release.assert_called_once_with("12345")

    def test_valid_url(self, plugin_with_client, mock_client):
        mock_client.get_release.return_value = _make_bp_release()
        url = "https://beatport.com/release/test-release/67890"
        result = plugin_with_client.album_for_id(url)
        assert isinstance(result, AlbumInfo)
        mock_client.get_release.assert_called_once_with("67890")

    def test_invalid_id_returns_none(self, plugin_with_client):
        result = plugin_with_client.album_for_id("not-a-valid-id")
        assert result is None

    def test_empty_id_returns_none(self, plugin_with_client):
        result = plugin_with_client.album_for_id("")
        assert result is None

    def test_not_found_returns_none(self, plugin_with_client, mock_client):
        mock_client.get_release.return_value = None
        result = plugin_with_client.album_for_id("99999")
        assert result is None


# ──────────────────────────────────────────────────────────────
# track_for_id
# ──────────────────────────────────────────────────────────────


class TestTrackForId:
    def test_valid_numeric_id(self, plugin_with_client, mock_client):
        mock_client.get_track.return_value = _make_bp_track()
        result = plugin_with_client.track_for_id("300")
        assert isinstance(result, TrackInfo)
        mock_client.get_track.assert_called_once_with("300")

    def test_valid_url(self, plugin_with_client, mock_client):
        mock_client.get_track.return_value = _make_bp_track()
        url = "https://beatport.com/track/test-track/300"
        result = plugin_with_client.track_for_id(url)
        assert isinstance(result, TrackInfo)
        mock_client.get_track.assert_called_once_with("300")

    def test_invalid_id_returns_none(self, plugin_with_client):
        result = plugin_with_client.track_for_id("not-valid")
        assert result is None

    def test_not_found_returns_none(self, plugin_with_client, mock_client):
        mock_client.get_track.return_value = None
        result = plugin_with_client.track_for_id("99999")
        assert result is None


# ──────────────────────────────────────────────────────────────
# candidates
# ──────────────────────────────────────────────────────────────


class TestCandidates:
    def test_returns_album_info_list(self, plugin_with_client, mock_client):
        mock_client.search.return_value = iter([_make_bp_release()])
        result = plugin_with_client.candidates([], "Artist", "Album", False)
        assert len(result) == 1
        assert isinstance(result[0], AlbumInfo)

    def test_va_query_omits_artist(self, plugin_with_client, mock_client):
        mock_client.search.return_value = iter([])
        plugin_with_client.candidates([], "Artist", "Album", True)
        call_args = mock_client.search.call_args
        query = call_args[0][0]
        assert "Artist" not in query
        assert "Album" in query

    def test_api_error_returns_empty(self, plugin_with_client, mock_client):
        mock_client.search.side_effect = BeatportAPIError("fail")
        result = plugin_with_client.candidates([], "Artist", "Album", False)
        assert result == []


# ──────────────────────────────────────────────────────────────
# item_candidates
# ──────────────────────────────────────────────────────────────


class TestItemCandidates:
    def test_returns_track_info_list(self, plugin_with_client, mock_client):
        mock_client.search.return_value = iter([_make_bp_track()])
        result = plugin_with_client.item_candidates(None, "Artist", "Title")
        assert len(result) == 1
        assert isinstance(result[0], TrackInfo)

    def test_api_error_returns_empty(self, plugin_with_client, mock_client):
        mock_client.search.side_effect = BeatportAPIError("fail")
        result = plugin_with_client.item_candidates(None, "Artist", "Title")
        assert result == []
