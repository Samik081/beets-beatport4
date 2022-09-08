# This file is part of beets.
# Copyright 2016, Adrian Sampson.
# Copyright 2022, Szymon "Samik" Tarasiński.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Adds Beatport release and track search support to the autotagger
"""

import json
import re
from datetime import timedelta

from beets.library import MusicalKey

import beets
import beets.ui
import requests
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.plugins import BeetsPlugin, MetadataSourcePlugin, get_distance
import confuse

USER_AGENT = f'beets/{beets.__version__} +https://beets.io/'


class BeatportAPIError(Exception):
    pass


class BeatportLabel:
    def __init__(self, data):
        self.id = str(data['id'])
        self.name = str(data['name'])

    def __str__(self):
        return "<BeatportLabel: {}>".format(self.name)

    def __repr__(self):
        return str(self)


class BeatportArtist:
    def __init__(self, data):
        self.id = str(data['id'])
        self.name = str(data['name'])

    def __str__(self):
        return "<BeatportArtist: {}>".format(self.name)

    def __repr__(self):
        return str(self)


class BeatportRelease:
    def __init__(self, data):
        self.id = str(data['id'])
        self.name = str(data['name'])
        self.artists = []
        if 'artists' in data:
            self.artists = [BeatportArtist(x) for x in data['artists']]
        if 'label' in data:
            self.label = BeatportLabel(data['label'])
        if 'catalog_number' in data:
            self.catalog_number = str(data['catalog_number'])
        if 'slug' in data:
            self.url = "https://beatport.com/release/{}/{}" \
                .format(data['slug'], data['id'])
        if 'type' in data:
            self.category = data['type']['name']

    def __str__(self):
        if len(self.artists) < 4:
            artist_str = ", ".join(x.name for x in self.artists)
        else:
            artist_str = "Various Artists"
        return "<BeatportRelease: {} - {} ({})>" \
            .format(artist_str, self.name, self.catalog_number)

    def __repr__(self):
        return str(self)


class BeatportTrack:
    def __init__(self, data):
        self.id = str(data['id'])
        self.name = str(data['name'])
        self.artists = [BeatportArtist(x) for x in data['artists']]
        self.length = timedelta(milliseconds=data.get('length_ms', 0) or 0)
        self.number = None
        self.initial_key = None
        self.url = None
        self.bpm = None
        self.genre = None
        if not self.length:
            try:
                min, sec = data.get('length', '0:0').split(':')
                self.length = timedelta(minutes=int(min), seconds=int(sec))
            except ValueError:
                pass
        if 'key' in data:
            self.initial_key = self._normalize_key(str(data['key']['name']))
        if 'bpm' in data:
            self.bpm = int(data['bpm'])
        if 'sub_genre' in data and data['sub_genre']:
            self.genre = str(data['sub_genre']['name'])
        elif 'genre' in data and data['genre']:
            self.genre = str(data['genre']['name'])
        if 'mix_name' in data:
            self.mix_name = data['mix_name']
        if 'number' in data:
            self.number = data['number']
        if 'release' in data:
            self.release = BeatportRelease(data['release'])
        if 'remixers' in data:
            self.remixers = data['remixers']
        if 'slug' in data:
            self.url = "https://beatport.com/track/{}/{}" \
                .format(data['slug'], data['id'])

    def __str__(self):
        artist_str = ", ".join(x.name for x in self.artists)
        return "<BeatportTrack: {} - {} ({})>" \
            .format(artist_str, self.name, self.mix_name)

    def __repr__(self):
        return str(self)

    def _normalize_key(self, key):
        """ Normalize new Beatport key name format (e.g "Eb Major, C# Minor)
         for backwards compatibility

        :param key:    Key name
        """
        (letter_sign, chord) = key.split(" ")
        return MusicalKey().normalize((letter_sign + chord.lower())[:-2])


class BeatportMyAccount:
    def __init__(self, data):
        self.id = str(data['id'])
        self.email = str(data['email'])
        self.username = str(data['username'])

    def __str__(self):
        return "<BeatportMyAccount: {} <{}>>" \
            .format(self.username, self.email)

    def __repr__(self):
        return str(self)


class Beatport4Client:
    def __init__(self, access_token):
        """ Initiate the client with OAuth2 Bearer access token
         and fetch user account data

        :param access_token:    OAuth2 Bearer access token
        """
        self._api_base = 'https://api.beatport.com/v4'
        self.access_token = access_token

        try:
            my_account = self.get_my_account()
            print('Beatport authorized as {} <{}>'
                  .format(my_account.username, my_account.email))
        except BeatportAPIError as e:
            print("Exception when calling /my/account endpoint: %s\n" % e)
            raise e

    def get_my_account(self):
        """ Get information about current account.

        :returns:               The user account information
        :rtype:                 :py:class:`BeatportMyAccount`
        """
        response = self._get('/my/account')
        return BeatportMyAccount(response)

    def search(self, query, model='releases', details=True):
        """ Perform a search of the Beatport catalogue.

        :param query:           Query string
        :param model:           Type of releases to search for, can be
                                'release' or 'track'
        :param details:         Retrieve additional information about the
                                search results. Currently this will fetch
                                the tracklist for releases and do nothing for
                                tracks
        :returns:               Search results
        :rtype:                 generator that yields
                                py:class:`BeatportRelease` or
                                :py:class:`BeatportTrack`
        """
        response = self._get('catalog/search', q=query, per_page=5, type=model)
        if model == 'releases':
            for release in response['releases']:
                if details:
                    yield self.get_release(release['id'])
                yield BeatportRelease(release)
        elif model == 'tracks':
            for track in response['tracks']:
                yield BeatportTrack(track)

    def get_release(self, beatport_id):
        """ Get information about a single release.

        :param beatport_id:     Beatport ID of the release
        :returns:               The matching release
        :rtype:                 :py:class:`BeatportRelease`
        """
        response = self._get(f'/catalog/releases/{beatport_id}/')
        if response:
            release = BeatportRelease(response)
            release.tracks = self.get_release_tracks(beatport_id)
            return release
        return None

    def get_release_tracks(self, beatport_id):
        """ Get all tracks for a given release.

        :param beatport_id:     Beatport ID of the release
        :returns:               Tracks in the matching release
        :rtype:                 list of :py:class:`BeatportTrack`
        """
        response = self._get(f'/catalog/releases/{beatport_id}/tracks/',
                             perPage=100)
        return [BeatportTrack(t) for t in response]

    def get_track(self, beatport_id):
        """ Get information about a single track.

        :param beatport_id:     Beatport ID of the track
        :returns:               The matching track
        :rtype:                 :py:class:`BeatportTrack`
        """
        response = self._get(f'/catalog/tracks/{beatport_id}/')
        return BeatportTrack(response)

    def _make_url(self, endpoint):
        """ Get complete URL for a given API endpoint. """
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        return self._api_base + endpoint

    def _get(self, endpoint, **kwargs):
        """ Perform a GET request on a given API endpoint.

        Automatically extracts result data from the response and converts HTTP
        exceptions into :py:class:`BeatportAPIError` objects.
        """
        try:
            headers = {
                'Authorization': 'Bearer {}'.format(self.access_token),
                'User-Agent': USER_AGENT
            }
            response = requests.get(self._make_url(endpoint),
                                    params=kwargs,
                                    headers=headers)
        except Exception as e:
            raise BeatportAPIError(
                "Error connecting to Beatport API: {}"
                .format(e))
        if not response:
            raise BeatportAPIError(
                "Error {0.status_code} for '{0.request.path_url}"
                .format(response))

        json_response = response.json()

        # Handle both list and single entity responses
        if 'results' in json_response:
            return json_response['results']
        return json_response


class Beatport4Plugin(BeetsPlugin):
    data_source = 'Beatport'

    def __init__(self):
        super().__init__()
        self.config.add({
            'tokenfile': 'beatport_token.json',
            'source_weight': 0.5,
        })
        self.client = None
        self.register_listener('import_begin', self.setup)

    def setup(self):
        """Loads access token from the file
        """
        # Get the OAuth token from a file
        try:
            with open(self._tokenfile()) as f:
                data = json.load(f)
        except OSError:
            data = self._prompt_write_token_file()

        if 'access_token' not in data:
            raise beets.ui.UserError(
                'Invalid token given or stored in beatport_token.json file.')

        try:
            self.client = Beatport4Client(data['access_token'])
        except BeatportAPIError as e:
            # Retr
            if "Error 401" in str(e) or "Error 403" in str(e):
                data = self._prompt_write_token_file()

                self.client = Beatport4Client(data['access_token'])

    def _tokenfile(self):
        """Get the path to the JSON file for storing the OAuth token.
        """
        return self.config['tokenfile'].get(confuse.Filename(in_app_dir=True))

    def album_distance(self, items, album_info, mapping):
        """Returns the Beatport source weight and the maximum source weight
        for albums.
        """
        return get_distance(
            data_source=self.data_source,
            info=album_info,
            config=self.config
        )

    def track_distance(self, item, track_info):
        """Returns the Beatport source weight and the maximum source weight
        for individual tracks.
        """
        return get_distance(
            data_source=self.data_source,
            info=track_info,
            config=self.config
        )

    def candidates(self, items, artist, release, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for beatport search results
        matching release and artist (if not various).
        """
        if va_likely:
            query = release
        else:
            query = f'{artist} {release}'
        try:
            return self._get_releases(query)
        except BeatportAPIError as e:
            self._log.debug('API Error: {0} (query: {1})', e, query)
            return []

    def item_candidates(self, item, artist, title):
        """Returns a list of TrackInfo objects for beatport search results
        matching title and artist.
        """
        query = f'{artist} {title}'
        try:
            return self._get_tracks(query)
        except BeatportAPIError as e:
            self._log.debug('API Error: {0} (query: {1})', e, query)
            return []

    def album_for_id(self, release_id):
        """Fetches a release by its Beatport ID and returns an AlbumInfo object
        or None if the query is not a valid ID or release is not found.
        """
        self._log.debug('Searching for release {0}', release_id)
        match = re.search(r'(^|beatport\.com/release/.+/)(\d+)$', release_id)
        if not match:
            self._log.debug('Not a valid Beatport release ID.')
            return None
        release = self.client.get_release(match.group(2))
        if release:
            return self._get_album_info(release)
        return None

    def track_for_id(self, track_id):
        """Fetches a track by its Beatport ID and returns a
        TrackInfo object or None if the track is not a valid
        Beatport ID or track is not found.
        """
        self._log.debug('Searching for track {0}', track_id)
        match = re.search(r'(^|beatport\.com/track/.+/)(\d+)$', track_id)
        if not match:
            self._log.debug('Not a valid Beatport track ID.')
            return None
        bp_track = self.client.get_track(match.group(2))
        if bp_track is not None:
            return self._get_track_info(bp_track)
        return None

    def _get_releases(self, query):
        """Returns a list of AlbumInfo objects for a beatport search query.
        """
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Use `re.UNICODE` flag to avoid stripping non-english
        # word characters.
        query = re.sub(r'\W+', ' ', query, flags=re.UNICODE)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r'\b(CD|disc)\s*\d+', '', query, flags=re.I)
        albums = [self._get_album_info(x)
                  for x in self.client.search(query)]
        return albums

    def _get_album_info(self, release):
        """Returns an AlbumInfo object for a Beatport Release object.
        """
        va = len(release.artists) > 3
        artist, artist_id = self._get_artist(
            ((artist.id, artist.name) for artist in release.artists)
        )
        if va:
            artist = "Various Artists"
        tracks = [self._get_track_info(x) for x in release.tracks]

        return AlbumInfo(album=release.name, album_id=release.id,
                         artist=artist, artist_id=artist_id, tracks=tracks,
                         albumtype=release.category, va=va,
                         year=release.release_date.year,
                         month=release.release_date.month,
                         day=release.release_date.day,
                         label=release.label_name,
                         catalognum=release.catalog_number, media='Digital',
                         data_source=self.data_source, data_url=release.url,
                         genre=release.genre)

    def _get_track_info(self, track):
        """Returns a TrackInfo object for a Beatport Track object.
        """
        title = track.name
        if track.mix_name != "Original Mix":
            title += f" ({track.mix_name})"
        artist, artist_id = self._get_artist(
            ((artist.id, artist.name) for artist in track.artists)
        )
        length = track.length.total_seconds()
        return TrackInfo(title=title, track_id=track.id,
                         artist=artist, artist_id=artist_id,
                         length=length, index=track.number,
                         medium_index=track.number,
                         data_source=self.data_source, data_url=track.url,
                         bpm=track.bpm, initial_key=track.initial_key,
                         genre=track.genre)

    def _get_artist(self, artists):
        """Returns an artist string (all artists) and an artist_id (the main
        artist) for a list of Beatport release or track artists.
        """
        return MetadataSourcePlugin.get_artist(
            artists=artists, id_key=0, name_key=1
        )

    def _get_tracks(self, query):
        """Returns a list of TrackInfo objects for a Beatport query.
        """
        bp_tracks = self.client.search(query, model='tracks')
        tracks = [self._get_track_info(x) for x in bp_tracks]
        return tracks

    def _prompt_write_token_file(self):
        """Prompts user to paste the OAuth token in the console and
        writes the contents to the beatport_token.json file.
        Returns parsed JSON.
        """
        data = json.loads(beets.ui.input_(
            "Token not yet fetched, expired or not valid.\n"
            "Login at https://api.beatport.com/v4/docs/ "
            "and paste /token?code... response from the browser:"))
        with open(self._tokenfile(), 'w') as f:
            json.dump(data, f)

        return data
