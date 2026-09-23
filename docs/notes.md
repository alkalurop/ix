# Working notes (do not execute from this file)

Parking lot for crate, tagging, and hardware ideas. Ordered checklist: `docs/TODO.md`. Agents: read both, then stop unless David asks to act. Off-repo tools and library paths stay off git.

Last update: 2026-09-23. **16ch Channel D + 11a live.** A/B/C sample into Maschine → S88 → D. **11b parked** (FLX10 native). **13 on hold** (S8 pads). **Next: Floor 10.** Hardware leftover: **40**. 2ch rollback: `~/Music/blackhole_2ch/`. Alkalurop bridge monthly 15th 15:00 local; benchmark mirror this afternoon. `favorites` still recording (TODO 41); reviews **2026-09-16** / **2026-10-09**. Toolkit: README. How/why: `docs/crate.md`.

## Alkalurop org bridge (2026-09-15)

Org [alkalurop](https://github.com/alkalurop) is the main bridge (profile: [alkalurop/.github](https://github.com/alkalurop/.github)). First mirror of current ixamal `main`:

First mirror of then-current ixamal `main` (2026-09-15):

| alkalurop | then `main` |
| --- | --- |
| [ix](https://github.com/alkalurop/ix) | `6ec577f` |
| [stems](https://github.com/alkalurop/stems) | `40069a1` |
| [ix_bangers](https://github.com/alkalurop/ix_bangers) | `f257be1` |
| [blackhole](https://github.com/alkalurop/blackhole) | `17700c3` |
| [music_migration](https://github.com/alkalurop/music_migration) | `0a4735f` |

`github.com/alkalurop/ix` used to 301 to ixamal/ix (old transfer redirect). Re-created the org repo so the name lives on the org. Script: `docs/examples/alkalurop-bridge.sh`. Plist: `ai.ixamal.alkalurop-bridge` — 15th 15:00 local. No tokens in git.

**2026-09-19 refresh:** mirrored current ixamal `main` onto alkalurop (David-only authorship, Floor next, **13** on hold).

**2026-09-23 benchmark.** Functioning rig is the 13:11 CDT checkpoint (archive off git). Same afternoon: stems HUD ETA, and `ix_bangers` `scripts/speak.mjs` (dry read of Rekordbox, one Apple album, one Traktor file). Then a full ixamal → [alkalurop](https://github.com/alkalurop) mirror, ahead of the monthly 15th. Org profile: [alkalurop/.github](https://github.com/alkalurop/.github). SHAs are the ixamal `main` tips mirrored that run:

| alkalurop | 2026-09-23 `main` |
| --- | --- |
| [ix](https://github.com/alkalurop/ix) | this note |
| [stems](https://github.com/alkalurop/stems) | `8a16432` |
| [ix_bangers](https://github.com/alkalurop/ix_bangers) | `8b17f46` |
| [blackhole](https://github.com/alkalurop/blackhole) | `83cf17a` |
| [music_migration](https://github.com/alkalurop/music_migration) | `7e8768c` |

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

### IndustryStems folder kept (2026-09-19)

The `IndustryStems/` tree is not unfinished work. Official `drums/bass/other/vocals.wav` packs stay there. `--fix-industry-artists` only named them. `--dedupe` keeps those WAVs. Checked 2026-09-19: **209** folders, **835** wav, **44 GB**, `nlink` 1. Traktor 4.5.1 **1251** path hits; rekordbox.xml **968** Locations (artist already clean). A factory mix of the same song under Artist/Album is a different file. David asked to leave it. Do not delete.

### Resume next

1. Reload Rekordbox xml (`<>`) and reopen Traktor if needed — analyze new DJ Sets rows. First glance 2026-09-10 was good.
2. Leftover same-title copies in STEMIT. Alternative stems 1–3 (TODO 17) unless David names another playlist.
3. **11 + 11a done.** 16ch Channel D. A, B, and C sample into Maschine, S88 on D. **11b parked** (FLX10). **13 on hold** (S8 pads → S88).
4. **40** Investigate Traktor → FLX10 Channel 2 as a digital feed (today: analog master). Leftover after Floor.
5. **Next: Floor 10.** OSC `127.0.0.1:9000` → UE Niagara.
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

Working rig (2026-09-19): S88 keys into Komplete Kontrol or Maschine, down **BlackHole 16ch 1–2**, into Traktor Channel D on **Traktor S8 + BlackHole**, out the S8 fader. KK and Maschine share one D fader. Leave Maschine Input off BlackHole (loop). Leave S8 unchecked in Maschine MIDI. Close KK when Maschine needs the S88.

**2ch rollback (2026-09-19):** `~/Music/blackhole_2ch/`. **16ch post-quit archive:** `~/Music/blackhole_16ch_2026_09_19_0755/` (TSI = Traktor S8 + BlackHole; Maschine = BH 16ch). Off git.

**This session (blackhole):**

1. **Done.** 16ch Channel D. Traktor `Traktor S8 + BlackHole`, D = In 10/11. First try In 11/12 was right-only. Maschine BH 16ch Out 1 only. Sound checks.
2. **11a done.** A, B, and C all check. Internal Record **7/8** → Maschine In 2 → S88 → D.
3. **11b parked.** 2026-09-19: Rekordbox on `FLX10 + BlackHole 2ch` silenced the Sony, booth, and master. David, 2026-09-23: that silence needed a reboot, same class as the S8 power cycle. It is not a ban on a digital feed. Aggregate was destroyed that day; scripts remain. Native **DDJ-FLX10** is what is selected now.
4. **13 on hold.** S8 pads → S88 slots after Floor. Convert to WAV/AIFF only if file samples are needed (`~/local_tools`).

Keep converters and MIDI maps in `~/local_tools`, not in this public repo. Rekordbox audio device stays **DDJ-FLX10**. Leftover S8/S88 MIDI maps stay unused.

## FLX10 tempo range (2026-09-23)

Looked up for a live slide parked at **125 BPM**, wanting the tempo fader capped at **±1**, **±5**, or **±30 BPM**. Rekordbox on the DDJ-FLX10 does not have BPM brackets. The fader throw is a percent of the track’s original BPM, and there are four stops only: **±6% → ±10% → ±16% → WIDE (±100%)**.

On the deck: hold **SHIFT** and press **TEMPO RESET** (the button beside the tempo fader). Each press advances one stop. The jog display and the **±%** under the BPM show the current stop. Clicking that **±%** in Performance mode cycles the same four. Range is per deck.

TEMPO RESET alone snaps playback back to the original BPM and ignores the fader until you press it again.

At a **125.00** original:

| Stop | Full throw | Floor–ceiling |
| --- | --- | --- |
| ±6% | ±7.50 BPM | 117.50–132.50 |
| ±10% | ±12.50 BPM | 112.50–137.50 |
| ±16% | ±20.00 BPM | 105.00–145.00 |
| WIDE | ±125 BPM | 0–250 (track stops at −100%) |

So the three asked caps do not exist as stops:

- **±1 BPM** (±0.8%) and **±5 BPM** (±4%): tightest stop is **±6%** (±7.5 BPM). That is the live slide to use when the goal is staying near 125. Center of the fader is 0%. On-screen tempo steps at ±6% are 0.02% (0.025 BPM at 125), so a small move off center is the ±1 zone, but the fader can still reach ±7.5 if you shove it.
- **±30 BPM** (±24%, 95–155): **±16%** stops at ±20 (105–145). **WIDE** is the only stop that can reach ±30, and the same throw continues out to 0–250, so the fader is no longer isolated inside ±30.

Pitch bend (jog side, Vinyl off) nudges without moving the tempo fader, so the chosen bracket stays put. Long-press **KEY SYNC** (no SHIFT; the dash on the hardware diagram means hold) toggles **Master Tempo** so the slide changes BPM and leaves the key alone. **MT** shows on the jog display. SHIFT + KEY SYNC is key reset, a different function.

Default for CDJ/XDJ export is Preferences → **DJ System** → **My Settings** → **Tempo Range**, then apply to the device. That file only stores ±6 / ±10 / ±16 / WIDE. It does not add a custom BPM cap. Live FLX10 sessions still follow SHIFT + TEMPO RESET on the deck.

Links:

- [DDJ-FLX10 instruction manual](https://support.pioneerdj.com/hc/en-us/articles/16716272919193) — rekordbox section: SHIFT + TEMPO RESET cycles ±6 / ±10 / ±16 / WIDE.
- [Rekordbox hardware diagram](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-FLX10/DDJ-FLX10_HardwareDiagram_rekordbox_E1.pdf) — TEMPO RESET = tempo reset / tempo range; KEY SYNC long-press = Master Tempo.
- [EVERY button explained — Pioneer DDJ FLX10](https://www.youtube.com/watch?v=Ji8Tpzj21Sc) — tempo fader, TEMPO RESET, then SHIFT + TEMPO RESET through ±6 / ±10 / ±16 / WIDE. No shorter clip turned up that is only this control.

## FLX10 Channel 2 + USB noise

**11b (2026-09-19, corrected 2026-09-23).** Rekordbox on `FLX10 + BlackHole 2ch` silenced master, booth, and the Sony. David: that was a reboot, not a broken route. The aggregate was destroyed that day. Rekordbox is on native **DDJ-FLX10** until the digital try is on purpose. Booth stays the FLX10’s analog RCAs to the KRK. Not the same job as **40**.

**Room (2026-09-23).** The FLX10 is the hub. Master goes to the **Sony STR-AN1000**. That master is split with **AudioQuest** plus a sub controller into an **SVS** sub. Booth is a **KRK Rokit 5**. S8 master out and S8 booth out should sit idle. Serials, and the exact SVS / AudioQuest / sub-controller models, come later (State Farm). Rekordbox device stays native **DDJ-FLX10**.

**Target (TODO 40).** David wants the whole S8/Traktor mix on FLX10 channel 2 without the analog master cable. Afternoon conclusion below: **LINE stays the working feed.** The switch cannot be aimed at BlackHole.

**B is the second USB port**, not a Rekordbox checkbox. The channel switch is USB **A** / **LINE** / USB **B** (Serato quickstart; the FLX10 manual calls A and B “a track loaded onto a deck”). This Mac is on one USB port, so Rekordbox owns **A**. **B** is the other USB socket, meant for a second computer. With nothing on that socket, CH2 on B is silent. LINE is the only position that hears the S8 master cable.

Do not add the FLX10 to `Traktor S8 + BlackHole` (44.1 vs 48 kHz). The second USB port has no channel-2 bus.

**Second cable, 2026-09-23.** David plugged this Mac into the other FLX10 USB port. CoreAudio shows two `DDJ-FLX10` devices, both 44.1 kHz, 10 in / 4 out. Rekordbox is on `…:2100000:1,2` (running). The free port is `…:EEMP004232CC:1,2` (idle). Its only output format is 4 channels at 44.1: **Out 0 / Out 1** master, **Out 2 / Out 3** phones. There is no channel-2 deck bus for a bridge to write. Switch **B** plays a deck from DJ software on that port, not a CoreAudio copy of Traktor. Do not play BlackHole into Out 0 / Out 1. That is PC-B master and can reach the Sony. CH2 on **B** with nothing playing a deck there stays silent. **LINE** remains the S8 feed. **A** remains Rekordbox.

**LINE is not Channel D (2026-09-23 afternoon).** David asked to make CH2 digital, including calling it MIDI, then asked whether LINE can take the S8 the way BlackHole feeds S8 Channel D. It cannot. Nothing was rerouted. Rekordbox stayed on **DDJ-FLX10**. Traktor stayed on **Traktor S8 + BlackHole**. No bridge was started.

S8 Channel D works because Traktor is the mixer for that channel. Mixing mode is Internal. Deck D’s header is **Live Input**. Input routing is aggregate **In 10 / In 11** (the first BlackHole pair). The channel button is **TRAKTOR**, so the hardware channel plays that software deck. Maschine writes BlackHole **Out 0 / Out 1**. Traktor hears it.

FLX10 CH2 **LINE** selects the rear RCA. The manual calls that a line-level device on the LINE terminals, mixed in the hardware with no computer in the path. There is no device menu that assigns LINE to BlackHole, the S8, or any CoreAudio input.

FLX10 CH2 **A** or **B** plays a track loaded on a deck in the DJ app on that USB port. Rekordbox decks play a library track. They have no Traktor Live Input, so they will not play the S8 mix that is already on the Traktor record tap. Rekordbox already owns USB A and will not run a second copy on USB B. Pointing Traktor’s audio device at the FLX10 drops S8 phones and Channel D.

CoreAudio on this Mac, one `DDJ-FLX10`: **10 in / 4 out**, 44.1 kHz. Those four outputs are master and phones. Writing them reaches the Sony or the headphone jack and skips the channel fader. MIDI on the FLX10 is faders, pads, and the switch. The mix is audio.

DDJ-FLX10 Setting Utility labels such as **CH2 Control Tone DIGITAL** and **Pre/Post CH fader** are the recording direction, mixer into the computer. Rekordbox Input Deck 1–4 are the same RCAs, computer-bound. **PC MASTER OUT** copies the rekordbox master to a computer device and still lands on the master bus, not on the CH2 fader.

The S8 mix is already digital on Traktor record **7/8**. The channel strip accepts it through the RCA on **LINE**. iDefender stays.

USB ground-loop / 5 V power hum on this rig: **iFi iDefender Max** (USB-C). Bought from [Bloom Audio](https://bloomaudio.com/) 2026-05-08, order **52738**. It sits on the USB path and strips host power so the interface is not sharing a dirty 5 V rail. David: it works pretty well. Leftover noise after that insert is why CH2 digital is on the list — do not rip the iDefender out while chasing 40. Note for anyone cloning the hall: try the iDefender Max before buying another mixer or a new interface.

## Shutdown hum + Channel D (2026-09-23)

Prefs were already the live rig (Traktor `Traktor S8 + BlackHole`, D = In 10/11, Maschine BH 16ch Out 1 = Out 0/1, Rekordbox native `DDJ-FLX10`). S8 phones were silent and FLX10 CH2 had no S8 master. David powered down: **Maschine, Traktor, S88, S8.**

1. **Maschine quit first.** S88 reverb became audible on **S8 Channel D**. Traktor was still open. The BlackHole → Deck D path was alive. Maschine in front was the piece that had been keeping that reverb off D. KK and Maschine share the one D fader; KK stays quit when Maschine should own the S88.
2. **Traktor quit, then S88 off, then S8 off.** Killing the S8 left an analog hum on the FLX10. The **Sony STR-AN1000** volume was cranked, which is why it showed up. That hum was not heard while the S8 was still on. FLX10 CH2 is the analog insert from the S8 master jacks, so an S8 that has just lost power is an open line input.

**Repair when isolating (not done yet):**

- Sony down, and FLX10 CH2 **TRIM** down, before the S8 loses power. Switch CH2 off **LINE** if the S8 will stay off. An open LINE input plus a cranked receiver is this hum.
- Leave the **iFi iDefender Max** in place. If the hum is still there with the S8 on, master meters moving, and the Sony at a normal level, that is TODO **40**, not this shutdown.
- Prove Channel D again before Maschine opens: S88 key, D fader up, Traktor already on `Traktor S8 + BlackHole`. The reverb tail already showed that path. Then open Maschine (KK quit) and play a key with Out 1 on BlackHole **Out 0 / Out 1**. If D goes quiet only while Maschine is in front, the gap is Maschine’s level or which sound is selected, not the aggregate.

**Power up (proven 2026-09-23):** Sony down and FLX10 CH2 TRIM down. **S8** (wait until it enumerates), **S88** (direct USB + wall wart), **Traktor**, prove phones (monitor **3 / 4**) and a deck, prove D with Maschine still quit, then CH2 **LINE** and bring the Sony up. **Maschine last.** KK stays quit. David ran **S8 → S88 → Traktor → Maschine** and the rig came back.

## Functioning checkpoint (2026-09-23 13:11 CDT)

This is the working rig. Archive (off git): `~/Music/blackhole_16ch_2026-09-23_1311/`. Traktor, Maschine, and Rekordbox were open. On-disk TSI already says **Traktor S8 + BlackHole**. Maschine plist already says **BlackHole 16ch**.

Traktor: 48 kHz, buffer 512, Internal, master **1/2**, phones **3/4**, record **7/8**, Deck D **In 10/In 11**. Maschine: Out 1 = **Out 0/Out 1**, In 1 off, In 2 = **In 2/In 3**, In 3 = **In 4/In 5**. Rekordbox: native **DDJ-FLX10**, 44.1 kHz, PC MASTER OUT off, master and phones on the FLX10, booth empty. One FLX10 was in Core Audio. Mac default output was External Headphones. Channel 2 **LINE** is still the S8 RCA. Boot: **S8 → S88 → Traktor → Maschine**.

## Parked in siblings (not this repo)

- [ixamal/blackhole](https://github.com/ixamal/blackhole) — 16ch Channel D + 11a live. 2ch archive: `~/Music/blackhole_2ch/`. **11b parked** (FLX10 native). **13 on hold.** Next work is Floor on this repo.
- [ixamal/ix_bangers](https://github.com/ixamal/ix_bangers) — Bangers MCP catalog (stems, Music, Rekordbox, Traktor). Dry mode until David says commit. Not native Traktor.
- [ixamal/stems](https://github.com/ixamal/stems) — factory idle after the first `stems_audio` pass. Parked there: dump the crate to JSON + a spreadsheet webpage. Not now.

## Played / Not Played But Should (TODO 41)

```bash
PYTHONPATH=crate python3 -m ix_crate favorites
PYTHONPATH=crate python3 -m ix_crate favorites --execute
PYTHONPATH=crate python3 -m ix_crate favorites --execute --playlists
PYTHONPATH=crate python3 -m ix_crate favorites --execute --snapshot
```

**Crates:** stable names. `Played` is the **100 most recent** (`last_played`). `Not Played But Should` has three subcrates of **12** each — neglected genres (genres you play that still have sitting tracks), random, favorites-match (genre + BPM ±6 + energy ±1). Library tracks whose genre or title says acapella stay out of those picks. Skip playlist writes when the play fingerprint is unchanged (no new decks). Full 22k not-played stays in JSON only.

**2026-09-23 genres.** The same `--playlists` write adds `MUSIC/GENRES/<Genre>` from the shared iTunes library XML (file on disk, `.m4p` skipped) and `MUSIC/ACAPELLAS/<Genre>` for STEMIT vocals (`Song_vocals.m4a`, `vocals.m4a`) matched to that library. Artist + title first, then the title with mix and feat tails removed. When several rows share the title, the folder artist picks. No Untagged playlist. Vocals the library does not name are finished by `follow_unmatched()` in `library_genres` (MusicBrainz, then Shazam) and written back to `ACAPELLAS` only. Quit Rekordbox for xml, Traktor for NML. Apple Music media is never written. FairPlay `drms` files skip in the factory as `apple drm`. Process: `docs/crate.md`.

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
