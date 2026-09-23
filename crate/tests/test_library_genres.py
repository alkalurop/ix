from __future__ import annotations

import unittest
from pathlib import Path

from ix_crate.crates import PathIndex
from ix_crate.library_genres import (
    LibraryTrack,
    build_catalog,
    library_genre_plans,
    match_library_genre,
)


class LibraryGenreTests(unittest.TestCase):
    def test_mix_title_uses_the_artist_row(self) -> None:
        catalog = build_catalog(
            [
                LibraryTrack("Radiohead", "Example (Original Mix)", "Rock"),
                LibraryTrack("Other", "Example", "House"),
            ]
        )
        self.assertEqual(match_library_genre("Radiohead", "Example", catalog), "Rock")
        self.assertEqual(match_library_genre("", "Example", catalog), "")

    def test_genre_playlist_folder(self) -> None:
        path = Path("/tmp/example.m4a")
        catalog = build_catalog([LibraryTrack("Radiohead", "Example", "Rock", path)])
        plans = library_genre_plans(catalog, dest="nml", index=PathIndex())
        self.assertEqual(plans[0].name, "Rock")
        self.assertEqual(plans[0].folder, ("GENRES",))
        self.assertEqual(plans[0].missing[0].title, "Example")
