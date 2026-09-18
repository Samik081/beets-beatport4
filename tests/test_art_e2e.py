"""End-to-end tests for the art handling (``art`` / ``art_mode`` /
``art_overwrite``) against a real beets library and real audio files.

Only ``Beatport4Client.get_image`` is mocked; embedding goes through
``beetsplug._utils.art`` and mediafile, saving goes through
``Album.set_art()``, and results are checked on disk and in the database.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import beets
import pytest
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.library import Item, Library
from beetsplug._utils import art

JPEG = b"\xff\xd8\xff\xe0 beatport jpeg"
PNG = b"\x89PNG\r\n\x1a\n beatport png"
LOCAL = b"\xff\xd8\xff\xe0 local cover"
OLD_EMBEDDED = b"\xff\xd8\xff\xe0 old embedded"

# MPEG-1 Layer III, 128 kbps, 44.1 kHz, no padding: 417-byte frames.
# Ten silent frames are enough for mutagen to parse and write tags.
_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _write_mp3(path: Path) -> Path:
    path.write_bytes(_MP3_FRAME * 10)
    return path


def _embedded_art(item: Item) -> bytes | None:
    return art.get_art(MagicMock(), item)


@pytest.fixture
def lib(tmp_path):
    return Library(":memory:", directory=str(tmp_path / "lib"))


@pytest.fixture
def art_plugin(plugin_with_client, mock_client):
    plugin_with_client.config["art"].set(True)
    mock_client.get_image.return_value = JPEG
    return plugin_with_client


@pytest.fixture
def album(lib, tmp_path):
    """A two-track album that already lives at its final location."""
    album_dir = tmp_path / "lib" / "Artist" / "Album"
    album_dir.mkdir(parents=True)
    items = [
        Item(path=bytes(_write_mp3(album_dir / f"0{n}.mp3")), track=n)
        for n in (1, 2)
    ]
    return lib.add_album(items)


def _album_task(album):
    task = MagicMock()
    task.is_album = True
    task.album = album
    task.match.info = AlbumInfo(
        album="Album",
        album_id="1000",
        artist="Artist",
        artist_id="2000",
        tracks=[TrackInfo(track_id=str(i.id)) for i in album.items()],
        data_source="Beatport",
    )
    task.imported_items.return_value = list(album.items())
    return task


@pytest.fixture
def singleton(lib, tmp_path):
    single_dir = tmp_path / "lib" / "Artist" / "Single"
    single_dir.mkdir(parents=True)
    item = Item(path=bytes(_write_mp3(single_dir / "single.mp3")))
    lib.add(item)
    return item


def _singleton_task(item):
    task = MagicMock()
    task.is_album = False
    task.album = None
    task.match.info = TrackInfo(track_id="456", data_source="Beatport")
    task.imported_items.return_value = [item]
    return task


def _album_dir(album) -> Path:
    return Path(os.fsdecode(album.item_dir()))


def _cover(album, name="cover.jpg") -> Path:
    return _album_dir(album) / name


def _set_local_cover(album, tmp_path) -> Path:
    """Give the album a cover file, the way fetchart would have."""
    src = tmp_path / "local.jpg"
    src.write_bytes(LOCAL)
    album.set_art(str(src))
    album.store()
    cover = _cover(album)
    assert cover.read_bytes() == LOCAL
    return cover


def _stored_artpath(lib, album):
    return lib.get_album(album.id).artpath


class TestEmbedMode:
    def test_embeds_into_every_track(self, art_plugin, lib, album):
        art_plugin.import_task_files(_album_task(album))

        assert [_embedded_art(i) for i in album.items()] == [JPEG, JPEG]
        assert not _cover(album).exists()
        assert _stored_artpath(lib, album) is None

    def test_keeps_existing_embedded_art_without_overwrite(
        self, art_plugin, album
    ):
        first, second = album.items()
        art.embed_item(MagicMock(), first, _write_image(album, OLD_EMBEDDED))

        art_plugin.import_task_files(_album_task(album))

        assert _embedded_art(first) == OLD_EMBEDDED
        assert _embedded_art(second) == JPEG

    def test_replaces_existing_embedded_art_with_overwrite(
        self, art_plugin, album
    ):
        art_plugin.config["art_overwrite"].set(True)
        first, _ = album.items()
        art.embed_item(MagicMock(), first, _write_image(album, OLD_EMBEDDED))

        art_plugin.import_task_files(_album_task(album))

        assert [_embedded_art(i) for i in album.items()] == [JPEG, JPEG]

    def test_fetches_image_once_per_album(self, art_plugin, mock_client, album):
        art_plugin.import_task_files(_album_task(album))

        mock_client.get_image.assert_called_once()

    def test_singleton_is_embedded(self, art_plugin, singleton):
        art_plugin.import_task_files(_singleton_task(singleton))

        assert _embedded_art(singleton) == JPEG


class TestFileMode:
    @pytest.fixture(autouse=True)
    def _file_mode(self, art_plugin):
        art_plugin.config["art_mode"].set("file")

    def test_saves_cover_and_registers_it(self, art_plugin, lib, album):
        art_plugin.import_task_files(_album_task(album))

        assert _cover(album).read_bytes() == JPEG
        assert _stored_artpath(lib, album) == bytes(_cover(album))

    def test_leaves_audio_files_untouched(self, art_plugin, album):
        before = [Path(os.fsdecode(i.path)).read_bytes() for i in album.items()]

        art_plugin.import_task_files(_album_task(album))

        after = [Path(os.fsdecode(i.path)).read_bytes() for i in album.items()]
        assert after == before
        assert all(_embedded_art(i) is None for i in album.items())

    def test_png_image_gets_png_extension(self, art_plugin, mock_client, album):
        mock_client.get_image.return_value = PNG

        art_plugin.import_task_files(_album_task(album))

        assert _cover(album, "cover.png").read_bytes() == PNG
        assert not _cover(album, "cover.jpg").exists()

    def test_respects_art_filename_config(self, art_plugin, album):
        beets.config["art_filename"] = "folder"

        art_plugin.import_task_files(_album_task(album))

        assert _cover(album, "folder.jpg").read_bytes() == JPEG
        assert not _cover(album, "cover.jpg").exists()

    def test_keeps_existing_cover_without_downloading(
        self, art_plugin, mock_client, lib, album, tmp_path
    ):
        """The fetchart-fallback case: a local cover is already in place."""
        cover = _set_local_cover(album, tmp_path)

        art_plugin.import_task_files(_album_task(album))

        assert cover.read_bytes() == LOCAL
        assert _stored_artpath(lib, album) == bytes(cover)
        mock_client.get_image.assert_not_called()

    def test_replaces_existing_cover_with_overwrite(
        self, art_plugin, lib, album, tmp_path
    ):
        art_plugin.config["art_overwrite"].set(True)
        cover = _set_local_cover(album, tmp_path)

        art_plugin.import_task_files(_album_task(album))

        assert cover.read_bytes() == JPEG
        assert _stored_artpath(lib, album) == bytes(cover)
        assert sorted(p.name for p in _album_dir(album).iterdir()) == [
            "01.mp3",
            "02.mp3",
            "cover.jpg",
        ]

    def test_replaces_stale_artpath(self, art_plugin, lib, album, tmp_path):
        """artpath pointing at a deleted file does not count as a cover."""
        cover = _set_local_cover(album, tmp_path)
        cover.unlink()

        art_plugin.import_task_files(_album_task(album))

        assert cover.read_bytes() == JPEG
        assert _stored_artpath(lib, album) == bytes(cover)

    def test_singleton_does_nothing(self, art_plugin, mock_client, singleton):
        single_dir = Path(os.fsdecode(singleton.path)).parent

        art_plugin.import_task_files(_singleton_task(singleton))

        mock_client.get_image.assert_not_called()
        assert _embedded_art(singleton) is None
        assert [p.name for p in single_dir.iterdir()] == ["single.mp3"]

    def test_unwritable_album_dir_is_logged_not_raised(
        self, art_plugin, lib, album
    ):
        """set_art() failures surface as beets FilesystemError, which must
        not escape the event handler and abort the import."""
        album_dir = _album_dir(album)
        album_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            art_plugin.import_task_files(_album_task(album))
        finally:
            album_dir.chmod(stat.S_IRWXU)

        assert not _cover(album).exists()
        assert _stored_artpath(lib, album) is None


class TestBothMode:
    @pytest.fixture(autouse=True)
    def _both_mode(self, art_plugin):
        art_plugin.config["art_mode"].set("both")

    def test_saves_cover_and_embeds(self, art_plugin, lib, album):
        art_plugin.import_task_files(_album_task(album))

        assert _cover(album).read_bytes() == JPEG
        assert _stored_artpath(lib, album) == bytes(_cover(album))
        assert [_embedded_art(i) for i in album.items()] == [JPEG, JPEG]

    def test_keeps_existing_cover_but_still_embeds(
        self, art_plugin, mock_client, album, tmp_path
    ):
        cover = _set_local_cover(album, tmp_path)

        art_plugin.import_task_files(_album_task(album))

        assert cover.read_bytes() == LOCAL
        assert [_embedded_art(i) for i in album.items()] == [JPEG, JPEG]
        mock_client.get_image.assert_called_once()

    def test_overwrite_replaces_cover_and_embedded_art(
        self, art_plugin, album, tmp_path
    ):
        art_plugin.config["art_overwrite"].set(True)
        cover = _set_local_cover(album, tmp_path)
        first, _ = album.items()
        art.embed_item(MagicMock(), first, _write_image(album, OLD_EMBEDDED))

        art_plugin.import_task_files(_album_task(album))

        assert cover.read_bytes() == JPEG
        assert [_embedded_art(i) for i in album.items()] == [JPEG, JPEG]

    def test_singleton_only_embeds(self, art_plugin, singleton):
        single_dir = Path(os.fsdecode(singleton.path)).parent

        art_plugin.import_task_files(_singleton_task(singleton))

        assert _embedded_art(singleton) == JPEG
        assert [p.name for p in single_dir.iterdir()] == ["single.mp3"]

    def test_still_embeds_when_cover_cannot_be_saved(self, art_plugin, album):
        album_dir = _album_dir(album)
        album_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            art_plugin.import_task_files(_album_task(album))
        finally:
            album_dir.chmod(stat.S_IRWXU)

        assert not _cover(album).exists()
        assert [_embedded_art(i) for i in album.items()] == [JPEG, JPEG]


class TestTempFile:
    @pytest.fixture(autouse=True)
    def _own_tempdir(self, tmp_path, monkeypatch):
        self.tempdir = tmp_path / "tempdir"
        self.tempdir.mkdir()
        monkeypatch.setattr("tempfile.tempdir", str(self.tempdir))

    @pytest.mark.parametrize("mode", ["embed", "file", "both"])
    def test_temp_image_is_removed(self, art_plugin, album, mode):
        art_plugin.config["art_mode"].set(mode)

        art_plugin.import_task_files(_album_task(album))

        assert list(self.tempdir.iterdir()) == []

    def test_temp_image_is_removed_when_saving_fails(self, art_plugin, album):
        art_plugin.config["art_mode"].set("file")
        album_dir = _album_dir(album)
        album_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            art_plugin.import_task_files(_album_task(album))
        finally:
            album_dir.chmod(stat.S_IRWXU)

        assert list(self.tempdir.iterdir()) == []


def _write_image(album, data: bytes) -> str:
    """Write an image outside the album directory and return its path."""
    path = _album_dir(album).parent / "src_image.jpg"
    path.write_bytes(data)
    return str(path)
