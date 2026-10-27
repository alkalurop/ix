"""Specimen: where Industry Stems artist + STEMIT crate dedupe went down.

Do not run this against a live library. The crate command is:

    cd ~/github/ixamal/ix
    PYTHONPATH=crate python3 -m ix_crate stemit --fix-industry-artists
    PYTHONPATH=crate python3 -m ix_crate stemit --fix-industry-artists --execute

Industry Stems packs are ``stems_audio/IndustryStems/NN_Title/{drums,bass,other,vocals}.wav``.
Traktor showed artist = IndustryStems. The title is the folder (strip ``101_``).
The artist is already in the crate (NIN, FLA, Queen, Puscifer, …) or in the
iTunes/Deezer/MusicBrainz cascade. Never mutagen-write the WAVs. Never Discogs.

STEMIT Stems dupes were the same cut under Artist/Album *and* Compilations/Mashups
or Stems Spring Blossoms. Mix / stem / vocals / instrumental stay four files.
``stemit --dedupe`` then deletes confirmed copies from Finder (Mashups dumps,
Unknown Album, same-audio twins). Unique mashups and Industry Stems WAV packs
stay. Extra files do not stay on disk once audio or dump-family matches.

Music.app does not re-read tags. If a Songs row still says Industry Stems, use
``music-set-industry-artist.applescript`` against the TSV in
``~/local_tools/crate/reports/`` (off git). Quit Traktor before --execute.
Rekordbox folders follow ``stemit --genres``. This specimen does not rewrite rekordbox.xml.
"""

from __future__ import annotations

# Live implementation: crate/ix_crate/industry_stems.py
# AppleScript specimen: docs/examples/music-set-industry-artist.applescript

CASCADE = (
    "folder title (strip NN_)",
    "stems_audio Artist/Album crate match",
    "filename Artist - Title",
    "iTunes / Deezer / MusicBrainz (leftovers only)",
    "Traktor NML ARTIST/TITLE (never WAV tags)",
    "STEMIT playlist: one row per crate identity",
)
