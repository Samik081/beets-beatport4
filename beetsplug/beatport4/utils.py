"""Utility helpers for the beets-beatport4 plugin."""

from __future__ import annotations

import os


def _redact(value):
    """Mask sensitive values unless BEATPORT4_DEBUG_DISABLE_REDACTION is set."""
    if os.environ.get("BEATPORT4_DEBUG_DISABLE_REDACTION"):
        return value
    return "<REDACTED>"


def _image_extension(data: bytes) -> str:
    """Guess the file extension for raw image data. Beatport serves JPEGs,
    so anything that is not recognizably a PNG is treated as one.
    """
    if data.startswith(b"\x89PNG"):
        return ".png"
    return ".jpg"
