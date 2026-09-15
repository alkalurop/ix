# Architecture

```
                    CURSOR (control plane)
                    git · files · this repo
                              |
              +---------------+---------------+
              |                               |
     Public ix repo                    Off-repo machine
     ~/github/ixamal/ix                ~/local_tools
     schemas, OSC spec,                mcp_adapters/
     Niagara rehearsal UI              ollama/
     Python loopback runtime           ~/.cursor/mcp.json
              |                               |
              +---------------+---------------+
                              |
                     127.0.0.1 only
            OSC :9000    Ollama :11434    UE MCP
                              |
              Rekordbox / Traktor / Ableton / Blender / Houdini
                              |
                         Unreal Engine 5
                    Niagara Sim Cache (15s)
```

## Why Niagara cache, not live fluids
Cinema-grade pyro at 60 FPS next to Lumen is a bad live bet. Bake the sim. Scrub, reverse, and retime it from DJ beat phase. This is how large LED shows (including Sphere-scale work) actually run: pre-baked beauty, live time and light.

## Why not Omniverse / Zibra / Bifrost for v1
- Omniverse is not native on macOS.
- Zibra is a paid GPU codec. Useful later, not required.
- Maya Bifrost is offline-first.
- NanoVDB is a fine open alternative when a Houdini cache is needed. It is ASWF, not Nvidia-locked, and compiles for Metal.

## Control plane in this repo
The Next.js app is the rehearsal hall: OSC inject, Niagara cache playhead, Ollama probe, bridge map, security map. It does not ship Unreal. It does not ship Ollama.

## Runtime
`python3 -m ix_runtime` binds UDP OSC and a health HTTP port on `127.0.0.1`. It refuses `0.0.0.0`.

## Oracle
Ollama is not in this repo. On the Mac it is the Homebrew `ollama` CLI, kept alive by LaunchAgent `ai.ixamal.ollama`, listening on `127.0.0.1:11434`, with weights in `~/local_tools/ollama/models`. The rehearsal UI only probes that URL. Install notes: `docs/local-setup.md`.

## Crate
DJ files live in `~/Music/stems_audio`. STEM factory is [ixamal/stems](https://github.com/ixamal/stems). NML remaps are [ixamal/music_migration](https://github.com/ixamal/music_migration). Identity repair and the Music.app crate toolkit are `crate/` (`docs/crate.md`; README *Crate toolkit*). Disk names from Songs metadata are `music-organize`. Traktor ↔ Rekordbox convert is **[ATGR DJCU2](https://atgr.nl/)** (`docs/djcu2.md`) — confirmed 2026-08-30. Performance routing (S8 / S88 / BlackHole) is [ixamal/blackhole](https://github.com/ixamal/blackhole). Bangers catalog (dry) is [ixamal/ix_bangers](https://github.com/ixamal/ix_bangers). Monthly org snapshot of the public ixamal originals is [alkalurop](https://github.com/alkalurop) (`docs/local-setup.md`). Collection snapshots stay in `databases/` on the Mac, not in git.
