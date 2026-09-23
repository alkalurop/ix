#!/bin/bash
# 5am play harvest. Load with docs/examples/ai.ixamal.crate-favorites.plist
# --playlists also writes MUSIC/GENRES and MUSIC/ACAPELLAS.
# Quit Traktor before NML. Quit Rekordbox before xml.
set -euo pipefail
cd "${HOME}/github/ixamal/ix"
export PYTHONPATH=crate
python3 -m ix_crate favorites --execute --playlists
