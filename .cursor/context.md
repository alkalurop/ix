# IX context (synced for desktop + mobile agents)

Cursor desktop chats do not sync to the iPhone app. Cloud Agent threads do. Long-term decisions live in this repo so any device can read them.

## On Ix now (2026-09-30)

Floor TODO is phased ComfyUI → Syphon/NDI → UE (notes only). Phase 1 is local ComfyUI on Apple Silicon. RedefineFX Chaos & Niagara Destruction is the Phase 3 learning track. Do not install or implement from the list.

Source: Gemini architecture conversation, 2026-08-24, brought into ix by the first Valhalla cloud agent. Alkalurops vision (About page + Floor phases) landed 2026-09-30.

## Decision
ix is Valhalla: Cursor is the control plane. Ollama, MCP hardware bridges, and live sockets stay **off-repo**.

## Stack
1. Unreal Engine 5.x on Apple Silicon / macOS (Blueprints + C++ now; Verse later).
2. Niagara 3D grid fluids + 15s Niagara Sim Cache. No Houdini required for v1.
3. Rekordbox / Traktor / Pro DJ Link → OSC on `127.0.0.1:9000`.
4. Optional later: Houdini HDA / OpenVDB / NanoVDB (ASWF, Metal-capable).
5. Global MCP: `~/.cursor/mcp.json`. Adapters: `~/local_tools/mcp_adapters/`.
6. Ollama (installed on the Mac 2026-08-24): Homebrew CLI, LaunchAgent `ai.ixamal.ollama`, `OLLAMA_HOST=127.0.0.1:11434`, models in `~/local_tools/ollama/models`. Coder: `qwen2.5-coder:7b`. Crate music ID: `qwen2.5:7b`. Not in git. See `docs/local-setup.md`.

## Crate + hardware
Unknown Album dump **executed**. Inbox catalog + Ollama (`qwen2.5:7b`) **executed**. Traktor NML remapped. DJCU2 **worked**. Path-stable (TODO 3). Accapella + `EDM, …` **closed** (TODO 4 / 4a). `House, …` + Hip Hop spelling **closed** (TODO 8 / 9). Music.app same-file rows **closed** (TODO 16). Locate/! rows **relinked** (TODO 18). Playlist **Fix** identity **closed** (TODO 19 + 20; 0 empty artists). Various Artists fingerprint pass **closed** (TODO 21; 263 tagged / 75 leftover). Screenshot compilations **closed** (TODO 22; GU 010, Lazy Dog, MJ7, Mix This Pussy). Music.app `Media.localized/Music` is a **real folder** (drag-and-drop; never symlink to `.`). Stem jobs are **STEMIT** (`ix_crate stemit`) — `Never Forget 50th v01` **done** (TODO 23; 21/21, 78 min). **Rock genre STEMIT done 2026-09-24** (TODO 16c; ≈ **23%** of `MUSIC/GENRES`). Daily crates: **CRATER**. `EDM, …` recurrence + replicant rows **closed** (TODO 24; 229 + 66 genres, 622 extra rows). Terrarum recover + `music-cull` **closed** (TODO 25; 425 ghosts; library **21,824**, leftover `!` **0**). `riff-repair` restored ID3-headed WAV. **music-organize** shipped (TODO 26) — disk names from Songs metadata; Keep Music Media folder organized stays **Off**. Never mutagen-write `.wav`. Never relink to `/Volumes`. Items **5 / 5b / 6 omitted**. Stems: Acapella do not stem; Afro House done. **Milestone 2026-09-08: David is playing in Rekordbox + Traktor.** `crates --all` wrote Music.app **House / Origin Stories** into `rekordbox.xml/MUSIC/` (TODO 38). **2026-09-10:** ingest filled DJ Sets **230**; IndustryStems artist **0** (TODO 39). **2026-09-19:** `stems_audio/IndustryStems/` **kept** — official 4-WAV packs, live on the decks; do not delete (TODO 39a). TODO 41: CRATER / `favorites` records plays + patterns; git snapshots quarterly. Reviews **2026-09-16** / **2026-10-09**. **2026-09-19:** BlackHole **16ch Channel D** + **11a** (Traktor A/B/C → Maschine In 2 → S88 → D). **11b parked:** Rekordbox must stay native `DDJ-FLX10` (aggregate device broke master/booth/receiver). **13 on hold** (S8 pads → S88). **Next: Floor Phase 1** (local ComfyUI). Hardware leftover: FLX10 CH2 digital (40); iFi iDefender Max stays on USB. 2ch rollback: `~/Music/blackhole_2ch/`. Alternative stems 1–3 when David names one. **2026-10-11:** opening Traktor or Maschine while Rekordbox is already up kills sample-bank drag (Core Audio restart; playback can continue). Quit Maschine, then Traktor, then Rekordbox, and open Rekordbox again on native `DDJ-FLX10`. Procedure: `docs/examples/traktor-master-class-notes.md`. NI/Maschine lives in [ixamal/blackhole](https://github.com/ixamal/blackhole). Org bridge: [github.com/alkalurop](https://github.com/alkalurop) (publish this tip; monthly 15th). Deck convert: [ATGR DJCU2](https://atgr.nl/). Toolkit: README. How/why: `docs/crate.md`. Step log: `docs/onetagger.md`. Links: `docs/notes.md`.

## Immediate Floor work (on the Mac, not in this cloud VM)

Notes only from `docs/TODO.md` — do not install software or implement nodes from this list.

1. Phase 1: local ComfyUI on Apple Silicon (Python 3.11, PyTorch MPS, force-fp16, distilled 1–4 step models at 512×512).
2. Threaded OSC listener on `127.0.0.1:8000` for amplitude / frequency bands into prompt weights, denoise, or latent seed.
3. Phase 2–3 after that: Syphon/NDI into a UE dynamic material, then Niagara + lighting on the same OSC.

## Sync back to Mac
- Cloud Agent chat is visible at cursor.com/agents and in the Mac Agents panel.
- File changes land on Mac after pull into `~/github/ixamal/ix`.
- Do not rely on desktop Composer history. Rely on these markdown files.

## Deeplink to continue on desktop
https://cursor.com/link/prompt?text=Read%20.cursor/context.md%20and%20docs/TODO.md%20Floor%20section.%20Continue%20the%20Alkalurops%20rig%3A%20Phase%201%20local%20ComfyUI%20on%20Apple%20Silicon%2C%20notes%20only%20%E2%80%94%20do%20not%20install%20or%20implement%20nodes%20from%20the%20list.
