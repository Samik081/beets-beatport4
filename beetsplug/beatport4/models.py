"""Data models for Beatport API responses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from beets.dbcore.types import MusicalKey

from beetsplug.beatport4.constants import (
    BEATPORT_SITE_URL,
    DATE_FORMAT,
    TOKEN_EXPIRY_BUFFER_SECONDS,
    VA_ARTIST_NAME,
    VA_ARTIST_THRESHOLD,
)


@dataclass
class BeatportOAuthToken:
    access_token: str
    expires_at: float
    refresh_token: str

    @classmethod
    def from_api_response(cls, data: dict) -> BeatportOAuthToken:
        access_token = str(data["access_token"])
        if "expires_at" in data:
            expires_at = data["expires_at"]
        else:
            expires_at = time.time() + int(data["expires_in"])
        refresh_token = str(data["refresh_token"])
        return cls(
            access_token=access_token,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    def is_expired(self) -> bool:
        """Check whether the token is expired or about to expire
        within the safety buffer.
        """
        return time.time() + TOKEN_EXPIRY_BUFFER_SECONDS >= self.expires_at

    def encode(self) -> dict:
        """Encode this token as a JSON-serializable dict."""
        return {
            "access_token": self.access_token,
            "expires_at": self.expires_at,
            "refresh_token": self.refresh_token,
        }


@dataclass
class BeatportLabel:
    id: str
    name: str

    @classmethod
    def from_api_response(cls, data: dict) -> BeatportLabel:
        return cls(id=str(data["id"]), name=str(data["name"]))

    def __str__(self) -> str:
        return f"<BeatportLabel: {self.name}>"


@dataclass
class BeatportArtist:
    id: str
    name: str

    @classmethod
    def from_api_response(cls, data: dict) -> BeatportArtist:
        return cls(id=str(data["id"]), name=str(data["name"]))

    def __str__(self) -> str:
        return f"<BeatportArtist: {self.name}>"


@dataclass
class BeatportRelease:
    id: str
    name: str
    artists: list[BeatportArtist] = field(default_factory=list)
    tracks: list[BeatportTrack] = field(default_factory=list)
    type: str | None = None
    label: BeatportLabel | None = None
    catalog_number: str | None = None
    url: str | None = None
    publish_date: datetime | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> BeatportRelease:
        artists = []
        if "artists" in data:
            artists = [
                BeatportArtist.from_api_response(x)
                for x in data["artists"]
                if x is not None
            ]

        label = None
        if "label" in data:
            label = BeatportLabel.from_api_response(data["label"])

        catalog_number = None
        if "catalog_number" in data:
            catalog_number = str(data["catalog_number"])

        url = None
        if "slug" in data:
            url = f"{BEATPORT_SITE_URL}/release/{data['slug']}/{data['id']}"

        release_type = None
        if "type" in data:
            release_type = data["type"]["name"]

        publish_date = None
        if "publish_date" in data:
            publish_date = datetime.strptime(data["publish_date"], DATE_FORMAT)

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            artists=artists,
            tracks=[],
            type=release_type,
            label=label,
            catalog_number=catalog_number,
            url=url,
            publish_date=publish_date,
        )

    def __str__(self) -> str:
        if len(self.artists) < VA_ARTIST_THRESHOLD:
            artist_str = ", ".join(x.name for x in self.artists)
        else:
            artist_str = VA_ARTIST_NAME
        return f"<BeatportRelease: {artist_str} - {self.name} ({self.catalog_number})>"


@dataclass
class BeatportTrack:
    id: str
    name: str
    artists: list[BeatportArtist] = field(default_factory=list)
    length: timedelta = field(default_factory=lambda: timedelta(0))
    number: int | None = None
    initial_key: str | None = None
    url: str | None = None
    bpm: int | None = None
    genre: str | None = None
    image_url: str | None = None
    image_dynamic_url: str | None = None
    mix_name: str | None = None
    release: BeatportRelease | None = None
    remixers: list[dict] | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> BeatportTrack:
        artists = []
        if "artists" in data:
            artists = [
                BeatportArtist.from_api_response(x)
                for x in data["artists"]
                if x is not None
            ]
        length = timedelta(milliseconds=data.get("length_ms", 0) or 0)
        if not length:
            try:
                min_str, sec_str = (data.get("length", "0:0") or "0:0").split(
                    ":"
                )
                length = timedelta(minutes=int(min_str), seconds=int(sec_str))
            except ValueError:
                pass

        initial_key = None
        if data.get("key") and data["key"]["name"]:
            initial_key = BeatportTrack._normalize_key(str(data["key"]["name"]))

        bpm = None
        if data.get("bpm"):
            bpm = int(data["bpm"])

        genre = None
        if data.get("sub_genre"):
            genre = str(data["sub_genre"]["name"])
        elif data.get("genre"):
            genre = str(data["genre"]["name"])

        mix_name = data.get("mix_name")
        number = data.get("number")

        release = None
        image_url = None
        image_dynamic_url = None
        if "release" in data:
            release = BeatportRelease.from_api_response(data["release"])
            if "image" in data["release"]:
                if "uri" in data["release"]["image"]:
                    image_url = data["release"]["image"]["uri"]
                if "dynamic_uri" in data["release"]["image"]:
                    image_dynamic_url = data["release"]["image"]["dynamic_uri"]

        remixers = data.get("remixers")

        url = None
        if "slug" in data:
            url = f"{BEATPORT_SITE_URL}/track/{data['slug']}/{data['id']}"

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            artists=artists,
            length=length,
            number=number,
            initial_key=initial_key,
            url=url,
            bpm=bpm,
            genre=genre,
            image_url=image_url,
            image_dynamic_url=image_dynamic_url,
            mix_name=mix_name,
            release=release,
            remixers=remixers,
        )

    def __str__(self) -> str:
        artist_str = ", ".join(x.name for x in self.artists)
        return f"<BeatportTrack: {artist_str} - {self.name} ({self.mix_name})>"

    @staticmethod
    def _normalize_key(key: str) -> str | None:
        """Normalize Beatport key display format
        (e.g. "Eb Major", "C# Minor") to beets internal
        key notation (e.g. "D#maj", "C#min").
        """
        try:
            letter_sign, chord = key.split(" ")
        except ValueError:
            return None
        return MusicalKey().normalize((letter_sign + chord.lower())[:-2])


@dataclass
class BeatportMyAccount:
    id: str
    email: str
    username: str

    @classmethod
    def from_api_response(cls, data: dict) -> BeatportMyAccount:
        return cls(
            id=str(data["id"]),
            email=str(data["email"]),
            username=str(data["username"]),
        )

    def __str__(self) -> str:
        return f"<BeatportMyAccount: {self.username} <{self.email}>>"
