"""Utility helpers for the beets-beatport4 plugin."""

from __future__ import annotations

import os


def _redact(value):
    """Mask sensitive values unless BEATPORT4_DEBUG_DISABLE_REDACTION is set."""
    if os.environ.get("BEATPORT4_DEBUG_DISABLE_REDACTION"):
        return value
    return "<REDACTED>"
