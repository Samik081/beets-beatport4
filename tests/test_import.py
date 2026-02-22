"""Tests for module imports and plugin interface compatibility."""

from beets.metadata_plugins import MetadataSourcePlugin


class TestModuleImport:
    def test_import_module(self):
        import beetsplug.beatport4  # noqa: F401

    def test_import_plugin_class(self):
        from beetsplug.beatport4 import Beatport4Plugin  # noqa: F401

    def test_import_client_class(self):
        from beetsplug.beatport4 import Beatport4Client  # noqa: F401

    def test_import_data_classes(self):
        from beetsplug.beatport4 import (  # noqa: F401
            BeatportArtist,
            BeatportLabel,
            BeatportMyAccount,
            BeatportOAuthToken,
            BeatportRelease,
            BeatportTrack,
        )

    def test_import_exception(self):
        from beetsplug.beatport4 import BeatportAPIError  # noqa: F401


class TestPluginInterface:
    def test_subclasses_metadata_source_plugin(self, plugin):
        assert isinstance(plugin, MetadataSourcePlugin)

    def test_data_source(self, plugin):
        assert plugin.data_source == "Beatport"

    def test_has_candidates(self, plugin):
        assert hasattr(plugin, "candidates")

    def test_has_item_candidates(self, plugin):
        assert hasattr(plugin, "item_candidates")

    def test_has_album_for_id(self, plugin):
        assert hasattr(plugin, "album_for_id")

    def test_has_track_for_id(self, plugin):
        assert hasattr(plugin, "track_for_id")

    def test_default_config_tokenfile(self, plugin):
        assert plugin.config["tokenfile"].get() == "beatport_token.json"

    def test_default_config_art(self, plugin):
        assert plugin.config["art"].get() is False

    def test_default_config_penalty(self, plugin):
        assert plugin.config["data_source_mismatch_penalty"].get() == 0.5
