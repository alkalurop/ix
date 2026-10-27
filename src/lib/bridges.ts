export type HallId = "engine" | "forge" | "stage" | "floor" | "oracle";

export type Bridge = {
  id: string;
  hall: HallId;
  name: string;
  role: string;
  protocol: string;
  listen: string;
  mcpHint: string;
  statusHint: string;
};

export const halls: Array<{
  id: HallId;
  title: string;
  epithet: string;
  summary: string;
  href: string;
}> = [
  {
    id: "engine",
    title: "Engine",
    epithet: "Unreal Engine 5",
    summary:
      "Niagara 3D grid fluids, sim caches, OSC scrubbing. Apple Silicon, Metal.",
    href: "/bridges#engine",
  },
  {
    id: "forge",
    title: "Forge",
    epithet: "DCC",
    summary:
      "Maya, Houdini HDAs. Blender bpy lives in ixamal/stage (GPL), not ix.",
    href: "/bridges#forge",
  },
  {
    id: "stage",
    title: "Stage",
    epithet: "DAW",
    summary: "Ableton Live and Reaper over OSC. Tempo, clips, and arm — nothing else.",
    href: "/bridges#stage",
  },
  {
    id: "floor",
    title: "Floor",
    epithet: "DJ",
    summary:
      "Rekordbox / Traktor / Pro DJ Link. BPM, fader, beat phase into UE.",
    href: "/bridges#floor",
  },
  {
    id: "oracle",
    title: "Oracle",
    epithet: "Ollama",
    summary:
      "Local LLM on loopback. Weights and the binary never enter this git tree.",
    href: "/oracle",
  },
];

export const bridges: Bridge[] = [
  {
    id: "unreal",
    hall: "engine",
    name: "Unreal Engine 5",
    role: "Live canvas. Niagara sim cache playback, lights, cameras.",
    protocol: "OSC + in-editor MCP (stdio / 127.0.0.1)",
    listen: "127.0.0.1:9000",
    mcpHint: "unreal-engine (global ~/.cursor/mcp.json)",
    statusHint: "Enable the OSC plugin. Bind cache Age to /rekordbox/bpm.",
  },
  {
    id: "houdini",
    hall: "forge",
    name: "SideFX Houdini",
    role: "Optional HDA / VEX / NanoVDB when Niagara authorship runs out.",
    protocol: "stdio MCP, local hou sockets",
    listen: "127.0.0.1 only",
    mcpHint: "houdini (global MCP, adapter under ~/local_tools)",
    statusHint: "Not required for the first live slice.",
  },
  {
    id: "maya",
    hall: "forge",
    name: "Autodesk Maya",
    role: "Bifrost is a last resort. Prefer Niagara, then Houdini.",
    protocol: "stdio MCP",
    listen: "127.0.0.1 only",
    mcpHint: "maya (global MCP)",
    statusHint: "Optional. Do not put Maya paths in this repo.",
  },
  {
    id: "ableton",
    hall: "stage",
    name: "Ableton Live",
    role: "Tempo and clip control for rehearsal and scored sets.",
    protocol: "OSC UDP",
    listen: "127.0.0.1:11000",
    mcpHint: "ableton-daw → ~/local_tools/mcp_adapters/ableton.py",
    statusHint: "Circuit breaker: play, stop, set_tempo, arm_track.",
  },
  {
    id: "rekordbox",
    hall: "floor",
    name: "Rekordbox / Pioneer Pro DJ Link",
    role: "Live BPM, fader, beat phase, track id for Niagara scrub.",
    protocol: "OSC over loopback (or Ethernet → local bridge)",
    listen: "127.0.0.1:9000",
    mcpHint: "dj-rekordbox → ~/local_tools/mcp_adapters/dj_bridge.js",
    statusHint: "Hardware adapters never live in git.",
  },
  {
    id: "traktor",
    hall: "floor",
    name: "Traktor",
    role: "Same OSC contract as Rekordbox so UE does not care who is playing.",
    protocol: "OSC UDP",
    listen: "127.0.0.1:9000",
    mcpHint: "dj-traktor → ~/local_tools/mcp_adapters/traktor.py",
    statusHint: "Addresses stay /rekordbox/* for a single UE mapping.",
  },
  {
    id: "ollama",
    hall: "oracle",
    name: "Ollama",
    role: "Local model runtime. OpenAI-compatible at /v1 for Cursor.",
    protocol: "HTTP loopback",
    listen: "127.0.0.1:11434",
    mcpHint: "Do not add an Ollama MCP in-repo. Point Cursor Models at /v1.",
    statusHint: "Install under ~/local_tools/ollama. Bind OLLAMA_HOST=127.0.0.1.",
  },
];
