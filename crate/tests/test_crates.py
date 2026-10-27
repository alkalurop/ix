from __future__ import annotations

import io
import os
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ix_crate.crates import (
    CratePlaylist,
    PathIndex,
    TrackRef,
    apply_nml,
    apply_xml,
    dest_folder_for,
    format_plan,
    load_nml_playlists,
    load_xml_playlists,
    plan_membership,
    xml_path_index,
)
from ix_crate.stems_playlists import _rb_location, _traktor_dir_file


def _nml(path: Path, entries: str, playlists: str) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<NML VERSION=\"20\">"
        f'<COLLECTION ENTRIES="1">{entries}</COLLECTION>'
        "<PLAYLISTS><NODE TYPE=\"FOLDER\" NAME=\"$ROOT\">"
        f'<SUBNODES COUNT="1">{playlists}</SUBNODES>'
        "</NODE></PLAYLISTS></NML>",
        encoding="utf-8",
    )
    return path


def _xml(path: Path, tracks: str, playlists: str) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DJ_PLAYLISTS Version="1.0.0">'
        f'<COLLECTION Entries="1">{tracks}</COLLECTION>'
        f"<PLAYLISTS><NODE Name=\"ROOT\" Type=\"0\" Count=\"1\">{playlists}</NODE>"
        "</PLAYLISTS></DJ_PLAYLISTS>",
        encoding="utf-8",
    )
    return path


class UniquifyTests(unittest.TestCase):
    def test_same_folder_duplicate_gets_number(self) -> None:
        from ix_crate.crates import uniquify_playlist_names

        a = CratePlaylist(name="Soundtrack", folder=("Origin Stories",), tracks=[])
        b = CratePlaylist(name="Soundtrack", folder=("Origin Stories",), tracks=[])
        c = CratePlaylist(name="Soundtrack", folder=("House",), tracks=[])
        names = [(p.folder, p.name) for p in uniquify_playlist_names([a, b, c])]
        self.assertEqual(
            names,
            [
                (("Origin Stories",), "Soundtrack"),
                (("Origin Stories",), "Soundtrack (2)"),
                (("House",), "Soundtrack"),
            ],
        )
    def test_hardlink_matches_inode(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            apple = root / "Music" / "Honey.m4a"
            stems = root / "stems_audio" / "Honey.m4a"
            apple.parent.mkdir(parents=True)
            stems.parent.mkdir(parents=True)
            apple.write_bytes(b"mix")
            os.link(apple, stems)
            index = PathIndex()
            index.add(apple, "42")
            hit = index.lookup(stems)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0], "42")
            self.assertEqual(hit[1], "inode")


class XmlMembershipTests(unittest.TestCase):
    def test_writes_music_folder_and_keeps_cues(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Honey.m4a"
            audio.write_bytes(b"mix")
            xml = Path(tmp) / "rekordbox.xml"
            loc = _rb_location(audio)
            _xml(
                xml,
                '<TRACK TrackID="7" Name="Honey" Artist="Moby" Genre="House" '
                f'Location="{loc}">'
                '<POSITION_MARK Name="cue1" Type="0" Start="12.5"/>'
                '<TEMPO Inizio="0" Bpm="124.00" Metro="4/4" Battito="1"/>'
                "</TRACK>",
                '<NODE Name="STEMIT" Type="0" Count="1">'
                '<NODE Name="Mixes" Type="1" KeyType="0" Entries="1">'
                '<TRACK Key="7"/></NODE></NODE>',
            )
            playlists = [
                CratePlaylist(name="Never Forget 50th v01", tracks=[TrackRef(path=audio)])
            ]
            index = xml_path_index(xml)
            plan_playlists = plan_membership(playlists, index)
            from ix_crate.crates import SyncPlan

            plan = SyncPlan(
                source="music",
                dest="xml",
                dest_folder="MUSIC",
                playlists=plan_playlists,
            )
            apply_xml(plan, xml)
            tree = ET.parse(xml)
            track = tree.find(".//COLLECTION/TRACK")
            self.assertEqual(track.get("Genre"), "House")
            self.assertIsNotNone(track.find("POSITION_MARK"))
            self.assertIsNotNone(track.find("TEMPO"))
            self.assertEqual(track.find("POSITION_MARK").get("Start"), "12.5")
            music = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "MUSIC" and node.get("Type") == "0"
            ][0]
            crate = [n for n in music.findall("NODE") if n.get("Name") == "Never Forget 50th v01"][0]
            self.assertEqual(crate.get("Type"), "1")
            self.assertEqual(crate.find("TRACK").get("Key"), "7")
            stemit = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "STEMIT" and node.get("Type") == "0"
            ][0]
            self.assertEqual(stemit.find("NODE").get("Name"), "Mixes")

    def test_nested_folder_replace_rebuilds_music_keeps_stemit(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Honey.m4a"
            audio.write_bytes(b"mix")
            xml = Path(tmp) / "rekordbox.xml"
            _xml(
                xml,
                f'<TRACK TrackID="7" Name="Honey" Location="{_rb_location(audio)}"/>',
                '<NODE Name="STEMIT" Type="0" Count="1">'
                '<NODE Name="Mixes" Type="1" KeyType="0" Entries="1">'
                '<TRACK Key="7"/></NODE></NODE>'
                '<NODE Name="MUSIC" Type="0" Count="1">'
                '<NODE Name="stale" Type="1" KeyType="0" Entries="0"/>'
                "</NODE>",
            )
            from ix_crate.crates import SyncPlan

            plan = SyncPlan(
                source="music",
                dest="xml",
                dest_folder="MUSIC",
                replace_folder=True,
                playlists=plan_membership(
                    [
                        CratePlaylist(
                            name="Pivots",
                            folder=("House",),
                            tracks=[TrackRef(path=audio)],
                        )
                    ],
                    xml_path_index(xml),
                ),
            )
            apply_xml(plan, xml)
            tree = ET.parse(xml)
            music = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "MUSIC" and node.get("Type") == "0"
            ][0]
            names = [n.get("Name") for n in music.findall("NODE")]
            self.assertEqual(names, ["House"])
            house = music.find("NODE")
            crate = house.find("NODE")
            self.assertEqual(crate.get("Name"), "Pivots")
            self.assertEqual(crate.find("TRACK").get("Key"), "7")
            stale = [n for n in music.iter("NODE") if n.get("Name") == "stale"]
            self.assertEqual(stale, [])
            stemit = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "STEMIT" and node.get("Type") == "0"
            ]
            self.assertEqual(len(stemit), 1)

    def test_skips_tracks_not_in_collection(self) -> None:
        with TemporaryDirectory() as tmp:
            known = Path(tmp) / "Honey.m4a"
            missing = Path(tmp) / "Ghost.m4a"
            known.write_bytes(b"mix")
            missing.write_bytes(b"nope")
            xml = Path(tmp) / "rekordbox.xml"
            _xml(
                xml,
                f'<TRACK TrackID="7" Name="Honey" Location="{_rb_location(known)}"/>',
                "",
            )
            playlists = [
                CratePlaylist(
                    name="Set",
                    tracks=[TrackRef(path=known), TrackRef(path=missing, label="Ghost")],
                )
            ]
            planned = plan_membership(playlists, xml_path_index(xml))
            self.assertEqual(len(planned[0].matched), 1)
            self.assertEqual(len(planned[0].missing), 1)
            self.assertEqual(planned[0].missing[0].label, "Ghost")

    def test_apply_xml_fills_empty_genre_from_nml(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Honey.m4a"
            audio.write_bytes(b"mix")
            directory, file_attr = _traktor_dir_file(audio.resolve())
            nml = _nml(
                Path(tmp) / "collection.nml",
                f'<ENTRY TITLE="Honey" ARTIST="Moby">'
                f'<LOCATION DIR="{directory}" FILE="{file_attr}" VOLUME="Macintosh HD"/>'
                '<INFO GENRE="Deep House"/></ENTRY>',
                "",
            )
            xml = Path(tmp) / "rekordbox.xml"
            loc = _rb_location(audio)
            _xml(
                xml,
                f'<TRACK TrackID="7" Name="Honey" Artist="Moby" Location="{loc}"/>',
                "",
            )
            from ix_crate.crates import SyncPlan

            plan = SyncPlan(
                source="music",
                dest="xml",
                dest_folder="MUSIC",
                playlists=plan_membership(
                    [CratePlaylist(name="Set", tracks=[TrackRef(path=audio)])],
                    xml_path_index(xml),
                ),
            )
            apply_xml(plan, xml, nml=nml)
            track = ET.parse(xml).find(".//COLLECTION/TRACK")
            self.assertEqual(track.get("Genre"), "Deep House")

    def test_ingest_adds_location_row_not_stub(self) -> None:
        with TemporaryDirectory() as tmp:
            known = Path(tmp) / "Honey.m4a"
            extra = Path(tmp) / "Closer.m4a"
            drm = Path(tmp) / "Cloud.m4p"
            known.write_bytes(b"mix")
            extra.write_bytes(b"also")
            drm.write_bytes(b"fairplay")
            xml = Path(tmp) / "rekordbox.xml"
            _xml(
                xml,
                f'<TRACK TrackID="7" Name="Honey" Genre="House" Location="{_rb_location(known)}">'
                '<POSITION_MARK Name="cue1" Type="0" Start="12.5"/>'
                "</TRACK>",
                "",
            )
            from ix_crate.crates import SyncPlan

            playlists = [
                CratePlaylist(
                    name="DJ Sets",
                    tracks=[
                        TrackRef(path=known, artist="Moby", title="Honey"),
                        TrackRef(path=extra, artist="NIN", title="Closer"),
                        TrackRef(path=drm, artist="X", title="Cloud"),
                    ],
                )
            ]
            plan = SyncPlan(
                source="music",
                dest="xml",
                dest_folder="MUSIC",
                playlists=plan_membership(playlists, xml_path_index(xml)),
            )
            apply_xml(plan, xml)
            tree = ET.parse(xml)
            tracks = tree.find("COLLECTION").findall("TRACK")
            self.assertEqual(len(tracks), 2)
            honey = next(t for t in tracks if t.get("TrackID") == "7")
            self.assertEqual(honey.get("Genre"), "House")
            self.assertEqual(honey.find("POSITION_MARK").get("Start"), "12.5")
            closer = next(t for t in tracks if t.get("Name") == "Closer")
            self.assertEqual(closer.get("Artist"), "NIN")
            self.assertTrue(closer.get("Location"))
            crate = [
                n
                for n in tree.getroot().iter("NODE")
                if n.get("Name") == "DJ Sets" and n.get("Type") == "1"
            ][0]
            keys = {child.get("Key") for child in crate.findall("TRACK")}
            self.assertEqual(keys, {"7", closer.get("TrackID")})
            self.assertEqual(plan.playlists[0].ingested, 1)
            self.assertEqual(len(plan.playlists[0].missing), 1)
            self.assertTrue(str(plan.playlists[0].missing[0].path).endswith(".m4p"))


class NmlMembershipTests(unittest.TestCase):
    def test_nml_to_xml_skips_stemit_and_writes_traktor_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Honey.m4a"
            audio.write_bytes(b"mix")
            directory, file_attr = _traktor_dir_file(audio.resolve())
            key = f"Macintosh HD{directory}{file_attr}"
            nml = _nml(
                Path(tmp) / "collection.nml",
                f'<ENTRY TITLE="Honey" ARTIST="Moby">'
                f'<LOCATION DIR="{directory}" FILE="{file_attr}" VOLUME="Macintosh HD"/>'
                '<INFO COMMENT="energy 7"/><CUE_V2 NAME="cue" TYPE="0" START="1000"/>'
                "</ENTRY>",
                '<NODE TYPE="FOLDER" NAME="STEMIT"><SUBNODES COUNT="1">'
                '<NODE TYPE="PLAYLIST" NAME="Mixes"><PLAYLIST ENTRIES="1" TYPE="LIST">'
                f'<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="{key}"/></ENTRY>'
                "</PLAYLIST></NODE></SUBNODES></NODE>"
                '<NODE TYPE="PLAYLIST" NAME="Humid chills"><PLAYLIST ENTRIES="1" TYPE="LIST">'
                f'<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="{key}"/></ENTRY>'
                "</PLAYLIST></NODE>",
            )
            xml = _xml(
                Path(tmp) / "rekordbox.xml",
                f'<TRACK TrackID="9" Name="Honey" Location="{_rb_location(audio)}">'
                '<POSITION_MARK Name="hot" Type="0" Start="4"/>'
                "</TRACK>",
                "",
            )
            loaded = load_nml_playlists(nml, names={"Humid chills"})
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].name, "Humid chills")
            stemit = load_nml_playlists(nml, names={"Mixes"})
            self.assertEqual(stemit, [])
            from ix_crate.crates import SyncPlan

            plan = SyncPlan(
                source="nml",
                dest="xml",
                dest_folder=dest_folder_for("nml", "xml"),
                playlists=plan_membership(loaded, xml_path_index(xml)),
            )
            apply_xml(plan, xml)
            tree = ET.parse(xml)
            track = tree.find(".//COLLECTION/TRACK")
            self.assertEqual(track.find("POSITION_MARK").get("Start"), "4")
            trakt = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "TRAKTOR" and node.get("Type") == "0"
            ][0]
            crate = trakt.find("NODE")
            self.assertEqual(crate.get("Name"), "Humid chills")
            self.assertEqual(crate.find("TRACK").get("Key"), "9")

    def test_xml_to_nml_writes_music_folder_without_touching_cues(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Honey.m4a"
            audio.write_bytes(b"mix")
            directory, file_attr = _traktor_dir_file(audio.resolve())
            nml = _nml(
                Path(tmp) / "collection.nml",
                f'<ENTRY TITLE="Honey" ARTIST="Moby">'
                f'<LOCATION DIR="{directory}" FILE="{file_attr}" VOLUME="Macintosh HD"/>'
                '<INFO COMMENT="energy 8"/><CUE_V2 NAME="cue" TYPE="0" START="2000"/>'
                "</ENTRY>",
                '<NODE TYPE="FOLDER" NAME="STEMIT"><SUBNODES COUNT="0"/></NODE>',
            )
            xml = _xml(
                Path(tmp) / "rekordbox.xml",
                f'<TRACK TrackID="3" Name="Honey" Location="{_rb_location(audio)}"/>',
                '<NODE Name="MUSIC" Type="0" Count="1">'
                '<NODE Name="Never Forget 50th v01" Type="1" KeyType="0" Entries="1">'
                '<TRACK Key="3"/></NODE></NODE>',
            )
            loaded = load_xml_playlists(xml, names={"Never Forget 50th v01"})
            self.assertEqual(len(loaded), 1)
            from ix_crate.crates import SyncPlan, nml_path_index

            plan = SyncPlan(
                source="xml",
                dest="nml",
                dest_folder=dest_folder_for("xml", "nml"),
                playlists=plan_membership(loaded, nml_path_index(nml)),
            )
            apply_nml(plan, nml)
            tree = ET.parse(nml)
            entry = tree.find(".//COLLECTION/ENTRY")
            self.assertEqual(entry.find("INFO").get("COMMENT"), "energy 8")
            self.assertEqual(entry.find("CUE_V2").get("START"), "2000")
            music = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("TYPE") == "FOLDER" and node.get("NAME") == "MUSIC"
            ][0]
            crate = [
                node
                for node in music.find("SUBNODES").findall("NODE")
                if node.get("NAME") == "Never Forget 50th v01"
            ][0]
            self.assertEqual(crate.find("PLAYLIST").get("ENTRIES"), "1")
            stemit = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("TYPE") == "FOLDER" and node.get("NAME") == "STEMIT"
            ][0]
            self.assertIsNotNone(stemit)


class CliTests(unittest.TestCase):
    def test_help_lists_from_to(self) -> None:
        from ix_crate.__main__ import main

        buf = io.StringIO()
        with patch("sys.stdout", buf), self.assertRaises(SystemExit) as ctx:
            main(["crates", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = buf.getvalue()
        self.assertIn("--from", text)
        self.assertIn("--to", text)
        self.assertIn("--execute", text)

    def test_requires_playlist_or_all(self) -> None:
        from ix_crate.crates import main

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = main(["--from", "nml", "--to", "xml"])
        self.assertEqual(code, 2)
        self.assertIn("--playlist", buf.getvalue())

    def test_format_plan_names_folder(self) -> None:
        from ix_crate.crates import PlaylistPlan, SyncPlan

        text = format_plan(
            SyncPlan(
                source="music",
                dest="xml",
                dest_folder="MUSIC",
                playlists=[
                    PlaylistPlan(
                        name="Never Forget 50th v01",
                        folder=(),
                        matched=[],
                        missing=[TrackRef(path=Path("/tmp/x.m4a"), label="Ghost")],
                    )
                ],
            )
        )
        self.assertIn("MUSIC", text)
        self.assertIn("Ghost", text)


if __name__ == "__main__":
    unittest.main()
