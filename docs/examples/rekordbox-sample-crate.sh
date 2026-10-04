#!/bin/bash
# Rekordbox Capture → Saved + SAMPLES/Samplers in NML and rekordbox.xml
#
#   docs/examples/rekordbox-sample-crate.sh
#   docs/examples/rekordbox-sample-crate.sh --execute
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=crate
exec python3 -u -m ix_crate rekordbox-sample-crate "$@"
