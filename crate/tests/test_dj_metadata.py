"""dj_metadata parsing."""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from ix_crate.dj_metadata import parse_nml_entry, parse_xml_track


class TestDjMetadata(unittest.TestCase):
    def test_parse_nml_entry(self) -> None:
        entry = ET.fromstring(
            """<ENTRY TITLE="A1 Kick" ARTIST="Native Instruments">
            <ALBUM TITLE="Electric Vice - Traktor Remix Set"/>
            <INFO GENRE="Techno" KEY="9A" PLAYTIME="2"/>
            <TEMPO BPM="122.000000"/>
            </ENTRY>"""
        )
        meta = parse_nml_entry(entry)
        self.assertEqual(meta.title, "A1 Kick")
        self.assertEqual(meta.artist, "Native Instruments")
        self.assertEqual(meta.album, "Electric Vice - Traktor Remix Set")
        self.assertEqual(meta.bpm, "122.000000")
        self.assertEqual(meta.key, "9A")

    def test_parse_xml_track(self) -> None:
        track = ET.fromstring(
            '<TRACK Name="Test" Artist="A" Album="B" Genre="House" '
            'AverageBpm="128.00" Tonality="8A" TotalTime="180"/>'
        )
        meta = parse_xml_track(track)
        self.assertEqual(meta.title, "Test")
        self.assertEqual(meta.bpm, "128.00")
        self.assertEqual(meta.key, "8A")


if __name__ == "__main__":
    unittest.main()
