"""Tests for the utility helpers."""

from __future__ import annotations

from unittest.mock import patch

from beetsplug.beatport4 import _redact
from beetsplug.beatport4.utils import _image_extension


class TestRedact:
    def test_redact_returns_redacted(self):
        assert _redact("secret") == "<REDACTED>"

    def test_redact_disabled_returns_value(self):
        with patch.dict(
            "os.environ",
            {"BEATPORT4_DEBUG_DISABLE_REDACTION": "1"},
        ):
            assert _redact("secret") == "secret"


class TestImageExtension:
    def test_png_signature(self):
        assert _image_extension(b"\x89PNG\r\n\x1a\n rest") == ".png"

    def test_jpeg_signature(self):
        assert _image_extension(b"\xff\xd8\xff\xe0 rest") == ".jpg"

    def test_unknown_data_defaults_to_jpg(self):
        assert _image_extension(b"whatever") == ".jpg"
