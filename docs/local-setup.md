# Local setup (Mac)

Clone next to the other ixamal repos:

```bash
mkdir -p ~/github/ixamal
git clone git@github.com:ixamal/ix.git ~/github/ixamal/ix
cd ~/github/ixamal/ix
npm install
./scripts/install-local-tools.sh
```

The installer creates off-repo directories only. It does **not** install Ollama:

- `~/local_tools/mcp_adapters`
- `~/local_tools/ollama`
- `~/.cursor/mcp.json` (from `schemas/mcp.example.json` if missing)

## Ollama (never inside this repo)

The control plane only probes `http://127.0.0.1:11434`. The binary, weights, LaunchAgent, and shell env stay off-repo.

On this Mac (2026-08-24): Homebrew formula `ollama` (CLI). Not the `ollama-app` cask. Not copied into git.

```bash
brew install ollama
mkdir -p ~/local_tools/ollama/models ~/local_tools/ollama/bin
ln -sfn "$(brew --prefix ollama)/bin/ollama" ~/local_tools/ollama/bin/ollama
```

Do **not** run `brew services start ollama`. That unit does not pin loopback or the models directory. Use a user LaunchAgent instead.

### Bind and model path

```bash
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS=~/local_tools/ollama/models
```

On this machine those exports live in `~/local_tools/ollama/env.sh` and are sourced from `~/.zshlocal/.zshrc` (both off-repo).

LaunchAgent label: `ai.ixamal.ollama` → `~/Library/LaunchAgents/ai.ixamal.ollama.plist` (off-repo). It must set:

| Key | Value |
| --- | --- |
| `OLLAMA_HOST` | `127.0.0.1:11434` |
| `OLLAMA_MODELS` | `$HOME/local_tools/ollama/models` (expand `$HOME` in the plist; do not commit the plist) |
| Program | `$(brew --prefix ollama)/bin/ollama serve` |

Confirm the listen address before pulling models:

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
# NAME must be 127.0.0.1:11434 — never *:11434
```

Coder model (Cursor): `qwen2.5-coder:7b`. Crate music ID: `qwen2.5:7b` (pulled 2026-08-30). Both stay under `~/local_tools/ollama/models`.

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:7b
```

In Cursor: Settings → Models → OpenAI-compatible endpoint `http://127.0.0.1:11434/v1`.

## Run the control plane

```bash
npm run dev          # http://127.0.0.1:47241
npm run runtime      # OSC 127.0.0.1:9000 + health :9100
```

## Unreal Engine 5 (on the Mac)

1. Enable the OSC plugin. Listen `127.0.0.1:9000`.
2. Author a Niagara Grid 3D Gas/Smoke emitter.
3. Record a 15-second Niagara Sim Cache.
4. Expose Age / Explicit Time and density on a Blueprint; map `/rekordbox/bpm`, `/rekordbox/fader`, `/rekordbox/beat_phase`.

Global MCP lives in `~/.cursor/mcp.json`, not in this workspace.

## Alkalurop org bridge (monthly 15th)

Public [ixamal](https://github.com/ixamal) originals are mirrored into the [alkalurop](https://github.com/alkalurop) org. The org section landing page is [`alkalurop/.github`](https://github.com/alkalurop/.github) (`profile/README.md`). Day-to-day work stays on ixamal.

```bash
# First / manual run (uses local `gh` as org admin; no tokens in git)
~/github/ixamal/ix/docs/examples/alkalurop-bridge.sh

# Load the 15th-of-month 15:00 job
cp ~/github/ixamal/ix/docs/examples/ai.ixamal.alkalurop-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.ixamal.alkalurop-bridge.plist
```

Log: `/tmp/ix-alkalurop-bridge.log`. `alkalurop/ix` cannot use GitHub’s transfer redirect from the old path — the script checks `owner.login` is `alkalurop` before it treats the dest as present.
