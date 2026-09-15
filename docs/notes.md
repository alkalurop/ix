# Working notes (do not execute from this file)

Parking lot for crate, tagging, and hardware ideas. Ordered checklist: `docs/TODO.md`. Agents: read both, then stop unless David asks to act. Off-repo tools and library paths stay off git.

Last update: 2026-09-15. **Alkalurop bridge:** public ixamal repos mirrored into [github.com/alkalurop](https://github.com/alkalurop) (org profile is the main bridge). Monthly 15th 15:00 local. `favorites` still recording (TODO 41); reviews **2026-09-16** / **2026-10-09**. Hardware next: Maschine A/B/C (11a), FLX10 CH2 digital (40). Floor **10** parked. Toolkit: README. How/why: `docs/crate.md`.

## Alkalurop org bridge (2026-09-15)

Org [alkalurop](https://github.com/alkalurop) is the main bridge (profile: [alkalurop/.github](https://github.com/alkalurop/.github)). First mirror of current ixamal `main`:

| alkalurop | matches ixamal `main` |
| --- | --- |
| [ix](https://github.com/alkalurop/ix) | `6ec577f` |
| [stems](https://github.com/alkalurop/stems) | `40069a1` |
| [ix_bangers](https://github.com/alkalurop/ix_bangers) | `f257be1` |
| [blackhole](https://github.com/alkalurop/blackhole) | `17700c3` |
| [music_migration](https://github.com/alkalurop/music_migration) | `0a4735f` |

`github.com/alkalurop/ix` used to 301 to ixamal/ix (old transfer redirect). Re-created the org repo so the name lives on the org. Script: `docs/examples/alkalurop-bridge.sh`. Plist: `ai.ixamal.alkalurop-bridge` — 15th 15:00 local. No tokens in git.

## Crate status

- ATGR installed (ReCK, DJCU2, Mixed in Key).
- [ixamal/stems](https://github.com/ixamal/stems) processed `~/Music/stems_audio`.
- Identity tool lives in this repo: `crate/`, `docs/crate.md`.
- Cascade: filename → tags → iTunes/Deezer → MusicBrainz → Ollama `qwen2.5:7b` on `127.0.0.1:11434` → `Compilations/Mashups/Miscellaneous/`.
- Mashups: `Compilations/Mashups/{Artist}/`. Leftover clips and one-word names: `Miscellaneous`.
- Ollama music ID uses `qwen2.5:7b` (pulled 2026-08-30). `qwen2.5-coder:7b` stays off this job.

Reports (off git): `~/local_tools/crate/reports/`. Cache: `~/local_tools/crate/lookup-cache.json`.

Traktor (2026-08-30): NML remapped, then [ATGR DJCU2](https://atgr.nl/) converted the collection to Rekordbox. It works. ix does not reimplement that bridge. Snapshots: `databases/` (off git). Steps: `docs/djcu2.md`.

### Milestone (2026-09-08)

Rekordbox + Traktor are fun-playable from the path-stable crate. `music-genre --xml` cleaned **10,457** sidecar Genre rows. `crates --all` wrote **107** Music.app playlists (House + Origin Stories + three root crates). Rekordbox imported MUSIC into collection. Import skipped 21 files (16 dead paths, 4 `.m4p`). Cues stayed on collection rows.

### MUSIC ingest (2026-09-10)

Empty Rekordbox MUSIC crates were Music.app lists whose files were never in the sidecar collection (DJ Sets **0** vs **236** file tracks). `crates` now writes a Location row for missing files that exist on disk. Never a stub without a file. Skip `.m4p`.

```bash
PYTHONPATH=crate python3 -m ix_crate stemit --fix-industry-artists --execute
PYTHONPATH=crate python3 -m ix_crate crates --from music --to nml --all --execute
PYTHONPATH=crate python3 -m ix_crate crates --from music --to xml --all --execute
```

**Benchmark (this Mac, 2026-09-10):**
- Industry packs **209/209**. Sources: crate-exact **201**, crate-prefix **4**, MusicBrainz **2**, Shazam **2**. NML ARTIST leftover **28 → 0**. xml ARTIST **968 → 0** (831 live files + 133 dead-path ghosts, artist from pack folder). Music.app already **0**. WAV tags not written.
- `crates --all` Music → NML **111** playlists (~58 s dump+write). Music → xml **111** (~41 s after NML dump cached in the same session shape).
- **DJ Sets 0 → 230** (6 Apple DRM skipped). MUSIC empties **28 → 5** (`Feel it`, `Internet Songs`, `Kum Baja`, `Ringtones`, extra Social Network list — empty or DRM-only in Music).
- Played / NPBS Favorites / Neglected / Random now under **MUSIC/** on both decks.
- New collection rows have no grid until Rekordbox Analyze (or DJCU2 later). Reload xml `<>`. Don't ask again + **No** on tag overwrite.

### Resume next

1. Reload Rekordbox xml (`<>`) and reopen Traktor if needed — analyze new DJ Sets rows. First glance 2026-09-10 was good.
2. Leftover same-title copies in STEMIT. Alternative stems 1–3 (TODO 17) unless David names another playlist.
3. **11 / 11a** when David opens a blackhole session: 16ch, then Traktor A/B/C → Maschine sampler → S88.
4. **40** Investigate Traktor → FLX10 Channel 2 as a digital feed (today: analog master).
5. Floor **10** parked until David asks.
6. **41** Played / Not Played But Should — harvest + patterns live; crates via `--playlists`. Load the 5am LaunchAgent only when David asks. Quarterly `--snapshot` into git, not nightly. Reviews **2026-09-16**, **2026-10-09**.
7. Items 5 / 5b / 6 stay omitted. Do not Discogs-blast. Targeted one-album Discogs from a screenshot is OK (TODO 22 / `docs/crate.md`).

```bash
PYTHONPATH=crate python3 -m ix_crate unknown-album
PYTHONPATH=crate python3 -m ix_crate outliers
PYTHONPATH=crate python3 -m ix_crate mashups
PYTHONPATH=crate python3 -m ix_crate music-dupes
PYTHONPATH=crate python3 -m ix_crate music-dupes --execute
PYTHONPATH=crate python3 -m ix_crate music-repair
PYTHONPATH=crate python3 -m ix_crate music-repair --execute
PYTHONPATH=crate python3 -m ix_crate music-genre
PYTHONPATH=crate python3 -m ix_crate music-replicants
PYTHONPATH=crate python3 -m ix_crate music-cull
PYTHONPATH=crate python3 -m ix_crate music-organize
PYTHONPATH=crate python3 -m ix_crate music-organize --playlist Fix
PYTHONPATH=crate python3 -m ix_crate music-organize --execute
PYTHONPATH=crate python3 -m ix_crate music-playlist
PYTHONPATH=crate python3 -m ix_crate music-playlist --execute
PYTHONPATH=crate python3 -m ix_crate music-genre
PYTHONPATH=crate python3 -m ix_crate music-genre --xml
PYTHONPATH=crate python3 -m ix_crate riff-repair
PYTHONPATH=crate python3 -m ix_crate music-fix --playlist Fix
PYTHONPATH=crate python3 -m ix_crate music-fix --playlist Fix --execute
PYTHONPATH=crate python3 -m ix_crate stemit --playlist "Never Forget 50th v01"
PYTHONPATH=crate python3 -m ix_crate stemit --playlist "Never Forget 50th v01" --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-role-titles
PYTHONPATH=crate python3 -m ix_crate stemit --fix-role-titles --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-role-titles --nml --execute
PYTHONPATH=crate python3 -m ix_crate stemit --fix-industry-artists
PYTHONPATH=crate python3 -m ix_crate stemit --fix-titles
PYTHONPATH=crate python3 -m ix_crate stemit --drop-copies
PYTHONPATH=crate python3 -m ix_crate stemit --genres
PYTHONPATH=crate python3 -m ix_crate stemit --dedupe
PYTHONPATH=crate python3 -m ix_crate stemit --sync-playlists
PYTHONPATH=crate python3 -m ix_crate crates --from music --to xml --playlist "Never Forget 50th v01"
PYTHONPATH=crate python3 -m ix_crate crates --from music --to xml --all
PYTHONPATH=crate python3 -m ix_crate crates --from nml --to xml --playlist "Humid chills"
PYTHONPATH=crate python3 -m ix_crate favorites
PYTHONPATH=crate python3 -m ix_crate favorites --execute
PYTHONPATH=crate python3 -m ix_crate favorites --execute --playlists
PYTHONPATH=crate python3 -m ix_crate favorites --execute --snapshot
```

## Tagging

Path-stable crate done 2026-08-30. Accapella + `EDM, …` genre pass done 2026-08-30 (files + Music.app AppleScript). Step log: `docs/onetagger.md`.

1. **OneTagger** 1.7.0 Beatport is dead (API v4). Discogs is unsafe for the old Apple `EDM, …` compounds (flattened to Electronic; one compilation → Hip Hop).
2. **TODO 5 omitted (2026-09-01).** Not viable on this Mac. David is happy enough with the TODO 4 catalog to play in Rekordbox. Do not compile community PRs unless he asks.
    - [OneTagger 1.7.0](https://github.com/Marekkon5/onetagger/releases/tag/1.7.0) — last official Mac release, 2023-08-03. Beatport scrape in that build is dead.
    - [Beatport API v4](https://api.beatport.com/v4/docs/) — current catalog API (OAuth). 1.7.0 does not speak it.
    - [Issue #486](https://github.com/Marekkon5/onetagger/issues/486) — Beatport/Traxsource/Juno break after the v3→v4 cut.
    - [Issue #518](https://github.com/Marekkon5/onetagger/issues/518) / [#520](https://github.com/Marekkon5/onetagger/issues/520) — `__NEXT_DATA__` scrape gone.
    - [PR #526](https://github.com/Marekkon5/onetagger/pull/526) (rosgr100) — v4 OAuth + catalog search. Open since 2026-05, last activity 2026-06, **not merged**. Linux CLI testers say it works. No official Mac asset.
    - [PR #523](https://github.com/Marekkon5/onetagger/pull/523) — earlier Beatport v4 search attempt after `__NEXT_DATA__` removal.
2a. Music.app genre is the library DB, not the file. After file writes, AppleScript `set genre` (one track at a time). Specimen: `docs/examples/music-set-genre.applescript` (do not run). Sync Library is Off — keep it off for the DJ crate. Copy-on-add is On. **Keep Music Media folder organized** is Off — `music-organize` is the mover, so the artist-root crate is not hoisted into `Music/`. New files land in `Media.localized/Music/Artist/Album/`; the existing crate stays at `Media.localized/Artist/`. Never recreate `Media.localized/Music` as a symlink to `.` (breaks drag-and-drop). Details: `docs/crate.md`.
2b. **TODO 5b omitted (2026-09-01).** Same blocker as 5: embed-while-processing was store lookups (Beatport / Traxsource / Discogs). Those stores are not viable here. If this ever reopens: owned `.mp3` / `.wav` / `.m4a` only; never `.m4p`; never mutagen `save()` on `.stem.m4a` (strips NI stem atom); sidecar `{name}.stem.json` beside the file, not in git.
3. Never overwrite ReCK/MiK fields: Camelot/key, BPM, comments, cues.
4. **TODO 6 omitted (2026-09-01).** Ollama (`qwen2.5:7b` on `127.0.0.1:11434`) was reviewer-after-stores, not a catalog. 5 never runs, so 6 would invent genres. Reopen only if Rekordbox leftovers bother David: JSON/CSV proposals, human approve, allowlisted write. Never the coder.
5. Do not use `qwen2.5-coder:7b` as the musicologist. Crate ID already uses `qwen2.5:7b`.
6. **Beets** is not the library of record. If used at all: `copy: no`, `move: no`, `write: no`, DB under `~/local_tools/beets`. Default `beet import` copies files and would break DJCU2/ReCK/Music.app paths. Gemini’s `item.write()` plugin is rejected. Crate fingerprinting is AcoustID (`fpcalc`) plus Shazam (`shazamio`; optional `songrec`). `music-fix --library-va` writes tags in place and does not move Media.localized.

ix Floor stays live OSC (`/rekordbox/bpm`, `/fader`, `/beat_phase`). It does not convert libraries or write ID3.

## NI / Maschine (queued)

Crate is path-stable and playable (TODO 3 + 38). David queued **11a** 2026-09-08: sample Traktor **A / B / C into Maschine**. Execution lives in [ixamal/blackhole](https://github.com/ixamal/blackhole), not this repo. Dedicated session — do not wire during crate or Floor work.

Working rig (2026-08-22): S88 keys (Light Guide) into Komplete Kontrol or Maschine, down **BlackHole 2ch**, into Traktor Channel D, out the S8 fader. KK and Maschine share one D fader. Leave Maschine Input off BlackHole (loop). Leave S8 unchecked in Maschine MIDI. Close KK when Maschine needs the S88.

**Next session (blackhole, in this order):**

1. Port the working 2ch Channel D graph onto **BlackHole 16ch**. Prove tone, Traktor A, and S88-only-on-D still behave. Commit there only after this works.
2. Then tap Traktor **A/B/C into the Maschine sampler**, play pads on the **S88**. KK out — KK does not sample live decks. Ableton Link is clock, not audio. Open question: Internal Traktor may not offer three independent deck outs; 16ch alone does not invent them. Do not record the master into BlackHole while Channel D is up (feedback).
3. Convert Traktor / NI material to WAV or AIFF for Maschine + S88 only if file samples are needed. Off-repo under `~/local_tools`.
4. **Idea to try:** can **Traktor Kontrol S8** pads drive **S88** sample slots (Maschine / Komplete Kontrol S88)? MIDI/bridge after 1–2.

Keep converters and MIDI maps in `~/local_tools`, not in this public repo. Keep Rekordbox shut during the 16ch / sampler graph so FLX10 USB is not in the same fight.

## FLX10 Channel 2 + USB noise

Rekordbox **DDJ-FLX10 Channel 2** is analog from Traktor master out today. TODO **40**: see whether Traktor can feed CH2 digitally (USB audio / interface / Link) so that insert is not the analog master.

USB ground-loop / 5 V power hum on this rig: **iFi iDefender Max** (USB-C). Bought from [Bloom Audio](https://bloomaudio.com/) 2026-05-08, order **52738**. It sits on the USB path and strips host power so the interface is not sharing a dirty 5 V rail. David: it works pretty well. Leftover noise after that insert is why CH2 digital is on the list — do not rip the iDefender out while chasing 40. Note for anyone cloning the hall: try the iDefender Max before buying another mixer or a new interface.

## Parked in siblings (not this repo)

- [ixamal/blackhole](https://github.com/ixamal/blackhole) — 2ch Channel D works. Next: 16ch, then A/B/C → Maschine → S88.
- [ixamal/ix_bangers](https://github.com/ixamal/ix_bangers) — Bangers MCP catalog (stems, Music, Rekordbox, Traktor). Dry mode until David says commit. Not native Traktor.
- [ixamal/stems](https://github.com/ixamal/stems) — factory idle after the first `stems_audio` pass. Parked there: dump the crate to JSON + a spreadsheet webpage. Not now.

## Played / Not Played But Should (TODO 41)

```bash
PYTHONPATH=crate python3 -m ix_crate favorites
PYTHONPATH=crate python3 -m ix_crate favorites --execute
PYTHONPATH=crate python3 -m ix_crate favorites --execute --playlists
PYTHONPATH=crate python3 -m ix_crate favorites --execute --snapshot
```

**Crates:** stable names. `Played` is the **100 most recent** (`last_played`). `Not Played But Should` has three subcrates of **12** each — neglected genres (genres you play that still have sitting tracks), random, favorites-match (genre + BPM ±6 + energy ±1). Skip playlist writes when the play fingerprint is unchanged (no new decks). Full 22k not-played stays in JSON only.

**Patterns for the local LLM:** `configs/play-patterns.json` — genre / BPM band / energy / vibe histograms from played mixes. Vibe is `{genre}|{bpm-band}|e{energy}|{key}`, from tags (MiK `06A - Energy 5`), not invented. Ollama stays on `127.0.0.1:11434`. Do not farm this to the cloud.

**Git:** `configs/favorites.json` and `play-patterns.json` are gitignored. Once a quarter: `favorites --execute --snapshot` → `configs/quarterly/favorites-YYYYQn.json` (played + stats, no 22k sitting list) + `play-patterns-YYYYQn.json`, then commit those two. Not nightly.

**Nightly 5am:** LaunchAgent example `docs/examples/ai.ixamal.crate-favorites.plist` + `favorites-nightly.sh`. Not loaded until David asks. Skips NML/XML if Traktor/Rekordbox are open.

**When the LLM gets its own repo:** keep it in crate + `~/local_tools/ollama` until a quarterly review says it outgrew this tree — fine-tune weights, an eval set, or a pattern corpus that is a product. Then [ixamal](https://github.com/ixamal) (e.g. `crate-oracle`), still loopback-only, no collection paths. Quarterly is the right cadence; do not split early.

**Reviews booked:** week 1 **2026-09-16**, month 1 **2026-10-09**. Process: `docs/crate.md` (favorites). First quarterly draft in git: `configs/quarterly/*-2026Q3.json`.

First harvest 2026-09-09: **812** played, **22,266** not played, **9** star-rated, **162** with Energy comments.

## Do not do until asked

- Re-run DJCU2 on the whole library unless David asks.
- Run OneTagger Discogs against the whole library (wrong compilation matches; flattens to Electronic).
- Run OneTagger against Apple Music streams (`.m4p`).
- Turn on Music.app **Sync Library** on this DJ crate (still matches/replaces local files; not a hybrid keep-local mode).
- Convert NI/Traktor audio to WAV/AIFF.
- Wire BlackHole 16ch / Traktor A/B/C → Maschine (11 / 11a) except in a dedicated blackhole session.
- MIDI-map S8 pads to S88 samples.
- Run Bangers writes (dry catalog only; [ixamal/ix_bangers](https://github.com/ixamal/ix_bangers)).
- Re-run crate `--execute` on a live tree unless David asks.
- Run the embed-while-processing stamp (TODO 5b) on a live crate unless David asks.
