# ix crate

Identify and rehome untagged files under `~/Music/stems_audio`. Dry-run by default.

See `docs/crate.md`.

```bash
PYTHONPATH=crate python3 -m ix_crate unknown-album
PYTHONPATH=crate python3 -m ix_crate outliers
PYTHONPATH=crate python3 -m ix_crate mashups
PYTHONPATH=crate python3 -m ix_crate music-dupes
PYTHONPATH=crate python3 -m ix_crate music-dupes --execute
PYTHONPATH=crate python3 -m ix_crate music-repair
PYTHONPATH=crate python3 -m ix_crate music-repair --execute
PYTHONPATH=crate python3 -m ix_crate music-fix --playlist Fix
PYTHONPATH=crate python3 -m ix_crate music-fix --playlist Fix --execute
PYTHONPATH=crate python3 -m ix_crate music-fix --library-va
PYTHONPATH=crate python3 -m ix_crate music-fix --library-va --execute
PYTHONPATH=crate python3 -m ix_crate music-organize
PYTHONPATH=crate python3 -m ix_crate music-organize --playlist Fix
PYTHONPATH=crate python3 -m ix_crate music-organize --execute
PYTHONPATH=crate python3 -m ix_crate music-playlist
PYTHONPATH=crate python3 -m ix_crate music-playlist --execute
PYTHONPATH=crate python3 -m ix_crate music-genre --xml
PYTHONPATH=crate python3 -m ix_crate music-genre --xml --execute
PYTHONPATH=crate python3 -m ix_crate stemit --playlist "Never Forget 50th v01"
PYTHONPATH=crate python3 -m ix_crate stemit --playlist "Never Forget 50th v01" --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-role-titles
PYTHONPATH=crate python3 -m ix_crate stemit --fix-role-titles --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-role-titles --nml --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-industry-artists
PYTHONPATH=crate python3 -m ix_crate stemit --fix-industry-artists --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-titles
PYTHONPATH=crate python3 -m ix_crate stemit --fix-titles --execute
PYTHONPATH=crate python3 -m ix_crate stemit --drop-copies
PYTHONPATH=crate python3 -m ix_crate stemit --drop-copies --execute
PYTHONPATH=crate python3 -m ix_crate stemit --genres
PYTHONPATH=crate python3 -m ix_crate stemit --genres --execute
PYTHONPATH=crate python3 -m ix_crate stemit --dedupe
PYTHONPATH=crate python3 -m ix_crate stemit --dedupe --execute
PYTHONPATH=crate python3 -m ix_crate traktor-nml
PYTHONPATH=crate python3 -m ix_crate traktor-nml --execute
PYTHONPATH=crate python3 -m ix_crate crates --from music --to xml --playlist "Never Forget 50th v01"
PYTHONPATH=crate python3 -m ix_crate crates --from music --to xml --playlist "Never Forget 50th v01" --execute
PYTHONPATH=crate python3 -m ix_crate crates --from nml --to xml --playlist "Humid chills"
PYTHONPATH=crate python3 -m ix_crate favorites
PYTHONPATH=crate python3 -m ix_crate favorites --execute
PYTHONPATH=crate python3 -m ix_crate favorites --execute --playlists
PYTHONPATH=crate python3 -m ix_crate favorites --execute --snapshot
PYTHONPATH=crate python3 -m ix_crate crater
PYTHONPATH=crate python3 -m ix_crate crater --execute
PYTHONPATH=crate python3 -m ix_crate mixed-in-crate
PYTHONPATH=crate python3 -m ix_crate mixed-in-crate --execute
docs/examples/library-hygiene.sh
docs/examples/stemit-crater.sh
```

**CRATER** is the daily celestial crate pass (`docs/crate.md`). **BABYLON** (`docs/examples/babylon.sh` → `ix_crate babylon --execute`) is hygiene + optional STEMIT batches + CRATER with stems **RunLogger** (phase JSON under `stems/log/`, copy beside `babylon-*.log`). **Library hygiene** (`docs/examples/library-hygiene.sh`) runs the same music/decks steps without the orchestrated progress wrapper — use `HYGIENE=1` on `stemit-crater.sh` to chain before STEMIT. **mixed-in-crate** mirrors Mixed In Key user playlists into `MIXED IN KEY` (included in CRATER); Rekordbox still needs **`<>`** on the xml crate after writes.

Leftovers after lookup go to `Compilations/Mashups/Miscellaneous/`. Dry-run is the default; pass `--execute` to move.

`music-dupes` finds Music.app Songs rows that share one file on disk (Show in Finder opens the same path). Dry-run is the default. `--execute` deletes the extra *library rows* only — the audio stays. Uses the stems factory Aqua HUD (`py.utils.progress`). `--no-gui` stays in the terminal.

`music-repair` relinks Songs rows with no file (Locate / !) to a unique match on disk, then fills empty artist/album/title (crate cascade) and empty genre (iTunes only). It does not move Media.localized. `--no-gui` skips the Aqua HUD (batch scripts, Python without python-tk).

`music-fix` fills artist / album / title / genre on a Music.app playlist (default `Fix`). Default is aggressive: AcoustID fingerprints, Shazam, duration-matched iTunes/Deezer. Unidentified leftovers are skipped (not labeled Various Artists). `--library-va` targets library rows whose artist is Various Artists. `--strict` is the old dual-catalog path. Does not rename files. Screenshot-driven one-album Discogs (not a crate command): `docs/crate.md`.

`music-organize` names and files `Media.localized` from Music.app metadata (Artist / Album / `NN Title`). `Track 01` is renamed only when Songs already has a real title. Stays in the artist-root or `Music/` tree — never hoists. Keep **Keep Music Media folder organized** Off. Writes a remap report for music_migration. Dry-run default.

`music-playlist` refills a Music.app playlist from `~/Downloads` filenames (Beatport ids + `Artist - Title`). Matches existing Songs rows. Does not copy Downloads in. After a reorg empties a playlist, run this instead of dragging files again.

`crates` copies playlist **membership** between Music.app, Traktor NML, and `rekordbox.xml`. It does not rewrite cues, energy, comments, or beatgrids. Match by file path or hardlink. Missing files that exist on disk get a Location row so empty crates (DJ Sets) fill; skip `.m4p`. Unmatched missing/DRM stay skipped. Music → xml lands under `MUSIC/`; NML → xml under `TRAKTOR/`. STEMIT stays `stemit --genres`. Cues on new tracks: DJCU2 / in-app Analyze. Quit Rekordbox for `--to xml`. Dry-run default.

`favorites` records Traktor + Rekordbox plays (genre/BPM/energy/vibe) into local `configs/favorites.json` (gitignored) and compact `play-patterns.json` for the local LLM. `Played` is the 100 most recent. `--playlists` writes `Not Played But Should` (neglected / random / favorites). `--snapshot` is the quarterly git copy. Dry-run default.

**STEMIT** hardlinks a Music.app playlist into `~/Music/stems_audio/Artist/Album/` and runs the [stems](https://github.com/ixamal/stems) factory (`py.exec.separate`, Aqua HUD via `py.utils.progress`). Never writes Apple Music. Never stems Acapella. Skip existing `{name}.stem.m4a`. Dry-run default; `--execute` links then launches the factory. `--fix-role-titles` fills Title = vocals from the sibling mix / folder onto owned `.mp3` / `.m4a` (never `.wav`). Quit Traktor, then `--nml --execute`. `--fix-industry-artists` fills artist on Industry Stems WAV packs from the crate (then iTunes leftovers), patches Traktor NML, and keeps one STEMIT playlist row per identity. `--fix-titles` pretties Beatport catalog TITLEs in NML (`12432715_Together_We_Fall_…` → Together We Fall) and drops Google Drive shortcut rows. `--genres` cleans `EDM, …` / `House, …` on STEMIT NML rows (`music_genre.clean_genre`) and rebuilds `STEMIT/Genres/<Genre>/{Mixes,Stems,Acapellas,Instrumentals}` from crate keepers. `--genres --execute` writes that tree into `rekordbox.xml` (NML stays unless `--nml`). Re-run anytime after adds or copies. `--dedupe` deletes confirmed copies from Finder and rebuilds crates (unique mashups and Industry Stems WAV packs stay). Rekordbox follows via DJCU2 (`docs/djcu2.md`), not a rekordbox.xml rewrite. Specimens: `docs/examples/stemit-industry-artists.py`, `docs/examples/music-set-industry-artist.applescript`.

`traktor-nml` drops duplicate playlist PRIMARYKEYs, copies sibling COVERARTID when the Coverart cache file exists, and drops Finder ``(2)`` copies under ``stems_audio`` when mutagen length matches and decoded audio is identical. Then it rewrites STEMIT Mixes / Stems / Acapellas / Instrumentals from disk so role files are not listed in Mixes. Mix / stem / vocals / instrumental are four files, not copies. Quit Traktor first. Dry-run default.
