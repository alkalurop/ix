"""Mixed In Key playlist → rekordbox xml + Traktor NML."""

from __future__ import annotations

import plistlib
import sqlite3
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

from ix_crate.mixed_in_crate import (
    MikCue,
    MikPlaylist,
    MikTrack,
    bookmark_path,
    build_comment,
    load_playlists,
    musical_key_value,
    normalize_camelot,
    notes_from_tag_blob,
    write_nml,
    write_xml,
)
from ix_crate.stems_playlists import _rb_location, _traktor_dir_file


def _xml(path: Path, tracks: str, playlists: str) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DJ_PLAYLISTS Version="1.0.0">'
        f'<COLLECTION Entries="1">{tracks}</COLLECTION>'
        f'<PLAYLISTS><NODE Name="ROOT" Type="0" Count="1">{playlists}</NODE>'
        "</PLAYLISTS></DJ_PLAYLISTS>",
        encoding="utf-8",
    )
    return path


def _nml(path: Path, entries: str, playlists: str) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<NML VERSION="20">'
        f'<COLLECTION ENTRIES="1">{entries}</COLLECTION>'
        '<PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT">'
        f'<SUBNODES COUNT="1">{playlists}</SUBNODES>'
        "</NODE></PLAYLISTS></NML>",
        encoding="utf-8",
    )
    return path


def _comment_blob(original: str, comment: str) -> bytes:
    uid = plistlib.UID
    payload = {
        "$version": 100000,
        "$objects": [
            "$null",
            {
                "NS.keys": [uid(2), uid(3)],
                "NS.objects": [uid(4), uid(5)],
                "$class": uid(6),
            },
            "originalComment",
            "comment",
            original,
            comment,
            {"$classname": "NSDictionary"},
        ],
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)


class CommentTests(unittest.TestCase):
    def test_camelot_and_traktor_musical_key(self) -> None:
        self.assertEqual(normalize_camelot("05a"), "5A")
        self.assertEqual(normalize_camelot("12B"), "12B")
        self.assertEqual(normalize_camelot("6d"), "")
        self.assertEqual(musical_key_value("5A"), 12)
        self.assertEqual(musical_key_value("6A"), 19)

    def test_comment_carries_energy_key_and_note(self) -> None:
        text = build_comment("5A", 6, ["Purchased at Beatport.com"])
        self.assertEqual(text, "5A - Energy 6 - Purchased at Beatport.com")

    def test_comment_keeps_rekordbox_note_and_skips_hex(self) -> None:
        text = build_comment("9A", 2, [], existing="9A - Energy 2 - crate note")
        self.assertEqual(text, "9A - Energy 2 - crate note")
        self.assertEqual(
            build_comment("9A", 2, [], existing="000005A4 0000001F 00002B2F"),
            "9A - Energy 2",
        )

    def test_tag_blob_prefers_human_note(self) -> None:
        blob = _comment_blob(
            "000005A4 0000001F 00002B2F",
            "Purchased at Beatport.com",
        )
        self.assertEqual(notes_from_tag_blob(blob), ["Purchased at Beatport.com"])
        titled = _comment_blob("(Johnny Fiasco&#39;s Nu Jazz Rerub)", "")
        self.assertEqual(
            notes_from_tag_blob(titled),
            ["(Johnny Fiasco's Nu Jazz Rerub)"],
        )

    def test_bookmark_path(self) -> None:
        raw = (
            b"book\x00/Users/david/Music/Music/Media.localized/Song.wav\x00Macintosh HD"
        )
        self.assertEqual(
            bookmark_path(raw),
            Path("/Users/david/Music/Music/Media.localized/Song.wav"),
        )


class LibraryLoadTests(unittest.TestCase):
    def test_skips_library_and_full_mirror(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "Lion Steps.wav"
            audio.write_bytes(b"RIFFmix")
            db = root / "Collection11.mikdb"
            self._seed(db, audio)
            playlists, skipped = load_playlists(db)
            self.assertEqual([item.name for item in playlists], ["Spiritual House"])
            reasons = {item.name: item.reason for item in skipped}
            self.assertEqual(reasons["Library"], "library")
            self.assertEqual(reasons["Dance Beats"], "library mirror")
            house = playlists[0]
            self.assertEqual(len(house.tracks), 1)
            self.assertEqual(house.tracks[0].key, "5A")
            self.assertEqual(house.tracks[0].energy, 6)
            self.assertEqual(house.tracks[0].cues[0].energy, 6)
            self.assertEqual(house.tracks[0].notes, ["Purchased at Beatport.com"])
            self.assertEqual(house.tracks[0].path, audio.resolve())

            named, named_skipped = load_playlists(db, names={"Dance Beats"})
            self.assertEqual([item.name for item in named], ["Dance Beats"])
            self.assertEqual(named_skipped, [])

    def _seed(self, db: Path, audio: Path) -> None:
        con = sqlite3.connect(db)
        con.executescript(
            """
            CREATE TABLE ZCOLLECTION (
                Z_PK INTEGER PRIMARY KEY, ZNAME TEXT, ZISLIBRARY INTEGER, ZINDEX INTEGER
            );
            CREATE TABLE Z_1SONGS (Z_1COLLECTIONS INTEGER, Z_5SONGS INTEGER);
            CREATE TABLE ZSONG (
                Z_PK INTEGER PRIMARY KEY, ZARTIST TEXT, ZNAME TEXT, ZALBUM TEXT,
                ZGENRE TEXT, ZKEY TEXT, ZENERGY REAL, ZTEMPO REAL, ZCOMMENT TEXT,
                ZBOOKMARKDATA BLOB, ZTAGCOMMENTS BLOB
            );
            CREATE TABLE ZCUEPOINT (
                Z_PK INTEGER PRIMARY KEY, ZSONG INTEGER, ZTIME REAL, ZENERGYLEVEL INTEGER
            );
            """
        )
        bookmark = b"xx" + str(audio).encode() + b"\x00"
        comments = _comment_blob("000005A4 0000001F", "Purchased at Beatport.com")
        con.execute(
            "INSERT INTO ZSONG VALUES (1, 'The Timewriter', 'Lion Steps', '', '', '5A', 6, 127, '', ?, ?)",
            (bookmark, comments),
        )
        con.execute(
            "INSERT INTO ZSONG VALUES (2, 'Other', 'Whole Library', '', '', '1A', 4, 120, '', ?, NULL)",
            (bookmark,),
        )
        con.executemany(
            "INSERT INTO ZCUEPOINT VALUES (?, ?, ?, ?)",
            [(1, 1, 0.255, 6), (2, 1, 15.739, 7)],
        )
        con.executemany(
            "INSERT INTO ZCOLLECTION VALUES (?, ?, ?, ?)",
            [(1, "Library", 1, 0), (2, "Dance Beats", 0, 0), (3, "Spiritual House", 0, 1)],
        )
        con.executemany(
            "INSERT INTO Z_1SONGS VALUES (?, ?)",
            [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)],
        )
        con.commit()
        con.close()


def _mik() -> MikTrack:
    return MikTrack(
        path=Path("."),
        artist="The Timewriter",
        title="Lion Steps",
        key="5A",
        energy=6,
        tempo=127,
        notes=["Purchased at Beatport.com"],
        cues=[MikCue(0.255, 6), MikCue(15.739, 7)],
    )


class XmlWriteTests(unittest.TestCase):
    def test_stamps_cues_key_comment_and_playlist(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Lion Steps.wav"
            audio.write_bytes(b"RIFFmix")
            other = Path(tmp) / "Untouched.wav"
            other.write_bytes(b"RIFFother")
            xml = _xml(
                Path(tmp) / "rekordbox.xml",
                (
                    f'<TRACK TrackID="7" Name="Lion Steps" Artist="The Timewriter" '
                    f'AverageBpm="127.00" Tonality="Cm" '
                    f'Location="{_rb_location(audio)}">'
                    '<POSITION_MARK Name="hot" Type="0" Start="4" Num="0"/>'
                    '<POSITION_MARK Name="memory" Type="0" Start="9" Num="-1"/>'
                    '<TEMPO Inizio="0" Bpm="127.00" Metro="4/4" Battito="1"/>'
                    "</TRACK>"
                    f'<TRACK TrackID="8" Name="Untouched" Location="{_rb_location(other)}">'
                    '<POSITION_MARK Name="keep" Type="0" Start="1" Num="0"/>'
                    "</TRACK>"
                ),
                '<NODE Name="STEMIT" Type="0" Count="0"/>',
            )
            mik = _mik()
            mik.path = audio
            write_xml([MikPlaylist("Spiritual House", [mik])], xml)
            write_xml([MikPlaylist("Spiritual House", [mik])], xml)
            tree = ET.parse(xml)
            tracks = {
                el.get("TrackID"): el
                for el in tree.getroot().findall("./COLLECTION/TRACK")
            }
            lion = tracks["7"]
            self.assertEqual(lion.get("Tonality"), "5A")
            self.assertEqual(lion.get("AverageBpm"), "127.00")
            self.assertEqual(
                lion.get("Comments"),
                "5A - Energy 6 - Purchased at Beatport.com",
            )
            hot = [mark for mark in lion.findall("POSITION_MARK") if mark.get("Num") != "-1"]
            self.assertEqual([mark.get("Name") for mark in hot], ["Energy 6", "Energy 7"])
            self.assertEqual(hot[0].get("Start"), "0.255")
            self.assertEqual(hot[0].get("Num"), "0")
            self.assertEqual(lion.find("TEMPO").get("Bpm"), "127.00")
            memory = [mark for mark in lion.findall("POSITION_MARK") if mark.get("Num") == "-1"]
            self.assertEqual(memory[0].get("Name"), "memory")
            untouched = tracks["8"]
            self.assertEqual(untouched.find("POSITION_MARK").get("Name"), "keep")
            folder = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "MIXED IN KEY" and node.get("Type") == "0"
            ][0]
            playlist = folder.find("NODE")
            self.assertEqual(playlist.get("Name"), "Spiritual House")
            self.assertEqual(playlist.find("TRACK").get("Key"), "7")
            stemit = [
                node
                for node in tree.getroot().iter("NODE")
                if node.get("Name") == "STEMIT"
            ]
            self.assertEqual(len(stemit), 1)

    def test_ingests_missing_file_row(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "New.wav"
            audio.write_bytes(b"RIFFnew")
            xml = _xml(Path(tmp) / "rekordbox.xml", "", "")
            mik = _mik()
            mik.path = audio
            mik.title = "New"
            write_xml([MikPlaylist("Spiritual House", [mik])], xml)
            track = ET.parse(xml).find("./COLLECTION/TRACK")
            self.assertEqual(track.get("Tonality"), "5A")
            self.assertEqual(track.get("Name"), "New")
            self.assertEqual(len(track.findall("POSITION_MARK")), 2)
            playlist = [
                node
                for node in ET.parse(xml).getroot().iter("NODE")
                if node.get("Name") == "Spiritual House"
            ][0]
            self.assertEqual(playlist.find("TRACK").get("Key"), track.get("TrackID"))


class NmlWriteTests(unittest.TestCase):
    def test_stamps_cues_and_keeps_grid_marker(self) -> None:
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "Lion Steps.wav"
            audio.write_bytes(b"RIFFmix")
            directory, file_attr = _traktor_dir_file(audio.resolve())
            key = f"Macintosh HD{directory}{file_attr}"
            nml = _nml(
                Path(tmp) / "collection.nml",
                (
                    f'<ENTRY TITLE="Lion Steps" ARTIST="The Timewriter">'
                    f'<LOCATION DIR="{directory}" FILE="{file_attr}" VOLUME="Macintosh HD"/>'
                    '<INFO KEY="10m" COMMENT="06A - Energy 5"/>'
                    '<MUSICAL_KEY VALUE="0"/>'
                    '<CUE_V2 NAME="old" DISPL_ORDER="0" TYPE="0" START="1000" '
                    'LEN="0.000000" REPEATS="-1" HOTCUE="0"/>'
                    '<CUE_V2 NAME="AutoGrid" DISPL_ORDER="0" TYPE="4" START="9.2" '
                    'LEN="0.000000" REPEATS="-1" HOTCUE="-1"/>'
                    '<TEMPO BPM="127.000000"/>'
                    "</ENTRY>"
                ),
                "",
            )
            mik = _mik()
            mik.path = audio
            write_nml([MikPlaylist("Spiritual House", [mik])], nml)
            write_nml([MikPlaylist("Spiritual House", [mik])], nml)
            entry = ET.parse(nml).find("./COLLECTION/ENTRY")
            info = entry.find("INFO")
            self.assertEqual(info.get("KEY"), "5A")
            self.assertEqual(info.get("COMMENT"), "5A - Energy 6 - Purchased at Beatport.com")
            self.assertEqual(entry.find("MUSICAL_KEY").get("VALUE"), "12")
            self.assertEqual(entry.find("TEMPO").get("BPM"), "127.000000")
            hot = [cue for cue in entry.findall("CUE_V2") if cue.get("HOTCUE") != "-1"]
            self.assertEqual([cue.get("NAME") for cue in hot], ["Energy 6", "Energy 7"])
            self.assertEqual(hot[0].get("START"), "255.000000")
            self.assertEqual(hot[1].get("HOTCUE"), "1")
            grid = [cue for cue in entry.findall("CUE_V2") if cue.get("HOTCUE") == "-1"]
            self.assertEqual(grid[0].get("NAME"), "AutoGrid")
            folder = [
                node
                for node in ET.parse(nml).getroot().iter("NODE")
                if node.get("NAME") == "MIXED IN KEY"
            ][0]
            playlist = [
                node
                for node in folder.iter("NODE")
                if node.get("NAME") == "Spiritual House"
            ][0]
            primary = playlist.find("./PLAYLIST/ENTRY/PRIMARYKEY")
            self.assertEqual(primary.get("KEY"), key)
