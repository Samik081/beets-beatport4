"""Constants for the beets-beatport4 plugin."""

from __future__ import annotations

import re

import beets

# ── API URLs ──────────────────────────────────────────────────

API_BASE_URL = "https://api.beatport.com/v4"
BEATPORT_SITE_URL = "https://beatport.com"

# ── HTTP ──────────────────────────────────────────────────────

USER_AGENT = f"beets/{beets.__version__} +https://beets.io/"

# ── Pagination ────────────────────────────────────────────────

SEARCH_RESULTS_PER_PAGE = 5
RELEASE_TRACKS_PER_PAGE = 100

# ── Token ─────────────────────────────────────────────────────

TOKEN_EXPIRY_BUFFER_SECONDS = 30

# ── Artist / display ─────────────────────────────────────────

VA_ARTIST_THRESHOLD = 4
VA_ARTIST_NAME = "Various Artists"

# ── Track metadata ────────────────────────────────────────────

ORIGINAL_MIX_NAME = "Original Mix"
MEDIA_TYPE = "Digital"
DATE_FORMAT = "%Y-%m-%d"

# ── Compiled regex patterns ───────────────────────────────────

RELEASE_ID_PATTERN = re.compile(r"(^|beatport\.com/release/.+/)(\d+)$")
TRACK_ID_PATTERN = re.compile(r"(^|beatport\.com/track/.+/)(\d+)$")

# Used by _fetch_beatport_client_id
SCRIPT_SRC_PATTERN = re.compile(r"src=.(.*js)")
CLIENT_ID_PATTERN = re.compile(r"API_CLIENT_ID: \'(.*)\'")

# Used by _get_releases to sanitize search queries
NON_WORD_PATTERN = re.compile(r"\W+", flags=re.UNICODE)
MEDIUM_INFO_PATTERN = re.compile(r"\b(CD|disc)\s*\d+", flags=re.I)

# Used by _authorize to extract error messages
HTML_PARAGRAPH_PATTERN = re.compile(r"<p>(.*)</p>")
