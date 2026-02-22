"""Adds Beatport release and track search support to the autotagger"""

from beetsplug.beatport4.client import Beatport4Client
from beetsplug.beatport4.exceptions import BeatportAPIError
from beetsplug.beatport4.models import (
    BeatportArtist,
    BeatportLabel,
    BeatportMyAccount,
    BeatportOAuthToken,
    BeatportRelease,
    BeatportTrack,
)
from beetsplug.beatport4.plugin import Beatport4Plugin
from beetsplug.beatport4.utils import _redact

__all__ = [
    "Beatport4Client",
    "Beatport4Plugin",
    "BeatportAPIError",
    "BeatportArtist",
    "BeatportLabel",
    "BeatportMyAccount",
    "BeatportOAuthToken",
    "BeatportRelease",
    "BeatportTrack",
    "_redact",
]
