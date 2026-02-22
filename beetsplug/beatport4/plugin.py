"""Beets plugin for Beatport API v4 integration."""

from __future__ import annotations

import json
import os
import tempfile
from json import JSONDecodeError
from typing import TYPE_CHECKING

import beets
import beets.ui
import confuse  # type: ignore[import-untyped]
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.metadata_plugins import MetadataSourcePlugin
from beets.util import cached_classproperty

from beetsplug._utils import art
from beetsplug.beatport4.client import Beatport4Client
from beetsplug.beatport4.constants import (
    MEDIA_TYPE,
    MEDIUM_INFO_PATTERN,
    NON_WORD_PATTERN,
    ORIGINAL_MIX_NAME,
    RELEASE_ID_PATTERN,
    TRACK_ID_PATTERN,
    VA_ARTIST_NAME,
    VA_ARTIST_THRESHOLD,
)
from beetsplug.beatport4.exceptions import BeatportAPIError
from beetsplug.beatport4.models import BeatportOAuthToken

if TYPE_CHECKING:
    from collections.abc import Sequence

    from beets.library import Item

    from beetsplug.beatport4.models import BeatportRelease, BeatportTrack


class Beatport4Plugin(MetadataSourcePlugin):
    @cached_classproperty
    def data_source(cls) -> str:
        return "Beatport"

    def __init__(self) -> None:
        super().__init__(name="beatport4")
        self.config.add(
            {
                "tokenfile": "beatport_token.json",
                "data_source_mismatch_penalty": 0.5,
                "username": None,
                "password": None,
                "client_id": None,
                "art": False,
                "art_overwrite": False,
                "art_width": None,
                "art_height": None,
                "singletons_with_album_metadata": {
                    "enabled": False,
                    "year": True,
                    "album": True,
                    "label": True,
                    "catalognum": True,
                    "albumartist": True,
                    "track_number": True,
                },
            }
        )
        self.client: Beatport4Client | None = None
        self.register_listener("import_begin", self.setup)
        self.register_listener("import_task_files", self.import_task_files)

    def setup(self) -> None:
        """Loads access token from the file, initializes the client
        and writes the token to the file if new one is fetched during
        client authorization
        """
        beatport_token = None
        # Get the OAuth token from a file
        try:
            with open(self._tokenfile()) as f:
                beatport_token = BeatportOAuthToken.from_api_response(
                    json.load(f)
                )
        except FileNotFoundError:
            self._log.debug(
                "Token file not found at {}; will authenticate",
                self._tokenfile(),
            )
        except OSError as e:
            self._log.warning(
                "Could not read token file at {}: {}",
                self._tokenfile(),
                e,
            )
        except (JSONDecodeError, KeyError, AttributeError):
            self._log.warning(
                "Corrupt token file at {}; re-authenticating",
                self._tokenfile(),
            )

        try:
            self.client = Beatport4Client(
                log=self._log,
                client_id=self.config["client_id"].get(),
                username=self.config["username"].get(),
                password=self.config["password"].get(),
                beatport_token=beatport_token,
            )
        except BeatportAPIError as e:
            # Invalid client_id, username/password or other problems
            beets.ui.print_(str(e))

            # Retry manually
            try:
                token = self._prompt_for_token()
                self.client = Beatport4Client(
                    log=self._log,
                    client_id=None,
                    username=None,
                    password=None,
                    beatport_token=token,
                )
            except (
                BeatportAPIError,
                JSONDecodeError,
                KeyError,
                ValueError,
            ) as exc:
                self._log.warning("Manual token entry failed: {}", exc)
                return

        try:
            with open(self._tokenfile(), "w") as f:
                json.dump(self.client.beatport_token.encode(), f)
        except OSError as e:
            self._log.warning(
                "Could not write token file at {}: {}",
                self._tokenfile(),
                e,
            )

    def import_task_files(self, task: object) -> None:
        """Embed album art from Beatport after a track has been written.

        Skips art embedding when: the Beatport client is not initialized,
        the ``art`` config option is disabled, the matched data source is
        not Beatport, or ``art_overwrite`` is disabled and the file already
        contains artwork.

        :param task: import_task_files event parameter
        """
        if self.client is None:
            self._log.warning(
                "Beatport client not initialized; skipping art embedding"
            )
            return
        try:
            if self.config["art"].get():
                if task.match.info.data_source != self.data_source:
                    return

                if not self.config["art_overwrite"].get() and art.get_art(
                    self._log, task.item
                ):
                    self._log.debug(
                        "File already contains an art, skipping fetching new"
                    )
                    return

                for track in task.imported_items():
                    track_id = track.get("mb_trackid")
                    image_data = self.client.get_image(
                        track_id,
                        self.config["art_width"].get(),
                        self.config["art_height"].get(),
                    )
                    if image_data is None:
                        return

                    tmp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(
                            delete=False
                        ) as temp_image:
                            tmp_path = temp_image.name
                            temp_image.write(image_data)
                        art.embed_item(self._log, task.item, tmp_path)
                    finally:
                        if tmp_path:
                            os.remove(tmp_path)
        except (OSError, BeatportAPIError) as e:
            self._log.warning("Failed to embed image: {}", e)

    def _prompt_for_token(self) -> BeatportOAuthToken:
        """Prompt user to paste OAuth token.
        Returns parsed BeatportOAuthToken.
        """
        data = json.loads(
            beets.ui.input_(
                "Could not fetch token. Check your beatport username and password "
                "in the config, or try to get token manually.\n"
                "Login at https://api.beatport.com/v4/docs/ "
                "and paste /token endpoint response from the browser:"
            )
        )

        return BeatportOAuthToken.from_api_response(data)

    def _tokenfile(self) -> str:
        """Get the path to the JSON file for storing the OAuth token."""
        return self.config["tokenfile"].get(confuse.Filename(in_app_dir=True))

    def candidates(
        self,
        items: Sequence[Item],
        artist: str,
        album: str,
        va_likely: bool,
    ) -> list[AlbumInfo]:
        """Returns a list of AlbumInfo objects for beatport search results
        matching release and artist (if not various).
        """
        if self.client is None:
            return []
        if va_likely:
            query = album
        else:
            query = f"{artist} {album}"
        try:
            return self._get_releases(query)
        except BeatportAPIError as e:
            self._log.warning("API Error: {0} (query: {1})", e, query)
            return []

    def item_candidates(
        self, item: Item, artist: str, title: str
    ) -> list[TrackInfo]:
        """Returns a list of TrackInfo objects for beatport search results
        matching title and artist.
        """
        if self.client is None:
            return []
        query = f"{artist} {title}"
        try:
            return self._get_tracks(query)
        except BeatportAPIError as e:
            self._log.warning("API Error: {0} (query: {1})", e, query)
            return []

    def album_for_id(self, album_id: str) -> AlbumInfo | None:
        """Fetches a release by its Beatport ID or URL and returns an AlbumInfo
        object or None if the query is not a valid ID or release is not found.
        """
        if self.client is None:
            return None
        if not album_id:
            self._log.debug("No release ID provided.")
            return None
        self._log.debug("Searching for release {0}", album_id)
        match = RELEASE_ID_PATTERN.search(album_id)
        if not match:
            self._log.debug("Not a valid Beatport release ID.")
            return None
        release = self.client.get_release(match.group(2))
        if release:
            return self._get_album_info(release)
        return None

    def track_for_id(self, track_id: str) -> TrackInfo | None:
        """Fetches a track by its Beatport ID or URL and returns a
        TrackInfo object or None if the track is not a valid
        Beatport ID or track is not found.
        """
        if self.client is None:
            return None
        self._log.debug("Searching for track {0}", track_id)
        match = TRACK_ID_PATTERN.search(track_id)
        if not match:
            self._log.debug("Not a valid Beatport track ID.")
            return None
        bp_track = self.client.get_track(match.group(2))
        if bp_track is not None:
            return self._get_track_info(bp_track)
        return None

    def _get_releases(self, query: str) -> list[AlbumInfo]:
        """Returns a list of AlbumInfo objects for a beatport search query."""
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Non-ASCII word characters (e.g. accented letters) are
        # preserved by the \W+ pattern.
        query = NON_WORD_PATTERN.sub(" ", query)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = MEDIUM_INFO_PATTERN.sub("", query)
        albums = [self._get_album_info(x) for x in self.client.search(query)]
        return albums

    def _get_album_info(self, release: BeatportRelease) -> AlbumInfo:
        """Returns an AlbumInfo object for a Beatport Release object."""
        va = len(release.artists) >= VA_ARTIST_THRESHOLD
        artist, artist_id = self._get_artist(
            (artist.id, artist.name)
            for artist in release.artists
            if artist is not None
        )
        if va:
            artist = VA_ARTIST_NAME
        tracks = [
            self._get_track_info(x) for x in release.tracks if x is not None
        ]

        return AlbumInfo(
            album=release.name,
            album_id=release.id,
            artist=artist,
            artist_id=artist_id,
            tracks=tracks,
            albumtype=release.type,
            va=va,
            year=release.publish_date.year if release.publish_date else None,
            month=release.publish_date.month if release.publish_date else None,
            day=release.publish_date.day if release.publish_date else None,
            label=release.label.name if release.label else None,
            catalognum=release.catalog_number,
            media=MEDIA_TYPE,
            data_source=self.data_source,
            data_url=release.url,
            genre=None,
        )

    def _get_track_info(self, track: BeatportTrack) -> TrackInfo:
        """Returns a TrackInfo object for a Beatport Track object."""
        title = track.name
        if track.mix_name != ORIGINAL_MIX_NAME:
            title += f" ({track.mix_name})"
        artist, artist_id = self._get_artist(
            (artist.id, artist.name)
            for artist in track.artists
            if artist is not None
        )
        length = track.length.total_seconds()
        extra_fields: dict = {}
        # Populate album-level metadata from a related release when importing singletons
        enrich_config = self.config["singletons_with_album_metadata"]
        if (
            enrich_config["enabled"].get()
            and (release := track.release) is not None
            and not release.tracks
        ):
            # Fetch full release data as it's not available in the API response
            # for a single track
            full_release = self.client.get_release(release.id)
            if full_release:
                release = full_release
            if enrich_config["year"].get() and release.publish_date:
                extra_fields["year"] = release.publish_date.year
                extra_fields["month"] = release.publish_date.month
                extra_fields["day"] = release.publish_date.day
            if enrich_config["album"].get() and release.name:
                extra_fields["album"] = release.name
            if enrich_config["label"].get():
                if release.label and release.label.name:
                    extra_fields["label"] = release.label.name
            if enrich_config["catalognum"].get() and release.catalog_number:
                extra_fields["catalognum"] = release.catalog_number
            if enrich_config["albumartist"].get() and release.artists:
                albumartist, _albumartist_id = self._get_artist(
                    (a.id, a.name) for a in release.artists if a is not None
                )
                extra_fields["albumartist"] = albumartist
            if (
                enrich_config["track_number"].get()
                and not track.number
                and release.tracks
            ):
                for t in release.tracks:
                    if t.id == track.id:
                        # For singletons, beets' apply_item_metadata does not map
                        # TrackInfo.index to Item.track (it's in SPECIAL_FIELDS).
                        # Pass it as 'track' so _apply_metadata copies it through.
                        extra_fields["track"] = t.number
                        break
        return TrackInfo(
            title=title,
            track_id=track.id,
            artist=artist,
            artist_id=artist_id,
            length=length,
            index=track.number,
            medium_index=track.number,
            media=MEDIA_TYPE,
            data_source=self.data_source,
            data_url=track.url,
            bpm=track.bpm,
            initial_key=track.initial_key,
            genre=track.genre,
            **extra_fields,
        )

    def _get_artist(self, artists: object) -> tuple[str, str | None]:
        """Returns an artist string (all artists) and an artist_id (the main
        artist) for a list of Beatport release or track artists.
        """
        return MetadataSourcePlugin.get_artist(
            artists=artists, id_key=0, name_key=1
        )

    def _get_tracks(self, query: str) -> list[TrackInfo]:
        """Returns a list of TrackInfo objects for a Beatport query."""
        bp_tracks = self.client.search(query, model="tracks")
        tracks = [self._get_track_info(x) for x in bp_tracks if x is not None]
        return tracks
