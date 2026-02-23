"""Beatport API v4 HTTP client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from beetsplug.beatport4.constants import (
    API_BASE_URL,
    CLIENT_ID_PATTERN,
    HTML_PARAGRAPH_PATTERN,
    HTTP_TIMEOUT,
    RELEASE_TRACKS_PER_PAGE,
    SCRIPT_SRC_PATTERN,
    SEARCH_RESULTS_PER_PAGE,
    USER_AGENT,
)
from beetsplug.beatport4.exceptions import BeatportAPIError
from beetsplug.beatport4.models import (
    BeatportMyAccount,
    BeatportOAuthToken,
    BeatportRelease,
    BeatportTrack,
)
from beetsplug.beatport4.utils import _redact

if TYPE_CHECKING:
    import logging
    from collections.abc import Generator


class Beatport4Client:
    def __init__(
        self,
        log: logging.Logger,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        beatport_token: BeatportOAuthToken | None = None,
    ) -> None:
        """Initialize the client and ensure it is correctly authorized.

        Three authentication paths are attempted in order:

        1. If *beatport_token* is non-expired, verify it via ``/my/account``.
        2. If the token is missing, expired, or invalid and *username* /
           *password* are provided, run the full OAuth authorization flow.
        3. If neither a usable token nor credentials are available, raise
           :py:class:`BeatportAPIError`.

        :param log:             Logger instance for debug/warning output.
        :param client_id:       Beatport API client ID (scraped automatically
                                when *None*).
        :param username:        Beatport account username.
        :param password:        Beatport account password.
        :param beatport_token:  Previously obtained OAuth token to reuse.
        """
        self._api_base = API_BASE_URL
        self._api_client_id = client_id
        self._beatport_redirect_uri = f"{self._api_base}/auth/o/post-message/"
        self.username = username
        self.password = password
        self.beatport_token = beatport_token
        self._log = log

        # Token from the file passed
        if self.beatport_token and not self.beatport_token.is_expired():
            self._log.debug("Trying beatport token loaded from file")
            try:
                my_account = self.get_my_account()
                self._log.debug(
                    "Beatport authorized with stored token as {0} <{1}>",
                    _redact(my_account.username),
                    _redact(my_account.email),
                )
            except BeatportAPIError:
                # Token from the file could be invalid, authorize and fetch new
                self._log.debug("Beatport token loaded from file invalid")
                self.beatport_token = self._authorize()
        elif self.username and self.password:
            self.beatport_token = self._authorize()
        else:
            raise BeatportAPIError(
                "Neither Beatport username/password, nor access token is given."
            )

    def _fetch_beatport_client_id(self) -> str:
        """Fetch Beatport API client ID from the docs script."""
        try:
            html = requests.get(
                f"{API_BASE_URL}/docs/", timeout=HTTP_TIMEOUT
            ).content.decode("utf-8")
        except requests.exceptions.RequestException as e:
            raise BeatportAPIError(
                f"Error fetching Beatport docs page: {e}"
            ) from e
        scripts_matches = SCRIPT_SRC_PATTERN.findall(html)
        last_error = None
        for script_url in scripts_matches:
            url = f"https://api.beatport.com{script_url}"
            try:
                js = requests.get(url, timeout=HTTP_TIMEOUT).content.decode(
                    "utf-8"
                )
            except requests.exceptions.RequestException as e:
                self._log.debug("Failed to fetch script {}: {}", url, e)
                last_error = e
                continue
            client_id_matches = CLIENT_ID_PATTERN.findall(js)
            if client_id_matches:
                return client_id_matches[0]
        msg = "Could not fetch API_CLIENT_ID"
        if last_error:
            msg += f" (last error: {last_error})"
        raise BeatportAPIError(msg)

    def _authorize(self) -> BeatportOAuthToken:
        """Authorize client and fetch access token.

        Uses the username and password stored on the client instance with the
        ``authorization_code`` grant type in the Beatport OAuth flow.

        :returns: Beatport OAuth token.
        """
        self._log.debug(
            "Started authorizing to the API using username and password"
        )
        if self._api_client_id is None:
            self._api_client_id = self._fetch_beatport_client_id()

        try:
            with requests.Session() as s:
                # Login to get session id and csrf token cookies
                response = s.post(
                    url=self._make_url("/auth/login/"),
                    json={
                        "username": self.username,
                        "password": self.password,
                    },
                )
                response.raise_for_status()
                data = response.json()
                if "username" not in data or "email" not in data:
                    # response contains error message from Beatport API
                    self._log.debug("Beatport auth error: {0}", data)
                    raise BeatportAPIError(data)

                self._log.debug(
                    "Authorized with username and password as {0} <{1}>",
                    _redact(data["username"]),
                    _redact(data["email"]),
                )

                # Fetch authorization code
                response = s.get(
                    url=self._make_url(
                        "/auth/o/authorize/",
                        query={
                            "response_type": "code",
                            "client_id": self._api_client_id,
                            "redirect_uri": self._beatport_redirect_uri,
                        },
                    ),
                    allow_redirects=False,
                )

                body = response.content.decode("utf-8")
                if "invalid_request" in body:
                    paragraphs = HTML_PARAGRAPH_PATTERN.findall(body)
                    msg = paragraphs[0] if paragraphs else body
                    raise BeatportAPIError(f"Beatport OAuth error: {msg}")

                # Auth code is available in the Location header
                if "Location" not in response.headers:
                    raise BeatportAPIError(
                        "Beatport OAuth redirect missing "
                        "Location header; "
                        f"status={response.status_code}"
                    )
                next_url = urlparse(
                    self._make_url(response.headers["Location"])
                )
                codes = parse_qs(next_url.query).get("code")
                if not codes:
                    raise BeatportAPIError(
                        "No authorization code in Beatport "
                        f"redirect: {next_url.geturl()}"
                    )
                auth_code = codes[0]

                self._log.debug("Authorization code: {0}", _redact(auth_code))

                # Exchange authorization code for access token
                response = s.post(
                    url=self._make_url(
                        "/auth/o/token/",
                        query={
                            "code": auth_code,
                            "grant_type": "authorization_code",
                            "redirect_uri": self._beatport_redirect_uri,
                            "client_id": self._api_client_id,
                        },
                    )
                )
                response.raise_for_status()
                data = response.json()
                self._log.debug(
                    "Exchanged authorization code for the access token: {0}",
                    _redact(json.dumps(data)),
                )

                return BeatportOAuthToken.from_api_response(data)
        except requests.exceptions.HTTPError as e:
            raise BeatportAPIError(
                f"Beatport authorization failed with HTTP "
                f"{e.response.status_code}: {e}",
                status_code=e.response.status_code,
            ) from e
        except requests.exceptions.RequestException as e:
            raise BeatportAPIError(
                f"Error connecting to Beatport during authorization: {e}"
            ) from e

    def get_my_account(self) -> BeatportMyAccount:
        """Get information about current account.

        :returns: The user account information.
        """
        response = self._get("/my/account")
        return BeatportMyAccount.from_api_response(response)

    def search(
        self,
        query: str,
        model: str = "releases",
        details: bool = True,
    ) -> Generator[BeatportRelease | BeatportTrack]:
        """Perform a search of the Beatport catalogue.

        :param query:           Query string
        :param model:           Type of results to search for, can be
                                'releases' or 'tracks'
        :param details:         Retrieve additional information about the
                                search results. Currently this will fetch
                                the tracklist for releases and do nothing for
                                tracks
        :returns:               Search results
        """
        response = self._get(
            "catalog/search",
            q=query,
            per_page=SEARCH_RESULTS_PER_PAGE,
            type=model,
        )
        if model == "releases":
            for release in response["releases"]:
                if details:
                    release = self.get_release(release["id"])
                    if release:
                        yield release
                    continue
                yield BeatportRelease.from_api_response(release)
        elif model == "tracks":
            for track in response["tracks"]:
                yield BeatportTrack.from_api_response(track)

    def get_release(self, beatport_id: int | str) -> BeatportRelease | None:
        """Get information about a single release.

        :param beatport_id:     Beatport ID of the release
        :returns:               The matching release
        """
        try:
            response = self._get(f"/catalog/releases/{beatport_id}/")
        except BeatportAPIError as e:
            self._log.debug("Failed to fetch release {}: {}", beatport_id, e)
            return None
        release = BeatportRelease.from_api_response(response)
        release.tracks = self.get_release_tracks(beatport_id)
        return release

    def get_release_tracks(self, beatport_id: int | str) -> list[BeatportTrack]:
        """Get all tracks for a given release.

        :param beatport_id:     Beatport ID of the release
        :returns:               Tracks in the matching release
        """
        try:
            response = self._get(
                f"/catalog/releases/{beatport_id}/tracks/",
                per_page=RELEASE_TRACKS_PER_PAGE,
            )
        except BeatportAPIError as e:
            self._log.debug(
                "Failed to fetch release tracks {}: {}",
                beatport_id,
                e,
            )
            return []
        # The release-tracks endpoint returns abbreviated track objects
        # missing fields like 'number' (track position), so we fetch
        # each track individually via get_track().
        tracks = [self.get_track(t["id"]) for t in response if t is not None]
        return [t for t in tracks if t is not None]

    def get_track(self, beatport_id: int | str) -> BeatportTrack | None:
        """Get information about a single track.

        :param beatport_id:     Beatport ID of the track
        :returns:               The matching track
        """
        try:
            response = self._get(f"/catalog/tracks/{beatport_id}/")
        except BeatportAPIError as e:
            self._log.debug("Failed to fetch track {}: {}", beatport_id, e)
            return None
        return BeatportTrack.from_api_response(response)

    def _make_url(self, endpoint: str, query: dict | None = None) -> str:
        """Get complete URL for a given API endpoint."""
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        if query:
            return self._api_base + endpoint + "?" + urlencode(query)
        return self._api_base + endpoint

    def get_image(
        self,
        beatport_id: int | str,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Fetches image from Beatport in a binary format.

        :param beatport_id: Beatport ID of the track
        :param width:       Width of the image to fetch using dynamic uri
        :param height:      Height of the image to fetch using dynamic uri
        :returns:           Image as binary data or None if not found
        :raises BeatportAPIError: If the image fetch request fails.
        """
        track = self.get_track(beatport_id)
        if track is None:
            return None

        if width == 0:
            width = None
        if height == 0:
            height = None

        if (
            width is not None or height is not None
        ) and track.image_dynamic_url is not None:
            image_url = track.image_dynamic_url.format(
                w=width or height, h=height or width
            )
        else:
            image_url = track.image_url
        if image_url is None:
            return None

        try:
            headers = self._get_request_headers()
            self._log.debug("Fetching image from URL: {}", image_url)
            response = requests.get(
                image_url, headers=headers, timeout=HTTP_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            raise BeatportAPIError(
                f"Error fetching image from Beatport: {e}"
            ) from e
        if not response:
            raise BeatportAPIError(
                f"Error {response.status_code} for '{image_url}'",
                status_code=response.status_code,
            )

        return response.content

    def _get(self, endpoint: str, **kwargs: object) -> dict | list:
        """Perform a GET request on a given API endpoint.

        Automatically extracts result data from the response and converts HTTP
        exceptions into :py:class:`BeatportAPIError` objects.
        """
        try:
            headers = self._get_request_headers()
            response = requests.get(
                self._make_url(endpoint),
                params=kwargs,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise BeatportAPIError(
                f"Error connecting to Beatport API: {e}"
            ) from e
        if not response.ok:
            raise BeatportAPIError(
                f"Error {response.status_code} for '{response.request.path_url}'",
                status_code=response.status_code,
            )

        try:
            json_response = response.json()
        except ValueError as e:
            raise BeatportAPIError(
                f"Invalid JSON in Beatport API response "
                f"for '{response.request.path_url}': {e}"
            ) from e

        # Handle both list and single entity responses
        if "results" in json_response:
            return json_response["results"]
        return json_response

    def _get_request_headers(self) -> dict[str, str]:
        """Formats Authorization and User-Agent HTTP client request headers

        :returns: HTTP client request headers
        """
        return {
            "Authorization": f"Bearer {self.beatport_token.access_token}",
            "User-Agent": USER_AGENT,
        }
