# Gemini conversation — distilled

This is the working memory from the Gemini thread that defined IX. Full chat stays out of git; the decisions do not.

## Cursor mobile vs Mac
Desktop Composer history is local SQLite under workspaceStorage. The iPhone app does not see it. Cloud Agents do. Persist architecture in `.cursor/` and `docs/` so phone-spawned agents and the Mac share a brain.

## MCP + Ollama + DCCs
Cursor is the orchestrator. Frontier models (Claude / Codex) plan and call MCP. Ollama stays on loopback for local inference. Maya / Houdini / Unreal MCP servers are configured **globally**, not in-repo. Blender (`bpy`) is **stage** only (GPL).

## Open-source vs machine
Do not keep MCP adapters in the git tree even behind gitignore. Accidental `git add .` is how Macs get compromised. Store them in `~/local_tools`.

## Live music → UE
Yes, people do this (Anyma / Afterlife, Pro DJ Link, MetaSounds, Spout/NDI). The live part is scrub, camera, light, and mix — not a full Navier-Stokes solve on the GPU during the drop.

## Zibra vs NanoVDB vs Niagara
Zibra is performant and expensive. NanoVDB is ASWF open source and Metal-capable. For v1 on a Mac: Niagara fluids + sim cache. Houdini HDA later if authorship needs VEX.

## UE6 / Verse
Too far out. Stay on UE 5.x Blueprints + C++. Verse will be text-native and MCP-friendly when it lands.

## Immediate actions
1. UE OSC `:9000` loopback.
2. 15s Niagara smoke cache.
3. Wire `/rekordbox/bpm` and `/rekordbox/fader`.

Crate and NI S8/S88 / BlackHole 16ch ideas live in `docs/TODO.md` and `docs/notes.md`. Do not treat this Gemini distill as the crate log.
