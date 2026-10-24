#!/usr/bin/env bash
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${AUTOMATION_HOME:-${HOME}/automation}"

mkdir -p "$DEST"
rsync -a --exclude 'install.sh' "$SRC/" "$DEST/"
chmod +x "$DEST"/contacts/*.sh 2>/dev/null || true

echo "Installed to: $DEST"
echo "Try: $DEST/contacts/duplicate-by-name.sh"
