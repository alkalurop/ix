# ix

Primary planetary code base for machines and humans. This is Valhalla: Cursor, a local Ollama oracle, Unreal Engine 5, DCC, DAW, and DJ tools meet here. The destination is **Elysium**.

Public git: [github.com/ixamal/ix](https://github.com/ixamal/ix)

Mac clone path: `~/github/ixamal/ix`

**Vibe coding.** Cursor and Codex only. Git commits are David — no Cursor or Codex co-author trailers.

## Where we are

If you DJ, or you have been collecting longer than you have been DJing, you already know this mess. Twenty thousand files. Mix CDs tagged as the DJ who mixed them. iTunes calling everything `EDM, House`. The same record twice because Apple named the second copy `Track 1`. A USB drive that *was* the crate until you unplugged it and half of Songs grew a `!`. You cannot play what you cannot find. You cannot stem what has no name. You cannot migrate playlists if the path is a lie.

This week we stopped hunting. The crate is playable again: **21,824** tracks, all under `~/Music`, no leftover `!`, no leftover `EDM,`. The missing Aphex and Orb cuts can wait — they are not ghosts in the library anymore. Detail: `docs/TODO.md`. How we did the work: `docs/crate.md`.

### Why we organize like this

We are both. Collector first — decades of vinyl-brain in folders. DJ second — the crate has to survive a night, two decks, and a laptop that is not a NAS.

So the rule is one tree: **Artist / Album / track**. Not `Downloads`. Not `Unknown Album`. Not a volume that goes away. Music.app is where identity lives (artist, album, genre, the Songs list you actually browse). Traktor and Rekordbox are the decks — they must see the **same path**, or you own three libraries that disagree. Mix CDs file under the DJ or series who made the mix (Tenaglia, Farina, Lazy Dog), with the real track artists written on each cut. Mashups have a bucket. Leftovers have `Miscellaneous`. `Unknown` is not a home.

iCloud Sync stays **off**. This is a local DJ crate, not a streaming locker. We do not let [Beets](https://beets.io/) become the library of record — it wants to own the files, and we already have an owner. When a store genre is a slash (`Funk / Soul / Disco`), that is a real spelling, not junk. `EDM, House` is junk. We strip the prefix and keep the rest.

### Three repos, one crate

The audio never enters git. Three public repos share the labor so no one tool tries to be the whole shop.

| Repo | Job |
| --- | --- |
| **This one** — `crate/` | Name it, file it, talk to Music.app, kick off a stem job. Identity, relink, consolidate, genre, ghosts. **STEMIT** is the handshake: pick a playlist, hardlink the mix into `stems_audio`, call the factory. |
| [ixamal/stems](https://github.com/ixamal/stems) | The shop. Mel vocals/instrumental + the four-deck `.stem.m4a`. NUO-STEMS is the reference; this is the CLI that will do tens of thousands. It does not rename your Music library. |
| [ixamal/music_migration](https://github.com/ixamal/music_migration) | After files *move*, Traktor NML and Rekordbox XML still have to find them. Remap paths, repair playlist keys. You do not rebuild 27k rows by hand. |

STEMIT never copies the mix. One set of bytes, two names (Apple Music + `stems_audio`). Delete the stem-side name and the crate file is still there. After a move, `music_migration` is what keeps Traktor and Rekordbox honest. After a naming fight, `crate/` is what keeps Music.app honest. The factory in `stems` only runs when the name is already true.

Traktor → Rekordbox is not our bridge. That is [ATGR DJCU2](https://atgr.nl/). We remapped, then converted, then confirmed the same song lives at the same place in all three.

### The libraries we actually use

**On the decks**

| App | Why it stays |
| --- | --- |
| **Apple Music** | The crate of record for *who it is*. Drag Beatport / Traxsource in. Sync Library Off. |
| **Traktor** | The four-deck STEM player. Collection remapped after every move. |
| **Rekordbox** | The other deck. Same paths as Traktor. Vocals/instrumental pairs from the factory. |
| **Mixed in Key / ReCK** | Key, BPM, energy, cues. We never overwrite those. |
| **Music.app + AppleScript** | Genre and location live in the library database. Writing a file tag alone does nothing to the column browser. We learned that the hard way. |

**To name a mystery, in this order**

Filename → tags already on the mix → iTunes + Deezer (title and duration, or both catalogs agree) → MusicBrainz (album only if we already know the artist) → [AcoustID](https://acoustid.org/) (listen to the file) → [Shazam](https://github.com/shazamio/ShazamIO) for the ones catalogs miss → a local [Ollama](https://ollama.com/) model on this Mac (`qwen2.5:7b`, `127.0.0.1` only) when the artist is already in the filename. Then `Compilations/Mashups/Miscellaneous/`. We do not guess. We do not Discogs-blast the crate. One mix CD from a screenshot is a human job.

**To write and compare audio**

- [mutagen](https://mutagen.readthedocs.io/) — tags on `.mp3` / `.m4a`. Never `.m4p` (DRM). Never `.wav` / `.aiff` (ID3 prepends and the file will not play). Never `.stem.m4a`.
- [ffmpeg](https://ffmpeg.org/) — “is this the same record?” Compare *decoded* audio, not tag bytes. A retag changes the file and a byte compare will swear twins are strangers.
- `fpcalc` / AcoustID, Shazam (`shazamio` in a venv), optional `songrec`.
- [OneTagger](https://onetagger.github.io/) — we used it once for the big `EDM,` strip. Beatport on the last Mac build is dead. Do not re-run Discogs on that set; it flattened House into Electronic and misfiled a compilation as Hip Hop.

**We refused**

Beets as the library. iCloud Sync. Relinking Songs to `/Volumes` (unplug = `!`). Turning on Music.app **Keep Music Media folder organized** (it would hoist the artist-root crate into `Music/` and break the decks). Guessing a title match (“24 Hours” is not unique). Stemming an acapella (it already *is* the vocal). Disk names that still say `Track 01` after Songs already knows the title are `music-organize`, not a casual reshuffle.

### What we just did, and why

Years of audio had been living on a migration drive (Terrarum). Music.app still thought those rows were the crate. Point a library at a USB volume and you do not have a crate — you have a promise that breaks when the cable comes out. So we **copied home first**, then relinked. Tags decided Artist / Album, not the mangled exFAT names.

The copies brought the old sins back with them. `EDM, House` is a cockroach — we killed it, recovered more files, it came back. Same command both times: write the file *and* tell Music.app. iTunes’ `Track 1.m4a` is not a new record; it is a second row on the same sound. We listen, then drop the extra *row*, and we keep the copy that is already in a playlist so a crate slot never goes empty. A tagger prepended `ID3` onto WAVs; Music.app said the file was junk; consolidate kindly added `(2)` and `(3)`. We put `RIFF` back and never write ID3 on a WAV again.

Then we stopped. If it was not on that drive, it is a later hunt, not a Songs ghost. 425 empty rows gone. Drag-and-drop into Music works again (a leftover iTunes shortcut had been copying files onto themselves). Mix CDs read as the DJ who mixed them. STEMIT proved on a real playlist — 21 tracks, 78 minutes, no copies, no failures. One track had no separable vocal, so the factory correctly kept the mix and skipped the pair.

The Python for that fight is `crate/`. Dry-run is the default. Reports stay off git in `~/local_tools/crate/reports`.

### Crate toolkit — steal these

Not a product. A crate that got sick of being a warehouse job. If yours looks like ours, take the idea and leave our paths.

| Command | The idea |
| --- | --- |
| `music-dupes` | Two Songs rows, **one file**. Delete the extra *row*. If Music.app bins the file, restore from Trash and stop. |
| `music-replicants` | Two Songs rows, **two files**, same *sound*. Decode, then drop. Alternate takes stay. |
| `music-genre` | `EDM, House` → `House`. File **and** library. Slash genres are real. |
| `music-repair` | Locate `!` by a unique artist/title hit on disk. Fill empty identity only. |
| `music-reconcile` | Same `!`, from the iTunes XML persistent-ID map. Exact, not a guess. Copy into `~/Music` before you relink. |
| `consolidate` | Pull a migration tree home as Artist / Album. Tags decide the folder. `Track 1` is a duplicate marker. |
| `riff-repair` | ID3-headed WAV is trash. Restore RIFF. Delete `(2)` / `(3)` only when the audio matches. |
| `music-cull` | Hunt over. Drop rows with no file. Valid audio stays. `.m4p` stays even if ffmpeg sulks. |
| `music-organize` | Songs already knows the title; the file is still `Track 01`. Rename / refile Artist / Album / `NN Title`, then relink. Remap the decks after. |
| `music-fix` / `stemit` | Name a playlist by sound. STEMIT hardlinks into `stems_audio` and calls [stems](https://github.com/ixamal/stems). |

If you adapt this: dry-run first. Music.app is a database. Title-only match will collide. WAV is not MP3. The crate stays local.

```bash
cd ~/github/ixamal/ix
PYTHONPATH=crate python3 -m ix_crate music-cull          # dry-run
PYTHONPATH=crate python3 -m ix_crate music-cull --execute
```

### Still ahead (not done)

- Run the remaining genre batches through STEMIT (Alternative is next, 3 tracks first as a check).
- Fill *empty* genres when Beatport works again. Do not blast the old EDM set.
- While processing, stamp owned songs with whatever we already know or can look up (artist, album, title, genre, length, BPM, key, comments, cues). Same kind of store databases OneTagger uses. Do not smash STEM files or overwrite Mixed in Key / ReCK. For STEMs, keep that data beside the file as JSON so Traktor’s four decks stay intact.
- Wire the DJ decks into Unreal so the visuals follow the music.
- Bigger audio path, then sampling Traktor A/B/C into Maschine / S88 — queued as TODO **11a**, not wired.

### Where we are headed — Elysium

Valhalla is the mead-hall of the work. The crate wars, the relinks, the genre pass: fights won in the hall of the slain, seat earned, then the next horn sounds. We do not stay. The hall is for conquest. The destination is **Elysium** — the green field after the last fight, where the worthy rest and the living work begins.

In Elysium the process holds itself. The library is stable. Hands leave the warehouse and go to the floor:

- Creative visuals — Unreal, light, the sim that follows the drop.
- DJing — the crate as an instrument, not a cleanup job.
- Music manipulation and creation — stems, samples, Maschine, the S88, making rather than mending.

The still-ahead list above is the last ships to burn before that shore. Elysium is not a new repo. It is ix when the fights are written down and the nights are for sight and sound.

## What this repo is

A **control plane**. It holds architecture, OSC contracts, abstract MCP schemas, a rehearsal hall for Niagara cache scrubbing, and a loopback OSC runtime.

It does **not** hold Ollama, model weights, live MCP configs, or hardware adapters. Those live outside git:

| Off-repo | Purpose |
| --- | --- |
| `~/local_tools/ollama` | Ollama prefix and models |
| `~/local_tools/mcp_adapters` | Rekordbox, Ableton, Houdini, … |
| `~/.cursor/mcp.json` | Global Cursor MCP |

Every socket this project opens binds `127.0.0.1`. `0.0.0.0` is rejected.

## Run

```bash
mkdir -p ~/github/ixamal
git clone git@github.com:ixamal/ix.git ~/github/ixamal/ix
cd ~/github/ixamal/ix
npm install
./scripts/install-local-tools.sh
npm run dev          # http://127.0.0.1:47241
npm run runtime      # OSC 127.0.0.1:9000
```

Ollama is installed off-repo (Homebrew CLI + LaunchAgent). Bind loopback only:

```bash
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS=~/local_tools/ollama/models
```

Point Cursor Models at `http://127.0.0.1:11434/v1`. Full steps: `docs/local-setup.md`.

## Halls

- **Engine** — UE 5.x Niagara 3D fluids + 15s sim cache, OSC scrub
- **Forge** — Blender / Maya / Houdini (optional HDAs later)
- **Stage** — Ableton / Reaper OSC with a command allowlist
- **Floor** — Rekordbox / Traktor / Pro DJ Link
- **Oracle** — local Ollama, never vendored here

## Docs

- `.cursor/context.md` — notes for desktop and iPhone Cloud Agents
- `docs/architecture.md`
- `docs/security.md`
- `docs/local-setup.md`
- `docs/crate.md` — how the crate work actually ran (commands, scars, STEMIT)
- [ixamal/stems](https://github.com/ixamal/stems) — the stem factory STEMIT calls
- [ixamal/music_migration](https://github.com/ixamal/music_migration) — remap Traktor / Rekordbox after files move
- `docs/djcu2.md` — Traktor ↔ Rekordbox via [ATGR DJCU2](https://atgr.nl/)
- `docs/onetagger.md` — genre pass (files + Music.app); not an LLM
- `docs/examples/music-set-genre.applescript` — generic Music.app `set genre` specimen (do not run)
- `docs/TODO.md` — ordered checklist (crate, tagging, Floor, NI)
- `docs/notes.md` — crate / tagging / hardware parking lot (do not execute from it)
- [ixamal/blackhole](https://github.com/ixamal/blackhole) — S8 / S88 / BlackHole routing (off this repo)
- [ixamal/ix_bangers](https://github.com/ixamal/ix_bangers) — Bangers MCP catalog, dry mode (off this repo)
- [github.com/alkalurop](https://github.com/alkalurop) — org profile is the main bridge; monthly 15th snapshot of the ixamal repos

Apache-2.0. See `LICENSE`.
