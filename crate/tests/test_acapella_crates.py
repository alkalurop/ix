from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

from ix_crate.acapella_crates import (
    AcapellaTrack,
    clear_acapella_playlists,
    genre_of,
    group_acapellas,
    index_music_genres,
    playlist_plans,
)
from ix_crate.stems_playlists import DiskFile


class MatchTests(unittest.TestCase):
    def test_artist_title_prefers_a_real_genre(self) -> None:
        pair, titles = index_music_genres(
            [
                {"Artist": "Radiohead", "Name": "Example", "Genre": "Acapella"},
                {"Artist": "Radiohead", "Name": "Example", "Genre": "Rock"},
                {"Artist": "One", "Name": "Shared", "Genre": "House"},
                {"Artist": "Two", "Name": "Shared", "Genre": "Techno"},
                {"Artist": "Solo", "Name": "Only", "Genre": "EDM, Ambient"},
            ]
        )
        self.assertEqual(genre_of("Radiohead", "Example", pair, titles), "Rock")
        self.assertEqual(genre_of("Nobody", "Only", pair, titles), "Ambient")
        self.assertEqual(genre_of("Nobody", "Shared", pair, titles), "Untagged")

    def test_vocal_file_lands_in_the_song_genre(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            album = root / "Radiohead" / "Hail to the Thief"
            album.mkdir(parents=True)
            vocal = album / "Example_vocals.m4a"
            vocal.write_bytes(b"vocal")
            mix = album / "Example.m4a"
            mix.write_bytes(b"mix")
            pair, titles = index_music_genres(
                [{"Artist": "Radiohead", "Name": "Example", "Genre": "Rock"}]
            )
            groups = group_acapellas(
                root=root,
                files=[
                    DiskFile(path=vocal.resolve(), crate="Acapellas"),
                    DiskFile(path=mix.resolve(), crate="Mixes"),
                ],
                genre_index=(pair, titles),
            )
            self.assertEqual(list(groups), ["Rock"])
            self.assertEqual(groups["Rock"][0].path, vocal.resolve())
            self.assertEqual(groups["Rock"][0].title, "Example")

    def test_plan_is_acapellas_folder(self) -> None:
        track = AcapellaTrack(
            path=Path("/tmp/Example_vocals.m4a"),
            artist="Radiohead",
            title="Example",
            genre="Rock",
        )
        plans = playlist_plans({"Rock": [track]}, dest="nml", nml_index={})
        self.assertEqual(plans[0].name, "Rock")
        self.assertEqual(plans[0].folder, ("ACAPELLAS",))
        self.assertEqual(plans[0].missing[0].title, "Example")

    def test_clear_drops_retired_list_and_keeps_played(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            nml = folder / "collection.nml"
            nml.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<NML><COLLECTION ENTRIES=\"0\"/>"
                "<PLAYLISTS><NODE TYPE=\"FOLDER\" NAME=\"$ROOT\"><SUBNODES COUNT=\"1\">"
                "<NODE TYPE=\"FOLDER\" NAME=\"MUSIC\"><SUBNODES COUNT=\"3\">"
                "<NODE TYPE=\"PLAYLIST\" NAME=\"Acapella\"><PLAYLIST ENTRIES=\"1\" TYPE=\"LIST\" UUID=\"a\"/></NODE>"
                "<NODE TYPE=\"FOLDER\" NAME=\"Acapellas\"><SUBNODES COUNT=\"1\">"
                "<NODE TYPE=\"PLAYLIST\" NAME=\"House\"><PLAYLIST ENTRIES=\"1\" TYPE=\"LIST\" UUID=\"b\"/></NODE>"
                "</SUBNODES></NODE>"
                "<NODE TYPE=\"PLAYLIST\" NAME=\"Played\"><PLAYLIST ENTRIES=\"1\" TYPE=\"LIST\" UUID=\"c\"/></NODE>"
                "</SUBNODES></NODE></SUBNODES></NODE></PLAYLISTS></NML>",
                encoding="utf-8",
            )
            xml = folder / "rekordbox.xml"
            xml.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<DJ_PLAYLISTS><COLLECTION Entries=\"0\"/>"
                "<PLAYLISTS><NODE Name=\"ROOT\" Type=\"0\" Count=\"1\">"
                "<NODE Name=\"MUSIC\" Type=\"0\" Count=\"3\">"
                "<NODE Name=\"Acapella\" Type=\"1\" KeyType=\"0\" Entries=\"1\"/>"
                "<NODE Name=\"Acapellas\" Type=\"0\" Count=\"1\">"
                "<NODE Name=\"House\" Type=\"1\" KeyType=\"0\" Entries=\"1\"/>"
                "</NODE>"
                "<NODE Name=\"Played\" Type=\"1\" KeyType=\"0\" Entries=\"1\"/>"
                "</NODE></NODE></PLAYLISTS></DJ_PLAYLISTS>",
                encoding="utf-8",
            )
            clear_acapella_playlists(nml, kind="nml")
            clear_acapella_playlists(xml, kind="xml")
            nml_names = [
                node.get("NAME")
                for node in ET.parse(nml).getroot().iter("NODE")
                if node.get("TYPE") == "PLAYLIST"
            ]
            xml_names = [
                node.get("Name")
                for node in ET.parse(xml).getroot().iter("NODE")
                if node.get("Type") == "1"
            ]
            self.assertEqual(nml_names, ["Played"])
            self.assertEqual(xml_names, ["Played"])
            self.assertTrue(
                any(
                    node.get("NAME") == "Acapellas"
                    for node in ET.parse(nml).getroot().iter("NODE")
                )
            )
