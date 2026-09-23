import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ix_crate.music_repair import RepairRow
from ix_crate.stemit import dest_mix, factory_env, plan_playlist, skip_reason


def _row(
    name: str,
    *,
    artist: str = "Chemars",
    album: str = "Jazz In The Park",
    genre: str = "Deep House",
    location: str = "",
) -> RepairRow:
    return RepairRow(
        persistent_id="PID",
        database_id=1,
        artist=artist,
        album=album,
        name=name,
        genre=genre,
        duration=180,
        location=location,
    )


class StemitPlanTests(unittest.TestCase):
    def test_dest_is_artist_album_filename(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "src" / "01 Jazz In The Park (Extended Club Mix).mp3"
            dest_root = Path(tmp) / "stems_audio"
            row = _row("Jazz In The Park (Extended Club Mix)", location=str(src))
            dest = dest_mix(row, stems_root=dest_root)
            self.assertEqual(
                dest,
                dest_root
                / "Chemars"
                / "Jazz In The Park"
                / "01 Jazz In The Park (Extended Club Mix).mp3",
            )

    def test_skips_acapella(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "Let It Go.mp3"
            src.write_bytes(b"x")
            row = _row("Let It Go", genre="Acapella", location=str(src))
            self.assertEqual(skip_reason(row, stems_root=Path(tmp) / "stems"), "acapella")

    def test_vocal_club_mix_is_not_acapella(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "What Planet You On (Bodyrox Vocal Club Mix).mp3"
            src.write_bytes(b"x")
            row = _row(
                "What Planet You On (Bodyrox Vocal Club Mix)",
                artist="Bodyrox, Luciana",
                album="What Planet You On",
                genre="House",
                location=str(src),
            )
            self.assertEqual(skip_reason(row, stems_root=Path(tmp) / "stems"), "")

    def test_skips_existing_stem(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "mix.mp3"
            src.write_bytes(b"x")
            dest_root = Path(tmp) / "stems_audio"
            row = _row("Jazz In The Park (Extended Club Mix)", location=str(src))
            dest = dest_mix(row, stems_root=dest_root)
            dest.parent.mkdir(parents=True)
            dest.with_name(f"{dest.stem}.stem.m4a").write_bytes(b"stem")
            self.assertEqual(skip_reason(row, stems_root=dest_root), "already has .stem.m4a")

    def test_skips_apple_drm(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "protected.m4a"
            src.write_bytes(b"ftypM4A " + b"drms" + b"\x00" * 16)
            row = _row("Wish Upon a Dog Star", location=str(src))
            self.assertEqual(skip_reason(row, stems_root=Path(tmp) / "stems"), "apple drm")

    def test_skips_m4p(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "stream.m4p"
            src.write_bytes(b"x")
            row = _row("Stream", location=str(src))
            self.assertEqual(skip_reason(row, stems_root=Path(tmp) / "stems"), "skip stem or m4p")

    def test_plan_uses_supplied_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "mix.mp3"
            src.write_bytes(b"x")
            rows = [
                _row("One", location=str(src)),
                _row("Two", location=str(src)),
                _row("Three", location=str(src)),
            ]
            payload = plan_playlist("genre:Rock", rows=rows[:2], stems_root=Path(tmp) / "stems")
            self.assertEqual(payload["playlist"], "genre:Rock")
            self.assertEqual(payload["tracks"], 2)
            self.assertEqual([job["name"] for job in payload["jobs"]], ["One", "Two"])

    def test_factory_env_puts_venv_bin_first(self) -> None:
        env = factory_env()
        first = Path(env["PATH"].split(os.pathsep)[0])
        self.assertEqual(first.name, "bin")
        self.assertEqual(first.parent.name, ".venv")
        self.assertTrue((first / "audio-separator").is_file())
