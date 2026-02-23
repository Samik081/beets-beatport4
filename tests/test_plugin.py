"""Tests for Beatport4Plugin methods with mocked client."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from beets.autotag.hooks import AlbumInfo, TrackInfo

from beetsplug.beatport4 import (
    BeatportAPIError,
    BeatportArtist,
    BeatportLabel,
    BeatportRelease,
    BeatportTrack,
)
from tests.conftest import make_token

_UNSET = object()


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
    publish_date=_UNSET,
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
        publish_date=datetime(2024, 6, 15)
        if publish_date is _UNSET
        else publish_date,
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


# ──────────────────────────────────────────────────────────────
# _get_album_info null fields
# ──────────────────────────────────────────────────────────────


class TestGetAlbumInfoNullFields:
    def test_missing_publish_date(self, plugin):
        release = _make_bp_release(publish_date=None)
        info = plugin._get_album_info(release)
        assert info.year is None
        assert info.month is None
        assert info.day is None

    def test_missing_label(self, plugin):
        release = _make_bp_release()
        release.label = None
        info = plugin._get_album_info(release)
        assert info.label is None

    def test_missing_both(self, plugin):
        release = _make_bp_release()
        release.publish_date = None
        release.label = None
        info = plugin._get_album_info(release)
        assert info.year is None
        assert info.month is None
        assert info.day is None
        assert info.label is None


# ──────────────────────────────────────────────────────────────
# candidates query sanitization
# ──────────────────────────────────────────────────────────────


class TestCandidatesQuerySanitization:
    def test_special_chars_stripped(self, plugin_with_client, mock_client):
        mock_client.search.return_value = iter([])
        plugin_with_client.candidates([], "Art!st", "Album", False)
        call_args = mock_client.search.call_args
        query = call_args[0][0]
        assert "!" not in query

    def test_medium_info_stripped(self, plugin_with_client, mock_client):
        mock_client.search.return_value = iter([])
        plugin_with_client.candidates([], "Artist", "Album CD1", False)
        call_args = mock_client.search.call_args
        query = call_args[0][0]
        assert "CD1" not in query


# ──────────────────────────────────────────────────────────────
# client is None guards
# ──────────────────────────────────────────────────────────────


class TestClientNoneGuards:
    def test_candidates_returns_empty_when_no_client(self, plugin):
        assert plugin.client is None
        result = plugin.candidates([], "Artist", "Album", False)
        assert result == []

    def test_item_candidates_returns_empty_when_no_client(self, plugin):
        assert plugin.client is None
        result = plugin.item_candidates(None, "Artist", "Title")
        assert result == []

    def test_album_for_id_returns_none_when_no_client(self, plugin):
        assert plugin.client is None
        result = plugin.album_for_id("12345")
        assert result is None

    def test_track_for_id_returns_none_when_no_client(self, plugin):
        assert plugin.client is None
        result = plugin.track_for_id("300")
        assert result is None


# ──────────────────────────────────────────────────────────────
# setup()
# ──────────────────────────────────────────────────────────────


class TestPluginSetup:
    def test_setup_with_valid_token_file(self, plugin, tmp_path):
        token = make_token()
        token_path = tmp_path / "token.json"
        token_path.write_text(json.dumps(token.encode()))
        plugin.config["tokenfile"].set(str(token_path))

        mock_client = MagicMock()
        mock_client.beatport_token = token
        with patch(
            "beetsplug.beatport4.plugin.Beatport4Client",
            return_value=mock_client,
        ) as cls:
            plugin.setup()
            cls.assert_called_once()
            assert plugin.client is mock_client

    def test_setup_with_missing_token_file(self, plugin, tmp_path):
        token_path = tmp_path / "nonexistent.json"
        plugin.config["tokenfile"].set(str(token_path))
        plugin.config["username"].set("user")
        plugin.config["password"].set("pass")

        token = make_token()
        mock_client = MagicMock()
        mock_client.beatport_token = token
        with patch(
            "beetsplug.beatport4.plugin.Beatport4Client",
            return_value=mock_client,
        ):
            plugin.setup()
            assert plugin.client is mock_client

    def test_setup_with_corrupt_token_file(self, plugin, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{bad json")
        plugin.config["tokenfile"].set(str(token_path))
        plugin.config["username"].set("user")
        plugin.config["password"].set("pass")

        token = make_token()
        mock_client = MagicMock()
        mock_client.beatport_token = token
        with patch(
            "beetsplug.beatport4.plugin.Beatport4Client",
            return_value=mock_client,
        ):
            plugin.setup()
            assert plugin.client is mock_client

    def test_setup_token_file_read_oserror(self, plugin, tmp_path):
        token_path = tmp_path / "token.json"
        plugin.config["tokenfile"].set(str(token_path))
        plugin.config["username"].set("user")
        plugin.config["password"].set("pass")

        token = make_token()
        mock_client = MagicMock()
        mock_client.beatport_token = token
        with (
            patch("builtins.open", side_effect=OSError("disk err")),
            patch(
                "beetsplug.beatport4.plugin.Beatport4Client",
                return_value=mock_client,
            ),
        ):
            plugin.setup()
            assert plugin.client is mock_client

    def test_setup_auth_failure_prompts_manual_token(self, plugin, tmp_path):
        token_path = tmp_path / "nonexistent.json"
        plugin.config["tokenfile"].set(str(token_path))

        token = make_token()
        mock_client = MagicMock()
        mock_client.beatport_token = token

        # First call raises, second call (manual token) succeeds
        with (
            patch(
                "beetsplug.beatport4.plugin.Beatport4Client",
                side_effect=[
                    BeatportAPIError("auth failed"),
                    mock_client,
                ],
            ),
            patch("beets.ui.print_"),
            patch(
                "beets.ui.input_",
                return_value=json.dumps(token.encode()),
            ),
        ):
            plugin.setup()
            assert plugin.client is mock_client

    def test_setup_auth_and_manual_both_fail_leaves_client_none(
        self, plugin, tmp_path
    ):
        token_path = tmp_path / "nonexistent.json"
        plugin.config["tokenfile"].set(str(token_path))

        with (
            patch(
                "beetsplug.beatport4.plugin.Beatport4Client",
                side_effect=BeatportAPIError("auth failed"),
            ),
            patch("beets.ui.print_"),
            patch(
                "beets.ui.input_",
                return_value="not valid json",
            ),
        ):
            plugin.setup()
            assert plugin.client is None

    def test_setup_writes_token_to_file(self, plugin, tmp_path):
        token_path = tmp_path / "token.json"
        plugin.config["tokenfile"].set(str(token_path))

        token = make_token()
        mock_client = MagicMock()
        mock_client.beatport_token = token
        with patch(
            "beetsplug.beatport4.plugin.Beatport4Client",
            return_value=mock_client,
        ):
            plugin.setup()
            written = json.loads(token_path.read_text())
            assert written["access_token"] == token.access_token

    def test_setup_token_write_oserror_does_not_crash(self, plugin, tmp_path):
        # Use a directory path so open(path, "w") raises OSError
        token_path = tmp_path / "no_such_dir" / "token.json"
        plugin.config["tokenfile"].set(str(token_path))

        token = make_token()
        mock_client = MagicMock()
        mock_client.beatport_token = token
        with patch(
            "beetsplug.beatport4.plugin.Beatport4Client",
            return_value=mock_client,
        ):
            plugin.setup()
            # Client is still set despite write failure
            assert plugin.client is mock_client


# ──────────────────────────────────────────────────────────────
# import_task_files()
# ──────────────────────────────────────────────────────────────


def _make_mock_task(data_source="Beatport", track_ids=None):
    """Create a mock import task with the given data source."""
    task = MagicMock()
    task.match.info.data_source = data_source
    items = []
    for tid in track_ids or ["123"]:
        item = MagicMock()
        item.get.return_value = tid
        items.append(item)
    task.imported_items.return_value = items
    return task


class TestImportTaskFiles:
    def test_skips_when_client_is_none(self, plugin):
        assert plugin.client is None
        task = _make_mock_task()
        plugin.import_task_files(task)
        # Should warn and return without calling get_image
        task.imported_items.assert_not_called()

    def test_skips_when_match_is_none(
        self, plugin_with_client, mock_client
    ):
        """Regression: 'as-is' imports set task.match = None."""
        plugin_with_client.config["art"].set(True)
        task = MagicMock()
        task.match = None
        plugin_with_client.import_task_files(task)
        mock_client.get_image.assert_not_called()

    def test_skips_when_art_disabled(self, plugin_with_client, mock_client):
        plugin_with_client.config["art"].set(False)
        task = _make_mock_task()
        plugin_with_client.import_task_files(task)
        mock_client.get_image.assert_not_called()

    def test_skips_when_data_source_mismatch(
        self, plugin_with_client, mock_client
    ):
        plugin_with_client.config["art"].set(True)
        task = _make_mock_task(data_source="MusicBrainz")
        plugin_with_client.import_task_files(task)
        mock_client.get_image.assert_not_called()

    def test_skips_when_art_exists_and_no_overwrite(
        self, plugin_with_client, mock_client
    ):
        plugin_with_client.config["art"].set(True)
        plugin_with_client.config["art_overwrite"].set(False)
        task = _make_mock_task()
        mock_client.get_image.return_value = b"\x89PNG fake"
        with patch("beetsplug.beatport4.plugin.art") as mock_art:
            mock_art.get_art.return_value = b"existing art"
            plugin_with_client.import_task_files(task)
            # Image is fetched once for the release
            mock_client.get_image.assert_called_once()
            # But embedding is skipped because art already exists
            mock_art.embed_item.assert_not_called()

    def test_embeds_art_successfully(self, plugin_with_client, mock_client):
        plugin_with_client.config["art"].set(True)
        plugin_with_client.config["art_overwrite"].set(True)
        task = _make_mock_task(track_ids=["123"])
        mock_client.get_image.return_value = b"\x89PNG fake"

        with patch("beetsplug.beatport4.plugin.art") as mock_art:
            plugin_with_client.import_task_files(task)
            mock_client.get_image.assert_called_once()
            mock_art.embed_item.assert_called_once()

    def test_returns_early_on_none_image_data(
        self, plugin_with_client, mock_client
    ):
        """Image fetched once per release; None → early return."""
        plugin_with_client.config["art"].set(True)
        plugin_with_client.config["art_overwrite"].set(True)
        task = _make_mock_task(track_ids=["111", "222"])
        mock_client.get_image.return_value = None

        with patch("beetsplug.beatport4.plugin.art") as mock_art:
            plugin_with_client.import_task_files(task)
            # get_image called once (for the first track)
            mock_client.get_image.assert_called_once()
            # No embedding attempted
            mock_art.embed_item.assert_not_called()

    def test_handles_get_image_api_error(self, plugin_with_client, mock_client):
        plugin_with_client.config["art"].set(True)
        plugin_with_client.config["art_overwrite"].set(True)
        task = _make_mock_task()
        mock_client.get_image.side_effect = BeatportAPIError("img fail")

        with patch("beetsplug.beatport4.plugin.art"):
            plugin_with_client.import_task_files(task)
            # Should not crash; warning logged

    def test_handles_oserror(self, plugin_with_client, mock_client):
        plugin_with_client.config["art"].set(True)
        plugin_with_client.config["art_overwrite"].set(True)
        task = _make_mock_task()
        mock_client.get_image.return_value = b"\x89PNG"

        with (
            patch("beetsplug.beatport4.plugin.art"),
            patch(
                "tempfile.NamedTemporaryFile",
                side_effect=OSError("disk full"),
            ),
        ):
            plugin_with_client.import_task_files(task)
            # Should not crash; warning logged
