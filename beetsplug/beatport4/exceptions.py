"""Exceptions for the beets-beatport4 plugin."""

from __future__ import annotations


class BeatportAPIError(Exception):
    def __init__(
        self, message: object = "", status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
