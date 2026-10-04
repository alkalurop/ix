"""rekordbox_sample_crate + traktor_remix_crate planning."""
from __future__ import annotations

import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from ix_crate.rekordbox_sample_crate import (
    plan_archive_moves,
    plan_sample_crate,
    sample_title_from_name,
)
from ix_crate.traktor_remix_crate import index_remix_sets_from_nml, remix_playlist_name


class TestSampleTitle(unittest.TestCase):
    def test_capture_suffix_stripped(self) -> None:
        self.assertEqual(
            sample_title_from_name("All This Is For A Jump vocals_capture.wav"),
            "All This Is For A Jump vocals",
        )


class TestArchiveMoves(unittest.TestCase):
    def test_move_when_saved_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cap = Path(tmp) / "Capture"
            saved = Path(tmp) / "Saved"
            cap.mkdir()
            src = cap / "kick_capture.wav"
            src.write_bytes(b"RIFF" + b"\0" * 40)
            actions = plan_archive_moves(capture=cap, saved=saved)
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].action, "move")

    def test_dedupe_same_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cap = Path(tmp) / "Capture"
            saved = Path(tmp) / "Saved"
            cap.mkdir()
            saved.mkdir()
            payload = b"RIFF" + b"\0" * 40
            (saved / "kick_capture.wav").write_bytes(payload)
            (cap / "kick_capture.wav").write_bytes(payload)
            actions = plan_archive_moves(capture=cap, saved=saved)
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].action, "remove_duplicate")

    def test_conflict_different_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cap = Path(tmp) / "Capture"
            saved = Path(tmp) / "Saved"
            cap.mkdir()
            saved.mkdir()
            (saved / "kick_capture.wav").write_bytes(b"a" * 64)
            (cap / "kick_capture.wav").write_bytes(b"b" * 64)
            actions = plan_archive_moves(capture=cap, saved=saved)
            self.assertEqual(actions[0].action, "skip_conflict")


class TestRemixSets(unittest.TestCase):
    def test_playlist_name_from_album(self) -> None:
        self.assertEqual(
            remix_playlist_name("Electric Vice - Traktor Remix Set"),
            "Electric Vice",
        )

    def test_index_from_minimal_nml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nml = Path(tmp) / "collection.nml"
            nml.write_text(
                """<?xml version="1.0"?>
<NML VERSION="19">
<COLLECTION ENTRIES="1">
<ENTRY TITLE="A1 Kick" ARTIST="Test">
<LOCATION DIR="/:tmp/:sets/:My Pack - Traktor Remix Set/:" FILE="A1.wav"
 VOLUME="Macintosh HD" VOLUMEID="Macintosh HD"/>
<ALBUM TITLE="My Pack - Traktor Remix Set"/>
</ENTRY>
</COLLECTION>
<PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="0"/></NODE></PLAYLISTS>
</NML>""",
                encoding="utf-8",
            )
            wav = Path("/tmp/sets/My Pack - Traktor Remix Set/A1.wav")
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x" * 32)
            try:
                grouped = index_remix_sets_from_nml(nml)
                self.assertIn("My Pack", grouped)
                self.assertEqual(len(grouped["My Pack"]), 1)
            finally:
                shutil.rmtree(wav.parent, ignore_errors=True)


class TestSampleCratePlan(unittest.TestCase):
    def test_playlist_includes_pending_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cap = Path(tmp) / "Capture"
            saved = Path(tmp) / "Saved"
            cap.mkdir()
            (cap / "new_capture.wav").write_bytes(b"n" * 48)
            plan = plan_sample_crate(capture=cap, saved=saved)
            self.assertEqual(len(plan.archive), 1)
            self.assertEqual(len(plan.playlist_paths), 1)


if __name__ == "__main__":
    unittest.main()
