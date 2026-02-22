"""Tests for the _redact utility function."""

from __future__ import annotations

from unittest.mock import patch

from beetsplug.beatport4 import _redact


class TestRedact:
    def test_redact_returns_redacted(self):
        assert _redact("secret") == "<REDACTED>"

    def test_redact_disabled_returns_value(self):
        with patch.dict(
            "os.environ",
            {"BEATPORT4_DEBUG_DISABLE_REDACTION": "1"},
        ):
            assert _redact("secret") == "secret"
