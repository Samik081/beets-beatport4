"""Tests for Beatport data classes."""

import time

from beetsplug.beatport4 import (
    BeatportArtist,
    BeatportLabel,
    BeatportMyAccount,
    BeatportOAuthToken,
    BeatportRelease,
    BeatportTrack,
)


class TestBeatportOAuthToken:
    def test_construction_with_expires_in(self, sample_token_data):
        token = BeatportOAuthToken.from_api_response(sample_token_data)
        assert token.access_token == "tok_abc123"
        assert token.refresh_token == "ref_xyz789"
        assert token.expires_at > time.time()

    def test_construction_with_expires_at(self):
        future = time.time() + 9999
        data = {
            "access_token": "a",
            "expires_at": future,
            "refresh_token": "r",
        }
        token = BeatportOAuthToken.from_api_response(data)
        assert token.expires_at == future

    def test_is_expired_false(self, sample_token_data):
        token = BeatportOAuthToken.from_api_response(sample_token_data)
        assert token.is_expired() is False

    def test_is_expired_true(self):
        data = {
            "access_token": "a",
            "expires_at": 0,
            "refresh_token": "r",
        }
        token = BeatportOAuthToken.from_api_response(data)
        assert token.is_expired() is True

    def test_encode_decode_roundtrip(self, sample_token_data):
        token = BeatportOAuthToken.from_api_response(sample_token_data)
        encoded = token.encode()
        token2 = BeatportOAuthToken.from_api_response(encoded)
        assert token2.access_token == token.access_token
        assert token2.expires_at == token.expires_at
        assert token2.refresh_token == token.refresh_token


class TestBeatportLabel:
    def test_construction(self, sample_label_data):
        label = BeatportLabel.from_api_response(sample_label_data)
        assert label.id == "200"
        assert label.name == "Test Label"

    def test_str(self, sample_label_data):
        label = BeatportLabel.from_api_response(sample_label_data)
        assert "Test Label" in str(label)


class TestBeatportArtist:
    def test_construction(self, sample_artist_data):
        artist = BeatportArtist.from_api_response(sample_artist_data)
        assert artist.id == "100"
        assert artist.name == "Test Artist"

    def test_str(self, sample_artist_data):
        artist = BeatportArtist.from_api_response(sample_artist_data)
        assert "Test Artist" in str(artist)


class TestBeatportRelease:
    def test_full_construction(self, sample_release_data):
        release = BeatportRelease.from_api_response(sample_release_data)
        assert release.id == "400"
        assert release.name == "Test Release"
        assert len(release.artists) == 1
        assert release.label.name == "Test Label"
        assert release.catalog_number == "TL001"
        assert release.type == "Album"
        assert release.publish_date.year == 2024

    def test_minimal_construction(self):
        release = BeatportRelease.from_api_response(
            {"id": 1, "name": "Minimal"}
        )
        assert release.id == "1"
        assert release.name == "Minimal"
        assert release.artists == []

    def test_none_artist_filtered(self):
        data = {
            "id": 1,
            "name": "R",
            "artists": [{"id": 1, "name": "A"}, None],
        }
        release = BeatportRelease.from_api_response(data)
        assert len(release.artists) == 1

    def test_str_few_artists(self, sample_release_data):
        release = BeatportRelease.from_api_response(sample_release_data)
        s = str(release)
        assert "Test Artist" in s
        assert "Test Release" in s

    def test_str_many_artists(self, sample_release_data):
        sample_release_data["artists"] = [
            {"id": i, "name": f"A{i}"} for i in range(5)
        ]
        release = BeatportRelease.from_api_response(sample_release_data)
        assert "Various Artists" in str(release)


class TestBeatportTrack:
    def test_full_construction(self, sample_track_data):
        track = BeatportTrack.from_api_response(sample_track_data)
        assert track.id == "300"
        assert track.name == "Test Track"
        assert len(track.artists) == 1
        assert track.bpm == 128
        assert track.mix_name == "Original Mix"
        assert track.number == 1
        assert track.url is not None
        assert track.length.total_seconds() == 360.0

    def test_sub_genre_precedence(self, sample_track_data):
        track = BeatportTrack.from_api_response(sample_track_data)
        assert track.genre == "Tech House"

    def test_genre_fallback(self, sample_track_data):
        del sample_track_data["sub_genre"]
        track = BeatportTrack.from_api_response(sample_track_data)
        assert track.genre == "House"

    def test_length_fallback_to_string(self, sample_track_data):
        sample_track_data["length_ms"] = 0
        sample_track_data["length"] = "6:30"
        track = BeatportTrack.from_api_response(sample_track_data)
        assert track.length.total_seconds() == 390.0

    def test_none_artist_filtered(self, sample_track_data):
        sample_track_data["artists"] = [
            {"id": 1, "name": "A"},
            None,
        ]
        track = BeatportTrack.from_api_response(sample_track_data)
        assert len(track.artists) == 1


class TestBeatportTrackNormalizeKey:
    def _make_track(self, key_name):
        """Helper to make a track with a specific key."""
        data = {
            "id": 1,
            "name": "T",
            "artists": [],
            "length_ms": 1000,
            "key": {"name": key_name},
        }
        return BeatportTrack.from_api_response(data)

    def test_major_key(self):
        track = self._make_track("C Major")
        assert track.initial_key == "Cmaj"

    def test_minor_key(self):
        track = self._make_track("A Minor")
        assert track.initial_key == "Amin"

    def test_sharp_key(self):
        track = self._make_track("F# Minor")
        assert track.initial_key == "F#min"

    def test_flat_key(self):
        track = self._make_track("Eb Major")
        assert track.initial_key == "D#maj"

    def test_no_key(self):
        data = {
            "id": 1,
            "name": "T",
            "artists": [],
            "length_ms": 1000,
        }
        track = BeatportTrack.from_api_response(data)
        assert track.initial_key is None


class TestBeatportMyAccount:
    def test_construction(self):
        acc = BeatportMyAccount.from_api_response(
            {"id": 1, "email": "a@b.com", "username": "user1"}
        )
        assert acc.id == "1"
        assert acc.email == "a@b.com"
        assert acc.username == "user1"

    def test_str(self):
        acc = BeatportMyAccount.from_api_response(
            {"id": 1, "email": "a@b.com", "username": "user1"}
        )
        assert "user1" in str(acc)
        assert "a@b.com" in str(acc)
