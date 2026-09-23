from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ix_crate.favorites import (
    PLAYED_LIMIT,
    PlayRow,
    assert_public,
    harvest_nml,
    harvest_xml,
    parse_energy,
    play_fingerprint,
    recent_played,
    record,
    skip_role,
    slim_for_git,
    snapshot_quarterly,
    stars,
    suggest_playlists,
    write_favorites,
)
from ix_crate.stems_playlists import _rb_location, _traktor_dir_file


class HelpersTests(unittest.TestCase):
    def test_skip_stems_and_vocals(self) -> None:
        self.assertTrue(skip_role("Honey.stem.m4a"))
        self.assertTrue(skip_role("Honey - vocals.wav"))
        self.assertFalse(skip_role("Honey (Original Mix).m4a"))
        self.assertFalse(skip_role("What Planet You On (Bodyrox Vocal Club Mix).mp3"))

    def test_stars(self) -> None:
        self.assertEqual(stars("0"), 0)
        self.assertEqual(stars("255"), 5)
        self.assertEqual(stars("51"), 1)
        self.assertEqual(stars("4"), 4)

    def test_parse_energy_and_ignore_hex_comment(self) -> None:
        self.assertEqual(parse_energy("06A - Energy 5"), 5)
        self.assertEqual(parse_energy(" 0000139D 0000167A 00009402"), 0)

    def test_recent_played_caps_at_100(self) -> None:
        rows = [
            PlayRow(artist="A", title=f"T{i}", plays={"traktor": 1}, last_played=f"2026-01-{i:02d}")
            for i in range(1, 28)
        ]
        rows += [
            PlayRow(artist="B", title=f"U{i}", plays={"traktor": 1}, last_played=f"2025-12-{i:02d}")
            for i in range(1, 80)
        ]
        picked = recent_played(rows, PLAYED_LIMIT)
        self.assertEqual(len(picked), 100)
        self.assertEqual(picked[0].title, "T27")


class HarvestTests(unittest.TestCase):
    def test_nml_and_xml_public_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            mix = Path(tmp) / "Honey (Original Mix).m4a"
            stem = Path(tmp) / "Honey.stem.m4a"
            mix.write_bytes(b"a")
            stem.write_bytes(b"b")
            directory, file_attr = _traktor_dir_file(mix)
            stem_dir, stem_file = _traktor_dir_file(stem)
            nml = Path(tmp) / "collection.nml"
            nml.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<NML VERSION=\"20\"><COLLECTION ENTRIES=\"2\">"
                '<ENTRY TITLE="Honey (Original Mix)" ARTIST="Moby">'
                f'<LOCATION DIR="{directory}" FILE="{file_attr}" VOLUME="Macintosh HD"/>'
                '<INFO PLAYCOUNT="3" PLAYTIME="185" LAST_PLAYED="2023/4/23" '
                'IMPORT_DATE="2019/12/30" RANKING="204" GENRE="EDM, House, Deep" '
                'KEY="8A" COMMENT="08A - Energy 6"/>'
                '<TEMPO BPM="124.00"/>'
                "</ENTRY>"
                '<ENTRY TITLE="Honey" ARTIST="Moby">'
                f'<LOCATION DIR="{stem_dir}" FILE="{stem_file}" VOLUME="Macintosh HD"/>'
                '<INFO PLAYCOUNT="9" PLAYTIME="185"/>'
                "</ENTRY></COLLECTION></NML>",
                encoding="utf-8",
            )
            xml = Path(tmp) / "rekordbox.xml"
            xml.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="1">'
                '<TRACK TrackID="7" Name="Honey (Original Mix)" Artist="Moby" '
                'PlayCount="1" TotalTime="185" Rating="51" DateAdded="2019-12-29" '
                'AverageBpm="124.00" Genre="Deep House" Comments="08A - Energy 6" '
                f'Location="{_rb_location(mix)}"/>'
                "</COLLECTION></DJ_PLAYLISTS>",
                encoding="utf-8",
            )
            payload = record(nml=nml, xml=xml, dest=Path(tmp) / "favorites.json", merge=False)
            assert_public(payload)
            blob = json.dumps(payload)
            self.assertNotIn("/Users/", blob)
            self.assertNotIn("file://", blob)
            self.assertEqual(payload["stats"]["played"], 1)
            self.assertEqual(payload["stats"]["not_played"], 0)
            row = payload["played"][0]
            self.assertEqual(row["artist"], "Moby")
            self.assertEqual(row["title"], "Honey (Original Mix)")
            self.assertEqual(row["play_count"], 4)
            self.assertEqual(row["plays"]["traktor"], 3)
            self.assertEqual(row["plays"]["rekordbox"], 1)
            self.assertEqual(row["last_played"], "2023-04-23")
            self.assertTrue(row["favorite"])
            self.assertEqual(row["genre"], "Deep House")
            self.assertEqual(row["energy"], 6)
            self.assertEqual(row["bpm"], 124.0)
            self.assertIn("Deep House|122-128|e6|", row["vibe"])
            self.assertEqual(len(harvest_nml(nml)), 1)
            self.assertEqual(len(harvest_xml(xml)), 1)

    def test_write_rejects_path(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "favorites.json"
            with self.assertRaises(ValueError):
                write_favorites({"played": [{"artist": "/Users/secret", "title": "x"}]}, dest)

    def test_suggest_three_trees_and_stable_fingerprint(self) -> None:
        played = [
            PlayRow(artist="A", title="One", plays={"traktor": 2}, genre="Deep House", bpm=124, energy=6, last_played="2026-09-08"),
            PlayRow(artist="B", title="Two", plays={"traktor": 1}, genre="Techno", bpm=130, energy=7, last_played="2026-09-01", rating=4),
        ]
        rest = [
            PlayRow(artist="C", title="Dust", genre="Deep House", bpm=125, energy=6, first_seen="2019-01-01"),
            PlayRow(artist="D", title="Rand1", genre="Ambient", bpm=90),
            PlayRow(artist="E", title="Rand2", genre="Ambient", bpm=88),
            PlayRow(artist="F", title="Close", genre="Techno", bpm=131, energy=7),
        ]
        rows = {f"{r.artist}\t{r.title}": r for r in played + rest}
        first = suggest_playlists(rows, "seed")
        again = suggest_playlists(rows, "seed")
        self.assertEqual([r.title for r in first["Random"]], [r.title for r in again["Random"]])
        self.assertTrue(first["Neglected genres"])
        self.assertTrue(first["Favorites"])
        self.assertEqual(first["Acapella"], [])
        self.assertEqual(play_fingerprint(played), play_fingerprint(played))

    def test_acapella_crate_keeps_them_out_of_random(self) -> None:
        rows = {
            "a\tCap": PlayRow(artist="A", title="Cap", genre="Acapella"),
            "b\tMix": PlayRow(artist="B", title="Mix", genre="House"),
        }
        suggestions = suggest_playlists(rows, "seed")
        self.assertEqual([row.title for row in suggestions["Acapella"]], ["Cap"])
        self.assertNotIn("Cap", [row.title for row in suggestions["Random"]])

    def test_quarterly_snapshot_drops_not_played(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            favorites = folder / "favorites.json"
            patterns = folder / "play-patterns.json"
            write_favorites(
                {
                    "played": [{"artist": "A", "title": "One", "play_count": 2}],
                    "not_played": [{"artist": "B", "title": "Dust"}] * 3,
                    "stats": {"played": 1, "not_played": 3},
                },
                favorites,
            )
            patterns.write_text('{"fingerprint":"abc"}\n', encoding="utf-8")
            written = snapshot_quarterly(favorites, patterns, folder / "quarterly")
            slim = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(slim["not_played"], [])
            self.assertEqual(len(slim["played"]), 1)
            self.assertEqual(slim_for_git({"not_played": [1], "played": [2]})["not_played"], [])


class CliTests(unittest.TestCase):
    def test_help(self) -> None:
        from ix_crate.__main__ import main

        buf = io.StringIO()
        with patch("sys.stdout", buf), self.assertRaises(SystemExit) as ctx:
            main(["favorites", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("--execute", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
