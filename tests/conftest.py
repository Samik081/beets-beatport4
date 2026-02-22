"""Shared fixtures for beets-beatport4 tests."""

import json
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import beets
import beets.plugins
import pytest
from beets.plugins import BeetsPlugin

from beetsplug.beatport4 import Beatport4Client, Beatport4Plugin

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Load a fixture file from tests/fixtures/.

    JSON files are parsed and returned as dicts/lists.
    Other files are returned as strings.
    """
    path = FIXTURES_DIR / name
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return text


@pytest.fixture(autouse=True)
def isolated_beets_config(tmp_path):
    """Isolate beets configuration so tests don't touch the real config."""
    env = {"BEETSDIR": str(tmp_path), "HOME": str(tmp_path)}
    with patch.dict("os.environ", env):
        beets.config.sources = []
        beets.config.read(defaults=True)
        yield
        BeetsPlugin.listeners = defaultdict(list)
        BeetsPlugin._raw_listeners = defaultdict(list)
        beets.plugins._instances = []


@pytest.fixture
def plugin():
    """Create a Beatport4Plugin instance without a client."""
    return Beatport4Plugin()


@pytest.fixture
def mock_client():
    """Create a MagicMock with the Beatport4Client spec."""
    return MagicMock(spec=Beatport4Client)


@pytest.fixture
def plugin_with_client(plugin, mock_client):
    """Plugin with a mocked client attached."""
    plugin.client = mock_client
    return plugin


# --------------- Sample data fixtures ---------------


@pytest.fixture
def sample_artist_data():
    return {"id": 100, "name": "Test Artist"}


@pytest.fixture
def sample_label_data():
    return {"id": 200, "name": "Test Label"}


@pytest.fixture
def sample_track_data(sample_artist_data):
    return {
        "id": 300,
        "name": "Test Track",
        "artists": [sample_artist_data],
        "length_ms": 360000,
        "key": {"name": "Eb Minor"},
        "bpm": 128,
        "sub_genre": {"name": "Tech House"},
        "genre": {"name": "House"},
        "mix_name": "Original Mix",
        "number": 1,
        "slug": "test-track",
        "release": {
            "id": 400,
            "name": "Test Release",
            "image": {
                "uri": "https://example.com/img.jpg",
                "dynamic_uri": "https://example.com/img/{w}x{h}.jpg",
            },
        },
        "remixers": [],
    }


@pytest.fixture
def sample_release_data(sample_artist_data, sample_label_data):
    return {
        "id": 400,
        "name": "Test Release",
        "artists": [sample_artist_data],
        "label": sample_label_data,
        "catalog_number": "TL001",
        "slug": "test-release",
        "type": {"name": "Album"},
        "publish_date": "2024-06-15",
    }


@pytest.fixture
def sample_token_data():
    return {
        "access_token": "tok_abc123",
        "expires_in": 3600,
        "refresh_token": "ref_xyz789",
    }
